from __future__ import annotations

from config.paths import env
from config.settings.base import *
from config.settings.base import REST_FRAMEWORK, SPECTACULAR_SETTINGS

DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["*"])

EMAIL_BACKEND = env.str(
    "DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)

# On a laptop you usually run only the API process, so tasks execute inline.
# Set DJANGO_CELERY_TASK_ALWAYS_EAGER=False to use a real worker instead.
CELERY_TASK_ALWAYS_EAGER = env.bool("DJANGO_CELERY_TASK_ALWAYS_EAGER", default=True)
CELERY_TASK_IGNORE_RESULT = True

REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}

SPECTACULAR_SETTINGS = {
    **SPECTACULAR_SETTINGS,
    "SERVE_INCLUDE_SCHEMA": True,
}
