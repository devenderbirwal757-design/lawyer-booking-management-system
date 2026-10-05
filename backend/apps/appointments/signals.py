"""Invalidation hooks for the availability slot cache (plan §5).

Any write to an appointment changes what occupies the provider's calendar, so
`post_save`/`post_delete` bump the provider's availability revision counter
(the same mechanism scheduling uses for rules/exceptions). Without this, a
just-created hold could still be offered by a cached, now-stale slot grid
until the TTL expires (S §B4 "no stale slots served past staleTime").
"""

from __future__ import annotations

from typing import Any

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.appointments.models import Appointment
from apps.scheduling.service import bump_provider_revision


@receiver(post_save, sender=Appointment)
@receiver(post_delete, sender=Appointment)
def _appointment_changed(sender: Any, instance: Appointment, **kwargs: Any) -> None:
    bump_provider_revision(instance.provider_id)


__all__ = ("_appointment_changed",)
