"""Invalidation hooks for the availability slot cache (plan §3 Phase 3).

Any write to a rule or exception must invalidate that provider's cached slot
grids, or an admin's calendar edit silently stops applying until the cache TTL
expires. `post_save`/`post_delete` bump the provider's revision counter, which
flows into every `SlotService` cache key.
"""

from __future__ import annotations

from typing import Any

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.scheduling.models import AvailabilityException, AvailabilityRule
from apps.scheduling.service import bump_provider_revision


def _drop_provider(instance: Any) -> None:
    bump_provider_revision(instance.provider_id)


@receiver(post_save, sender=AvailabilityRule)
@receiver(post_delete, sender=AvailabilityRule)
@receiver(post_save, sender=AvailabilityException)
@receiver(post_delete, sender=AvailabilityException)
def _availability_changed(sender: Any, instance: Any, **kwargs: Any) -> None:
    _drop_provider(instance)


__all__ = ("_availability_changed",)
