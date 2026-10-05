from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from common.views import healthz, readyz

API_V1 = "api/v1/"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", healthz, name="healthz"),
    path("healthz/", healthz),
    path("readyz", readyz, name="readyz"),
    path("readyz/", readyz),
    # The schema is always available so clients can generate code from it.
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        API_V1,
        include(("config.api_urls", "api_v1"), namespace="v1"),
    ),
]

if settings.SERVE_API_DOCS:
    urlpatterns += [
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
        path("", RedirectView.as_view(url="/api/docs/")),
        *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
    ]
