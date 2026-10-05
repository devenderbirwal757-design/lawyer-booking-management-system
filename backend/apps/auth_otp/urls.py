"""Customer OTP routing (plan §4).

Wall routes live under `/api/v1/auth/otp/...`; the polymorphic `/auth/me` is
registered in `config/api_urls.py` alongside them.
"""

from __future__ import annotations

from django.urls import path

from apps.auth_otp.views import OtpRequestView, OtpVerifyView

app_name = "auth_otp"

urlpatterns = [
    path("request", OtpRequestView.as_view(), name="otp-request"),
    path("verify", OtpVerifyView.as_view(), name="otp-verify"),
]
