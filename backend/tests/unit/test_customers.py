"""Customer model constraints: E.164 normalisation, uniqueness, isolation.

The identity rules (plan §6.3, S §A3):
- `phone` normalised to E.164 and unique per tenant;
- `email` optional (D3) and unique per tenant *when set*;
- every read is tenant-scoped and fails closed.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.db import IntegrityError

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _tenant(slug: str = "dwyer", **kwargs: Any) -> Any:
    from apps.tenants.models import Tenant

    return Tenant.objects.create(slug=slug, name="Dwyer LLP", timezone="UTC", **kwargs)


def test_save_normalises_phone_to_e164() -> None:
    from apps.customers.models import Customer

    tenant = _tenant()
    customer = Customer.objects.create(tenant=tenant, phone="0 98765 43210")
    assert customer.phone == "+919876543210"


def test_save_normalises_email() -> None:
    from apps.customers.models import Customer

    tenant = _tenant()
    customer = Customer.objects.create(
        tenant=tenant, phone="+919876543210", email="  A@Example.COM "
    )
    assert customer.email == "a@example.com"


def test_duplicate_phone_within_tenant_is_rejected() -> None:
    from django.db import transaction

    from apps.customers.models import Customer

    tenant = _tenant()
    Customer.objects.create(tenant=tenant, phone="+919876543210")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Customer.objects.create(tenant=tenant, phone="+919876543210")


def test_same_phone_across_tenants_is_allowed() -> None:
    from apps.customers.models import Customer

    a = _tenant("dwyer")
    b = _tenant("haas")
    Customer.objects.create(tenant=a, phone="+919876543210")
    Customer.objects.create(tenant=b, phone="+919876543210")
    assert Customer.objects.unfiltered().filter(phone="+919876543210").count() == 2


def test_email_unique_per_tenant_only_when_set() -> None:
    from django.db import transaction

    from apps.customers.models import Customer

    tenant = _tenant()
    Customer.objects.create(tenant=tenant, phone="+919876543210", email="a@example.com")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Customer.objects.create(tenant=tenant, phone="+919876543211", email="A@example.com")

    other = _tenant("haas")
    Customer.objects.create(tenant=other, phone="+919876543212", email="a@example.com")

    Customer.objects.create(tenant=tenant, phone="+919876543213")
    Customer.objects.create(tenant=tenant, phone="+919876543214")


def test_customer_reads_fail_closed_without_tenant() -> None:
    from apps.customers.models import Customer
    from common.exceptions import TenantContextMissing

    with pytest.raises(TenantContextMissing):
        list(Customer.objects.all())


def test_clean_rejects_invalid_phone() -> None:
    from django.core.exceptions import ValidationError

    from apps.customers.models import Customer

    tenant = _tenant()
    customer = Customer(tenant=tenant, phone="12345")
    with pytest.raises(ValidationError):
        customer.clean()

    customer.phone = "+919876543210"
    customer.clean()
    assert customer.phone == "+919876543210"
