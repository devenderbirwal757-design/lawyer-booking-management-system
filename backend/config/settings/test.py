from __future__ import annotations

from config.paths import env
from config.settings.base import *
from config.settings.base import DATABASES as BASE_DATABASES
from config.settings.base import REST_FRAMEWORK

DEBUG = False
SECRET_KEY = env.str("DJANGO_TEST_SECRET_KEY", default="test-secret-key-not-for-production")
ALLOWED_HOSTS = ["*", "testserver"]

# Tests resolve the tenant explicitly, by wrapping the call in `tenant_context(...)`
# or by addressing a fixture tenant, and every fixture invents its own slug. A
# developer's `.env` naming a real slug would otherwise leak in through the
# `import *` above and make `TenantMiddleware` 404 *every* request with
# `tenant_unavailable` - a 125-test failure whose cause is nowhere in the failing
# assertion. Same reasoning as overriding `SECRET_KEY` above: the suite must not
# inherit a developer's environment.
DEFAULT_TENANT_SLUG = None

# Test-only app providing a minimal tenant-scoped model so the shared
# `common/` layer is verified against a real database, not mocks.
INSTALLED_APPS = [
    *INSTALLED_APPS,
    "tests.testapp",
]

ROOT_URLCONF = "tests.testapp.urls"
SERVE_API_DOCS = True

# WhiteNoise warns about a missing STATIC_ROOT under the test runner.
MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m]

# ---------------------------------------------------------------- database
# Tests run against real PostgreSQL: the double-booking guarantee is a
# PostgreSQL exclusion constraint, which SQLite cannot express.
# btree_gist is pre-created on the test database (see README).
DATABASES = {
    "default": {
        **BASE_DATABASES["default"],
        "NAME": env.str("DJANGO_DB_NAME", default="lawyer"),
        "CONN_MAX_AGE": 0,
        "TEST": {
            "NAME": env.str("DJANGO_TEST_DB_NAME", default="lawyer_test"),
        },
    }
}

# ---------------------------------------------------------------- cache / celery
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "lawyer-tests",
    }
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_TASK_IGNORE_RESULT = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = "cache+memory://"

# ---------------------------------------------------------------- email
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# ---------------------------------------------------------------- security
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
SECURE_SSL_REDIRECT = False
CORS_ALLOWED_ORIGINS = []
CSRF_TRUSTED_ORIGINS = []

# Throttling is asserted by dedicated tests; keeping it off the global
# defaults makes the rest of the suite independent of the clock.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_CLASSES": [],
}

# ---------------------------------------------------------------- storage
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# ---------------------------------------------------------------- logging
LOG_JSON = False
LOG_LEVEL = env.str("DJANGO_LOG_LEVEL", default="WARNING")
