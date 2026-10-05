"""Admin auth routing (`apps/accounts` views).

Auth endpoints are versioned under `/api/v1/auth/...` like everything else;
S §A2 requires login be rate limited per IP and per email, which the views
declare explicitly.
"""

from __future__ import annotations

from django.urls import path

from apps.accounts.views import AdminLoginView, AdminLogoutView, AdminRefreshView

app_name = "accounts"

urlpatterns = [
    path("admin/login", AdminLoginView.as_view(), name="admin-login"),
    path("admin/refresh", AdminRefreshView.as_view(), name="admin-refresh"),
    path("admin/logout", AdminLogoutView.as_view(), name="admin-logout"),
]
