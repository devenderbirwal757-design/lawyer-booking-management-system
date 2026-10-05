from __future__ import annotations

import os
from typing import Any

from config.paths import DJANGO_SETTINGS_MODULE

os.environ.setdefault("DJANGO_SETTINGS_MODULE", DJANGO_SETTINGS_MODULE)

from celery import Celery
from celery.signals import setup_logging

app = Celery("lawyer")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@setup_logging.connect
def config_loggers(*_args: object, **_kwargs: object) -> None:
    """Let Django's LOGGING config drive Celery's loggers too."""
    from logging.config import dictConfig

    from django.conf import settings

    dictConfig(settings.LOGGING)


@app.task(bind=True, ignore_result=True)
def debug_task(self: Any) -> str:
    return f"request: {self.request!r}"
