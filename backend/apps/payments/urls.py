"""Payment URLs (plan §6).

Kept in a dedicated module rather than only the router because the webhook is
not a router view - it is unauthenticated, throttled on its own scope, and
mounted at an exact path that must never gain a trailing-slash twin (a gateway
configured for one URL would get a 301 for the other).
"""

from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.payments.views import (
    AdminPaymentEventViewSet,
    AdminPaymentViewSet,
    AdminRefundViewSet,
    CustomerPaymentViewSet,
    PaymentViewSet,
    PaymentWebhookView,
)

router = DefaultRouter()
router.register("payments", PaymentViewSet, basename="payment")
router.register("me/payments", CustomerPaymentViewSet, basename="me-payment")
router.register("admin/payments", AdminPaymentViewSet, basename="admin-payment")
router.register("admin/refunds", AdminRefundViewSet, basename="admin-refund")
router.register(
    "admin/payment-events",
    AdminPaymentEventViewSet,
    basename="admin-payment-event",
)

app_name = "payments"

urlpatterns = [
    path("payments/webhook", PaymentWebhookView.as_view(), name="payment-webhook"),
    path("", include(router.urls)),
]
