"""Tests for the structlog/stdlib logging bridge.

Regression coverage: if a `LOGGING` formatter entry passes a dotted string
where structlog expects a callable (either because Django's dictConfig does
not resolve strings nested inside kwargs, or because structlog's deprecated
singular ``processor`` kwarg is used), rendering raises
``TypeError: 'str' object is not callable``. The stdlib ``logging`` module
swallows that and prints "--- Logging error ---" to stderr while the
application keeps running, so it is easy to miss: these tests render records
directly and assert no such failure occurs.
"""

from __future__ import annotations

import copy
import functools
import io
import json
import logging
import logging.config
from typing import Any

import pytest
import structlog
from django.conf import settings
from django.utils.module_loading import import_string

from common.logging import JSON_FORMATTER, PLAIN_FORMATTER


def build_formatter(config: dict[str, Any]) -> logging.Formatter:
    """Instantiate a formatter config the way Django's dictConfig does."""
    kwargs = dict(config)
    factory = import_string(kwargs.pop("()"))
    return factory(**kwargs)


def make_record(
    name: str = "django.request", msg: str = "Not Found: /missing"
) -> logging.LogRecord:
    return logging.LogRecord(
        name=name,
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )


@pytest.mark.parametrize("config", [JSON_FORMATTER, PLAIN_FORMATTER])
def test_formatter_processors_are_callables(config: dict[str, Any]) -> None:
    processors = config["processors"]
    assert processors
    assert all(callable(processor) for processor in processors)


@pytest.mark.parametrize("config", [JSON_FORMATTER, PLAIN_FORMATTER])
def test_foreign_stdlib_record_renders(config: dict[str, Any]) -> None:
    rendered = build_formatter(config).format(make_record())
    assert "Not Found: /missing" in rendered


def test_json_formatter_emits_valid_json_without_processor_meta() -> None:
    payload = json.loads(build_formatter(JSON_FORMATTER).format(make_record()))
    assert payload["event"] == "Not Found: /missing"
    assert payload["level"] == "warning"
    assert payload["logger"] == "django.request"
    assert "timestamp" in payload
    assert "_record" not in payload
    assert "_from_structlog" not in payload


def test_plain_formatter_is_human_readable() -> None:
    rendered = build_formatter(PLAIN_FORMATTER).format(make_record())
    assert "warning" in rendered
    assert "Not Found: /missing" in rendered


def test_dotted_string_processor_would_break_logging() -> None:
    """Documents the failure mode this configuration previously had."""
    broken = {
        "()": "structlog.stdlib.ProcessorFormatter",
        "processor": "structlog.processors.JSONRenderer",
    }
    with pytest.raises(TypeError, match="'str' object is not callable"):
        build_formatter(broken).format(make_record())


def test_dict_config_logs_foreign_and_structlog_records(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = io.StringIO()
    config = {
        "version": 1,
        "disable_existing_loggers": True,
        "formatters": {"json": JSON_FORMATTER, "plain": PLAIN_FORMATTER},
        "handlers": {
            "console": {
                "()": functools.partial(logging.StreamHandler, stream),
                "formatter": "json",
            },
        },
        "root": {"handlers": ["console"], "level": "INFO"},
        # Mirrors config.settings.base.LOGGING so the real logger names used
        # by Django and the apps are exercised.
        "loggers": {
            "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
            "apps": {"handlers": ["console"], "level": "INFO", "propagate": False},
        },
    }
    root_level = logging.getLogger().level
    try:
        logging.config.dictConfig(config)
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.stdlib.add_log_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=False,
        )
        logging.getLogger("django.request").warning("Not Found: /missing")
        structlog.get_logger("apps.audit").warning("payment.webhook.failed")
    finally:
        structlog.reset_defaults()
        # Restore Django's own logging configuration for the rest of the suite.
        dictConfig_copy = copy.deepcopy(settings.LOGGING)
        dictConfig_copy["disable_existing_loggers"] = True
        logging.config.dictConfig(dictConfig_copy)
        logging.getLogger().setLevel(root_level)

    output = stream.getvalue()
    assert "Logging error" not in output
    events = [json.loads(line)["event"] for line in output.splitlines() if line.strip()]
    assert "Not Found: /missing" in events
    assert "payment.webhook.failed" in events
