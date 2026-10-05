from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from config.urls import urlpatterns as base_urlpatterns
from tests.testapp.views import WidgetViewSet

router = DefaultRouter()
router.register("test-widgets", WidgetViewSet, basename="widget")

urlpatterns = [
    *base_urlpatterns,
    path("api/v1/", include(router.urls)),
]
