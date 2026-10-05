from __future__ import annotations

import os
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BASE_DIR.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_SECRET_KEY=(str, ""),
    DJANGO_ALLOWED_HOSTS=(list, []),
    # No default here on purpose: `base.py` supplies the localhost fallbacks
    # for development, while `prod.py` refuses to start with an empty list. An
    # empty default at this layer would silently shadow the development default.
    DJANGO_CORS_ALLOWED_ORIGINS=(list, []),
    DJANGO_CSRF_TRUSTED_ORIGINS=(list, []),
    DJANGO_SECURE_SSL_REDIRECT=(bool, False),
    DJANGO_USE_TLS=(bool, False),
    DJANGO_DB_NAME=(str, "lawyer"),
    DJANGO_DB_USER=(str, "lawyer_app"),
    DJANGO_DB_PASSWORD=(str, "lawyer_app"),
    DJANGO_DB_HOST=(str, "127.0.0.1"),
    DJANGO_DB_PORT=(str, "5432"),
    DJANGO_DB_CONN_MAX_AGE=(int, 60),
    DJANGO_DB_SSLMODE=(str, "prefer"),
    DJANGO_DB_EXCLUDE_REPLICA=(bool, False),
    DJANGO_CACHE_URL=(str, "redis://127.0.0.1:6379/0"),
    DJANGO_CELERY_BROKER_URL=(str, "redis://127.0.0.1:6379/1"),
    DJANGO_CELERY_RESULT_BACKEND=(str, "redis://127.0.0.1:6379/2"),
    DJANGO_CELERY_TASK_ALWAYS_EAGER=(bool, False),
    DJANGO_CELERY_TASK_EAGER_PROPAGATES=(bool, True),
    DJANGO_DEFAULT_FROM_EMAIL=(str, "no-reply@example.com"),
    DJANGO_EMAIL_BACKEND=(str, "django.core.mail.backends.console.EmailBackend"),
    DJANGO_LOG_LEVEL=(str, "INFO"),
    DJANGO_LOG_JSON=(bool, True),
    DJANGO_STORAGE_BACKEND=(str, "django.core.files.storage.FileSystemStorage"),
    DJANGO_AWS_ACCESS_KEY_ID=(str, ""),
    DJANGO_AWS_SECRET_ACCESS_KEY=(str, ""),
    DJANGO_AWS_STORAGE_BUCKET_NAME=(str, ""),
    DJANGO_AWS_S3_REGION_NAME=(str, "ap-south-1"),
    DJANGO_AWS_S3_ENDPOINT_URL=(str, ""),
    DJANGO_AWS_QUERYSTRING_AUTH=(bool, False),
    DJANGO_AWS_S3_CUSTOM_DOMAIN=(str, ""),
    DJANGO_ACCESS_TOKEN_LIFETIME_MINUTES=(int, 15),
    DJANGO_REFRESH_TOKEN_LIFETIME_DAYS=(int, 7),
    DJANGO_PAGINATION_PAGE_SIZE=(int, 20),
    DJANGO_PAGINATION_MAX_PAGE_SIZE=(int, 100),
    DJANGO_THROTTLE_ANON_RATE=(str, "60/min"),
    DJANGO_THROTTLE_USER_RATE=(str, "600/min"),
    DJANGO_THROTTLE_OTP_REQUEST_RATE=(str, "5/hour"),
    DJANGO_THROTTLE_OTP_VERIFY_RATE=(str, "20/hour"),
    DJANGO_THROTTLE_LOGIN_RATE=(str, "5/15min"),
    DJANGO_THROTTLE_BOOKING_RATE=(str, "10/min"),
    DJANGO_THROTTLE_AVAILABILITY_RATE=(str, "120/min"),
    DJANGO_THROTTLE_WEBHOOK_RATE=(str, "120/min"),
    DJANGO_THROTTLE_PAYMENT_RATE=(str, "30/min"),
    DJANGO_PAYMENT_GATEWAY=(str, "razorpay"),
    DJANGO_PAYMENT_MODE=(str, "test"),
    DJANGO_PAYMENT_RECONCILE_MINUTES=(int, 30),
    DJANGO_RAZORPAY_KEY_ID=(str, ""),
    DJANGO_RAZORPAY_KEY_SECRET=(str, ""),
    DJANGO_RAZORPAY_WEBHOOK_SECRET=(str, ""),
    DJANGO_SLOT_HOLD_MINUTES=(int, 10),
    DJANGO_CANCELLATION_POLICY_MIN_HOURS=(int, 0),
    DJANGO_MAX_ACTIVE_HOLDS_PER_CUSTOMER=(int, 5),
    DJANGO_BOOKING_LEAD_TIME_HOURS=(int, 2),
    DJANGO_BOOKING_LOOKAHEAD_DAYS=(int, 60),
    DJANGO_AVAILABILITY_LEAD_TIME_MINUTES=(int, 0),
    DJANGO_AVAILABILITY_HORIZON_DAYS=(int, 60),
    DJANGO_AVAILABILITY_CACHE_SECONDS=(int, 60),
    DJANGO_DEFAULT_TIMEZONE=(str, "Asia/Kolkata"),
    DJANGO_DEFAULT_CURRENCY=(str, "INR"),
    DJANGO_OTP_LIFETIME_MINUTES=(int, 5),
    DJANGO_OTP_MAX_ATTEMPTS=(int, 5),
    DJANGO_OTP_SMS_BACKEND=(str, "console"),
    DJANGO_DEFAULT_COUNTRY_CODE=(str, "+91"),
)

_ENV_FILE = REPO_DIR / ".env" if (REPO_DIR / ".env").is_file() else BASE_DIR / ".env"
if _ENV_FILE.is_file():
    environ.Env.read_env(str(_ENV_FILE))

ENV = env

SETTINGS_MODULE_BY_ENV: dict[str, str] = {
    "dev": "config.settings.dev",
    "development": "config.settings.dev",
    "local": "config.settings.dev",
    "test": "config.settings.test",
    "testing": "config.settings.test",
    "prod": "config.settings.prod",
    "production": "config.settings.prod",
}

#: Resolved entrypoint settings module. Explicit `DJANGO_SETTINGS_MODULE` wins;
#: otherwise `DJANGO_SETTINGS_MODULE_SHORT` (dev | test | prod) selects it.
DJANGO_SETTINGS_MODULE = os.environ.get("DJANGO_SETTINGS_MODULE") or SETTINGS_MODULE_BY_ENV.get(
    os.environ.get("DJANGO_SETTINGS_MODULE_SHORT", "dev").lower(),
    "config.settings.dev",
)
