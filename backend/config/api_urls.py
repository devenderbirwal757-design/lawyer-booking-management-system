from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.appointments.views import (
    AdminAppointmentViewSet,
    BookingViewSet,
    CustomerAppointmentViewSet,
)
from apps.auth_otp.views import MeView
from apps.providers.views import ProviderViewSet
from apps.scheduling.views import (
    AdminAvailabilityExceptionViewSet,
    AdminAvailabilityRuleViewSet,
    AvailableDatesView,
    SlotsView,
)
from apps.services.views import AdminServiceViewSet, ServiceViewSet

router = DefaultRouter()
router.register("services", ServiceViewSet, basename="service")
router.register("providers", ProviderViewSet, basename="provider")
router.register("appointments", BookingViewSet, basename="booking")
router.register("me/appointments", CustomerAppointmentViewSet, basename="me-appointment")
router.register("admin/services", AdminServiceViewSet, basename="admin-service")
router.register("admin/appointments", AdminAppointmentViewSet, basename="admin-appointment")
router.register(
    "admin/availability/rules",
    AdminAvailabilityRuleViewSet,
    basename="admin-availability-rule",
)
router.register(
    "admin/availability/exceptions",
    AdminAvailabilityExceptionViewSet,
    basename="admin-availability-exception",
)

app_name = "api_v1"

urlpatterns = [
    path("auth/otp/", include("apps.auth_otp.urls")),
    path("auth/me", MeView.as_view(), name="me"),
    path("auth/", include("apps.accounts.urls")),
    path("availability/slots", SlotsView.as_view(), name="availability-slots"),
    path("availability/dates", AvailableDatesView.as_view(), name="availability-dates"),
    path("", include("apps.payments.urls")),
    path("", include("apps.reports.urls")),
    path("", include(router.urls)),
]
