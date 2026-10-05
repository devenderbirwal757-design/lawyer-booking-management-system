"""Admin reports endpoints (Phase 9)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from apps.appointments.models import Appointment, AppointmentStatus
from apps.customers.models import Customer
from apps.payments.models import PaymentOrder, PaymentOrderStatus
from common.mixins import TenantFilterMixin

# ViewSet not needed


class AdminReportViewSet(TenantFilterMixin, ViewSet):
    permission_classes = [permissions.IsAuthenticated]  # Will be refined by AdminScoped if needed
    tenant_field = "tenant_id"

    def get_tenant(self) -> Any:
        return getattr(self.request, "tenant", None)

    @action(detail=False, methods=["get"], url_path="dashboard")
    def dashboard(self, request: Request) -> Response:
        tenant = self.get_tenant()
        now_dt = timezone.now()
        today = now_dt.date()
        start_of_month = today.replace(day=1)
        end_of_month = (start_of_month + timedelta(days=32)).replace(day=1) - timedelta(days=1)

        # appointments today
        appts_today = Appointment.objects.filter(tenant=tenant, start_at__date=today).count()

        # upcoming (future start)
        appts_upcoming = Appointment.objects.filter(tenant=tenant, start_at__gt=now_dt).count()

        # customers (distinct)
        customers = Customer.objects.filter(tenant=tenant).count()

        # revenue collected (SUCCESS payment orders in month) - amounts stored as Decimal
        rev_collected = (
            PaymentOrder.objects.filter(
                tenant=tenant,
                status=PaymentOrderStatus.SUCCESS,
                paid_at__date__gte=start_of_month,
                paid_at__date__lte=end_of_month,
            ).aggregate(total=Sum("amount"))["total"]
            or 0
        )

        return Response(
            {
                "today_appointments": appts_today,
                "upcoming_appointments": appts_upcoming,
                "total_customers": customers,
                "revenue_collected_month": str(rev_collected),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"], url_path="appointments")
    def appointments(self, request: Request) -> Response:
        tenant = self.get_tenant()
        qs = Appointment.objects.filter(tenant=tenant).values("status").annotate(count=Count("id"))

        totals = dict.fromkeys(AppointmentStatus.values, 0)
        for row in qs:
            totals[row["status"]] = row["count"]

        return Response({"totals": totals}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="revenue")
    def revenue(self, request: Request) -> Response:
        tenant = self.get_tenant()
        qs = (
            PaymentOrder.objects.filter(tenant=tenant)
            .values("status")
            .annotate(total=Sum("amount"))
        )

        revenue = {
            "collected": "0",
            "pending": "0",
            "refunded": "0",
        }
        for row in qs:
            st = row["status"]
            total = row["total"] or 0
            if st == PaymentOrderStatus.SUCCESS:
                revenue["collected"] = str(total)
            elif st in (PaymentOrderStatus.PENDING, PaymentOrderStatus.CREATED):
                revenue["pending"] = str(total)
            elif st == PaymentOrderStatus.REFUNDED:
                revenue["refunded"] = str(total)

        return Response(revenue, status=status.HTTP_200_OK)
