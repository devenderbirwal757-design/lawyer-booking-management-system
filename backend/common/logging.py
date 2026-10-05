from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from django.conf import settings

#: Applied to log records that did not originate in structlog (e.g. Django's
#: own "Not Found: /foo" warnings) so they carry the same bound context.
#: These must be real callables, not dotted strings: Django's logging config
#: invokes each entry with no arguments.
FOREIGN_PRE_CHAIN: list[structlog.types.Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
]

#: Applied to structlog-originated records; the final entry hands the event
#: to Django's `ProcessorFormatter`, which does the actual rendering.
STRUCTLOG_PRE_CHAIN: list[structlog.types.Processor] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
    structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
]


def configure_logging() -> None:
    """Bridge structlog into Django's stdlib logging (see LOGGING in base.py)."""
    structlog.configure(
        processors=STRUCTLOG_PRE_CHAIN,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    logging.getLogger("django.db.backends").setLevel(logging.WARNING)
    logging.getLogger("django.security.DisallowedHost").setLevel(logging.ERROR)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    logging.getLogger("celery.utils.functional").setLevel(logging.WARNING)


def log_json_enabled() -> bool:
    return bool(getattr(settings, "LOG_JSON", True))


def stdlib_formatter(renderer: structlog.types.Processor) -> dict[str, Any]:
    """Build a `LOGGING` formatter entry around `structlog`'s ProcessorFormatter.

    Django's dictConfig does not resolve dotted paths *inside* kwargs, and
    structlog's `processors` chain requires real callables, so both the
    renderer and the pre-chain are passed as objects.
    """
    return {
        "()": "structlog.stdlib.ProcessorFormatter",
        "processors": [structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
        "foreign_pre_chain": list(FOREIGN_PRE_CHAIN),
    }


def renderer_for(json_output: bool) -> structlog.types.Processor:
    if json_output:
        return structlog.processors.JSONRenderer(ensure_ascii=False)
    return structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())


#: Ready-to-use `LOGGING["formatters"]` entries.
JSON_FORMATTER = stdlib_formatter(renderer_for(True))
PLAIN_FORMATTER = stdlib_formatter(renderer_for(False))
