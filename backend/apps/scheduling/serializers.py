"""Serializers for availability rules and exceptions (plan §4 admin surface).

Both validate through the model's own `clean()` - the field-keyed
`ValidationError` it raises is already mapped to the API's 400 envelope by the
shared exception handler, which is how these two claims stay enforced in one
place: `end > start`, and no overlapping windows for the same weekday.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.appointments.services import ensure_no_blocked_over_appointment
from apps.providers.serializers import TenantProviderField
from apps.scheduling.models import AvailabilityException, AvailabilityRule


class AvailabilityRuleSerializer(serializers.ModelSerializer[AvailabilityRule]):
    provider = TenantProviderField()

    class Meta:
        model = AvailabilityRule
        fields = (
            "id",
            "provider",
            "weekday",
            "start_time",
            "end_time",
            "effective_from",
            "effective_to",
        )
        read_only_fields = ("id",)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        self._as_model(attrs).clean()
        return attrs

    def _as_model(self, attrs: dict[str, Any]) -> AvailabilityRule:
        rule = AvailabilityRule()
        fields = (
            "provider",
            "weekday",
            "start_time",
            "end_time",
            "effective_from",
            "effective_to",
        )
        for field in fields:
            setattr(rule, field, attrs.get(field, self._existing(field)))
        if self.instance is not None:
            rule.pk = self.instance.pk
        return rule

    def _existing(self, field: str) -> Any:
        return getattr(self.instance, field, None) if self.instance is not None else None


class AvailabilityExceptionSerializer(serializers.ModelSerializer[AvailabilityException]):
    provider = TenantProviderField()

    class Meta:
        model = AvailabilityException
        fields = ("id", "provider", "date", "start_time", "end_time", "type", "reason")
        read_only_fields = ("id",)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        exception = self._as_model(attrs)
        exception.clean()
        # A BLOCKED day that would cover an active booking must be refused
        # outright (plan §5.5, answered 409 `slot_occupied`): the appointment
        # wins, and the admin is told to cancel or reschedule it first.
        if self.instance is None and (attrs.get("type") or "BLOCKED") == "BLOCKED":
            ensure_no_blocked_over_appointment(exception)
        return attrs

    def _as_model(self, attrs: dict[str, Any]) -> AvailabilityException:
        exception = AvailabilityException()
        for field in ("provider", "date", "start_time", "end_time", "type", "reason"):
            setattr(exception, field, attrs.get(field, self._existing(field)))
        return exception

    def _existing(self, field: str) -> Any:
        return getattr(self.instance, field, None) if self.instance is not None else None


__all__ = ("AvailabilityExceptionSerializer", "AvailabilityRuleSerializer")
