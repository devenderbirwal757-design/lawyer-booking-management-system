from __future__ import annotations

import os

from config.paths import DJANGO_SETTINGS_MODULE

os.environ.setdefault("DJANGO_SETTINGS_MODULE", DJANGO_SETTINGS_MODULE)

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
