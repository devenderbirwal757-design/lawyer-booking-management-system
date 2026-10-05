from __future__ import annotations

from config.paths import env
from config.settings.base import *
from config.settings.base import DATABASES, REST_FRAMEWORK, SPECTACULAR_SETTINGS

DEBUG = False

SECRET_KEY = env.str("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY must be set in production.")
if len(SECRET_KEY) < 50:
    raise RuntimeError("DJANGO_SECRET_KEY must be at least 50 characters in production.")
if not ALLOWED_HOSTS:
    raise RuntimeError("DJANGO_ALLOWED_HOSTS must be set in production.")
if env.bool("DJANGO_DEBUG"):
    raise RuntimeError("DEBUG must be False in production.")

# ---------------------------------------------------------------- https
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

CORS_ALLOWED_ORIGINS = env.list("DJANGO_CORS_ALLOWED_ORIGINS")
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS")

# Unlike development, production has no localhost fallback to inherit, so an
# unset allowlist is left to fail here rather than at the first browser request:
# an empty list silently produces no `Access-Control-Allow-Origin`, which is
# exactly the cross-origin breakage this wiring exists to prevent.
if not CORS_ALLOWED_ORIGINS:
    raise RuntimeError(
        "DJANGO_CORS_ALLOWED_ORIGINS must be set in production. List every exact "
        "frontend origin that calls the API, e.g. https://app.example.com. Never "
        "use `*`: cookies are credentialed, and `*` is invalid with credentials."
    )

# ---------------------------------------------------------------- storage
if not env.str("DJANGO_AWS_STORAGE_BUCKET_NAME"):
    raise RuntimeError("DJANGO_AWS_STORAGE_BUCKET_NAME must be set in production.")

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env.str("DJANGO_AWS_STORAGE_BUCKET_NAME"),
            "region_name": env.str("DJANGO_AWS_S3_REGION_NAME", default="ap-south-1"),
            "endpoint_url": env.str("DJANGO_AWS_S3_ENDPOINT_URL", default="") or None,
            "custom_domain": env.str("DJANGO_AWS_S3_CUSTOM_DOMAIN", default="") or None,
            "querystring_auth": env.bool("DJANGO_AWS_QUERYSTRING_AUTH", default=False),
            "default_acl": env.str("DJANGO_AWS_DEFAULT_ACL", default="private"),
        },
    },
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# ---------------------------------------------------------------- db
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DJANGO_DB_CONN_MAX_AGE", default=120)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DATABASES["default"]["OPTIONS"]["sslmode"] = env.str("DJANGO_DB_SSLMODE", default="require")

# ---------------------------------------------------------------- celery
CELERY_TASK_ALWAYS_EAGER = False
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "visibility_timeout": env.int("DJANGO_CELERY_VISIBILITY_TIMEOUT", default=3600),
    "socket_keepalive": True,
    "health_check_interval": 30,
}
CELERY_WORKER_MAX_TASKS_PER_CHILD = 1000
CELERY_RESULT_EXPIRES = 60 * 60 * 24

# Email goes out over SES-compatible SMTP in production.
EMAIL_BACKEND = env.str(
    "DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend"
)

# ---------------------------------------------------------------- api
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_THROTTLE_CLASSES": [
        "common.throttles.AnonRateThrottle",
        "common.throttles.UserRateThrottle",
        "common.throttles.ScopedRateThrottle",
    ],
}

SPECTACULAR_SETTINGS = {
    **SPECTACULAR_SETTINGS,
    "SERVE_INCLUDE_SCHEMA": False,
}

SERVE_API_DOCS = False

LOG_JSON = env.bool("DJANGO_LOG_JSON", default=True)
LOG_LEVEL = env.str("DJANGO_LOG_LEVEL", default="INFO")
