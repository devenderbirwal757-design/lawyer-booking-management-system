from __future__ import annotations

from django.urls import path

from apps.reports.views import AdminReportViewSet

urlpatterns = [
    path(
        "admin/reports/dashboard",
        AdminReportViewSet.as_view({"get": "dashboard"}),
        name="admin-reports-dashboard",
    ),
    path(
        "admin/reports/appointments",
        AdminReportViewSet.as_view({"get": "appointments"}),
        name="admin-reports-appointments",
    ),
    path(
        "admin/reports/revenue",
        AdminReportViewSet.as_view({"get": "revenue"}),
        name="admin-reports-revenue",
    ),
]
