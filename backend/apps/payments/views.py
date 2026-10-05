"""Payment endpoints (plan §6, PRD §11).

    POST /api/v1/payments/create-order      customer  start checkout
    GET  /api/v1/payments/{id}/status       customer  poll / reconcile
    POST /api/v1/payments/webhook           gateway   signature-verified callback
    GET  /api/v1/admin/payments             admin     list captured/attempted
    POST /api/v1/admin/payments/{id}/refund admin     create PENDING_ACTION refund
    POST /api/v1/admin/refunds/{id}/settle  admin     settle -> Payment REFUNDED

What is deliberately **not** here: any endpoint that accepts a status, an
amount, or a gateway payment id from a client. There is no `PATCH
/payments/{id}` and no "mark paid" - the only writer of `Payment.SUCCESS` is
the signature-verified webhook, or a gateway truth read by reconciliation
(S §A5 asserts this by enumerating the routes).

The webhook is unauthenticated on purpose - it is the gateway calling us, and
its credential is the HMAC over the raw body. It therefore also has no tenant
context, and resolves orders by the globally unique `gateway_order_id`.
"""

from __future__ import annotations

import json
from typing import Any

from django.shortcuts import get_object_or_404
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.appointments.models import Appointment
from apps.audit.audit import audit
from apps.auth_otp.authentication import CustomerJWTAuthentication
from apps.payments import services
from apps.payments.gateways import get_gateway
from apps.payments.models import (
    Payment,
    PaymentEvent,
    PaymentEventOutcome,
    PaymentOrder,
    PaymentOrderStatus,
    Refund,
    RefundStatus,
)
from apps.payments.serializers import (
    CreateOrderSerializer,
    PaymentEventSerializer,
    PaymentOrderSerializer,
    PaymentSerializer,
    RefundSerializer,
    SettleRefundSerializer,
)
from common.exceptions import ConflictError
from common.permissions import IsAdmin, IsCustomer
from common.throttles import ScopedRateThrottle
from common.viewset import TenantScopedViewSet


def _filter_params(
    request: Any,
    *,
    choices: dict[str, Any] | None = None,
    uuids: tuple[str, ...] = (),
    date_range: bool = False,
) -> Any:
    """Build a filter kwargs mapping from validated query params.

    Hand-rolled instead of declaring `filterset_fields`, for two reasons, both
    reproduced in `tests/integration/test_filterset_hazard.py`:

    * Building a django-filter filterset introspects `Model._default_manager`,
      which here is the *tenant-scoped* manager. With no tenant bound that
      raises `TenantContextMissing`, inside `AutoFilterSet.get_filters()` -
      before any queryset is filtered - so it takes down every list request and
      `manage.py spectacular` alike.
    * A relation field becomes a `ModelChoiceFilter` whose choices come from the
      *related* model's `_default_manager`, so `filterset_fields = ["tenant"]`
      would publish every practice's slug and UUID to a caller who may only ever
      see their own. Rows stay scoped; the disclosure is the problem.

    An unsupported value is a 400 rather than a silently empty list, which is
    what a typo'd `status=` would otherwise look like. With `date_range`, `from`
    and `to` become inclusive calendar-day bounds on `created_at`.

    `tests/unit/test_filterset_guard.py` fails the build if any tenant-scoped
    viewset declares `filterset_fields` or `filterset_class`.
    """
    from datetime import date as _date
    from uuid import UUID

    from rest_framework.exceptions import ValidationError

    query = request.query_params
    params: dict[str, Any] = {}
    for name, allowed in (choices or {}).items():
        value = query.get(name)
        if value in (None, ""):
            continue
        if value not in allowed:
            raise ValidationError({name: f"Unsupported value '{value}'."})
        params[name] = value
    for name in uuids:
        value = query.get(name)
        if value in (None, ""):
            continue
        try:
            params[name] = UUID(str(value))
        except (TypeError, ValueError) as exc:
            raise ValidationError({name: "Must be a UUID."}) from exc
    if date_range:
        for param, lookup in (("from", "created_at__date__gte"), ("to", "created_at__date__lte")):
            value = query.get(param)
            if value in (None, ""):
                continue
            try:
                params[lookup] = _date.fromisoformat(str(value))
            except (TypeError, ValueError) as exc:
                raise ValidationError({param: "Must be an ISO date (YYYY-MM-DD)."}) from exc
    return params


class PaymentViewSet(TenantScopedViewSet):
    """The customer's own payment surface."""

    serializer_class = PaymentOrderSerializer
    authentication_classes = [CustomerJWTAuthentication]  # noqa: RUF012 - DRF's own style
    permission_classes = [IsCustomer]  # noqa: RUF012 - DRF's own style
    queryset = PaymentOrder.objects.unfiltered()
    throttle_scope = "payment"

    def _own_order(self, pk: Any) -> PaymentOrder:
        """Resolve an order through the current customer or 404.

        Filtering by `customer` rather than returning 403 keeps another
        customer's order indistinguishable from one that does not exist
        (S §A4).

        Reads go through `unfiltered()` plus these explicit filters, never
        `get_object_or_404(PaymentOrder, ...)`: that uses the model's *default*
        manager, which is the tenant-scoped one and raises `TenantContextMissing`
        unless a tenant is bound to the context. The middleware cannot bind one
        for a customer JWT — it runs before DRF authenticates, so `request.user`
        is anonymous and it has only the host/default slug to go on. Every test
        wraps the call in `tenant_context(...)` and hides the difference; a real
        browser request against a single-tenant install hit a 500. The customer
        filter below is the isolation guarantee, and it needs no ambient context.
        """
        order: PaymentOrder = get_object_or_404(
            self._owned_orders(),
            pk=pk,
        )
        return order

    def _owned_orders(self) -> Any:
        return PaymentOrder.objects.unfiltered().filter(
            customer=getattr(self.request, "customer", None),
            tenant_id=self.get_tenant().pk,
        )

    @action(detail=False, methods=["post"], url_path="create-order")
    def create_order(self, request: Any) -> Response:
        """Start checkout: create the gateway order for an existing hold.

        The amount is recomputed from `Service.price_amount`; a client that
        sends its own amount and gets a mismatch is told so rather than charged
        the smaller number.
        """
        payload = CreateOrderSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        appointment = get_object_or_404(
            Appointment.objects.unfiltered(),
            pk=payload.validated_data["appointment_id"],
            customer=getattr(request, "customer", None),
            tenant_id=self.get_tenant().pk,
        )
        order = get_object_or_404(
            PaymentOrder.objects.unfiltered(),
            appointment=appointment,
            tenant_id=self.get_tenant().pk,
        )

        claimed = payload.validated_data.get("amount")
        server_amount = appointment.service.price_amount
        if claimed is not None and claimed != server_amount:
            raise ConflictError(
                detail=(
                    f"This service costs {server_amount} "
                    f"{appointment.service.currency}; the amount cannot be set by the client."
                ),
                code="amount_mismatch",
            )

        order = services.create_gateway_order(order=order)
        audit(
            action="payment.order_created",
            entity_type="payments.paymentorder",
            entity_id=order.pk,
            after={"gateway_order_id": order.gateway_order_id, "amount": str(order.amount)},
            actor=request.user if getattr(request.user, "is_authenticated", False) else None,
            tenant=order.tenant,
        )
        body = services.order_response_payload(order)
        return Response(body, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="status")
    def order_status(self, request: Any, pk: Any = None) -> Response:
        """Poll the gateway and reconcile - the fallback for a missed webhook.

        Returns the order plus its payment attempts. The response is a *read*:
        it can bring a missed capture forward, but it can never assert one.
        """
        order = self._own_order(pk)
        order = services.poll_order_status(order=order)
        payments = Payment.objects.unfiltered().filter(order=order).order_by("created_at")
        body = PaymentOrderSerializer(order).data
        body["payments"] = PaymentSerializer(payments, many=True).data
        return Response(body)


class CustomerPaymentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    TenantScopedViewSet,
):
    """`GET /me/payments` - the client's own payment history (plan §6).

    Separate from `PaymentViewSet` because the routes differ in kind: the
    checkout actions address an order by id and do their own authorisation,
    while this is an ordinary list scoped to whoever is holding the JWT.
    """

    serializer_class = PaymentSerializer
    authentication_classes = [CustomerJWTAuthentication]  # noqa: RUF012 - DRF's own style
    permission_classes = [IsCustomer]  # noqa: RUF012 - DRF's own style
    #: `TenantFilterMixin` narrows to this customer's tenant; the `customer`
    #: clause is what narrows it to this customer.
    queryset = Payment.objects.unfiltered().select_related("order")
    ordering = ("-created_at",)

    def get_queryset(self) -> Any:
        # Calls super() so the tenant filter still applies on top of the
        # customer clause - shadowing it here is what leaked other tenants'
        # payments out of the admin viewsets.
        queryset = super().get_queryset()
        return queryset.filter(customer=getattr(self.request, "customer", None))


class PaymentWebhookView(APIView):
    """`POST /payments/webhook` - the gateway's callback (plan §6).

    Order of operations is the security contract:

    1. read the **raw** body (`request.body`, never `request.data` - DRF would
       have parsed and re-serialized it by the time a serializer ran);
    2. verify the signature over those bytes, constant-time;
    3. only then parse, and only then record the event.

    An invalid signature raises before step 3, so an unsigned payload leaves no
    row behind at all (S §A5).

    Every processed delivery answers 200 - matched, duplicate, unmatched,
    unhandled - because a non-2xx only earns a retry of an outcome that will
    not change. Only a bad signature is a 400.
    """

    authentication_classes: list[Any] = []  # noqa: RUF012 - DRF's own style
    permission_classes: list[Any] = [AllowAny]  # noqa: RUF012 - DRF's own style
    throttle_classes = [ScopedRateThrottle]  # noqa: RUF012 - DRF's own style
    throttle_scope = "webhook"

    def post(self, request: Any) -> Response:
        raw_body = request.body
        signature = request.headers.get("X-Razorpay-Signature", "")
        event_type = request.headers.get("X-Razorpay-Event", "")

        try:
            payload = json.loads(raw_body or b"{}")
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        if not event_type:
            event_type = str(payload.get("event") or "")

        event = services.handle_webhook(
            raw_body=raw_body,
            signature=signature,
            event_type=event_type,
            payload=payload,
            gateway=get_gateway(),
        )
        return Response(
            {"received": True, "event_id": event.event_id, "outcome": event.outcome},
            status=status.HTTP_200_OK,
        )


class AdminPaymentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    TenantScopedViewSet,
):
    """Admin read surface plus the manual-refund action (plan §6.2).

    `List`/`Retrieve` are mixed in explicitly: this viewset is a
    `TenantScopedViewSet` (a bare `GenericViewSet`), so without them DRF's router
    registers only the `@action`s below and `GET /admin/payments` 404s while the
    dashboard's payments table happily asks for it.
    """

    serializer_class = PaymentSerializer
    authentication_classes: list[Any] = []  # noqa: RUF012 - DRF's own style
    permission_classes: list[Any] = [IsAdmin]  # noqa: RUF012 - DRF's own style
    #: Unfiltered on purpose: `TenantFilterMixin` narrows it to this admin's
    #: tenant on every request. Overriding `get_queryset()` instead (as this
    #: viewset used to) skips that mixin entirely, because the override never
    #: calls `super()`, and the refund action then reached any tenant's payment.
    queryset = Payment.objects.unfiltered().select_related("appointment", "order", "customer")
    ordering = ("-created_at",)

    def filter_queryset(self, queryset: Any) -> Any:
        """`status`, `appointment_id`, `order_id`, and a `from`/`to` date range.

        The dashboard's payments table sends all four.
        """
        return queryset.filter(
            **_filter_params(
                self.request,
                choices={"status": {str(s) for s in PaymentOrderStatus.values}},
                uuids=("appointment_id", "order_id"),
                date_range=True,
            )
        )

    @action(detail=True, methods=["post"])
    def refund(self, request: Any, pk: Any = None) -> Response:
        """Create a `PENDING_ACTION` refund. Does **not** call the gateway.

        The lawyer issues the refund in the dashboard and a second action
        (`/admin/refunds/{id}/settle`) records it. One click here creates a
        recorded liability, not a refund (plan §6.2, D2).
        """
        payment = get_object_or_404(self.get_queryset(), pk=pk)
        body = RefundSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        amount = body.validated_data.get("amount") or payment.amount
        refund = services.request_refund(
            payment=payment,
            amount=amount,
            reason=str(body.validated_data.get("reason") or ""),
            requested_by=request.user,
        )
        audit(
            action="payment.refund_requested",
            entity_type="payments.refund",
            entity_id=refund.pk,
            after={
                "amount": str(refund.amount),
                "payment_id": str(payment.pk),
                "status": refund.status,
            },
            actor=request.user,
            tenant=refund.tenant,
        )
        return Response(RefundSerializer(refund).data, status=status.HTTP_201_CREATED)


class AdminRefundViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    TenantScopedViewSet,
):
    """Admin refund list plus `settle`, the only path to `Payment.REFUNDED`."""

    serializer_class = RefundSerializer
    authentication_classes: list[Any] = []  # noqa: RUF012 - DRF's own style
    permission_classes: list[Any] = [IsAdmin]  # noqa: RUF012 - DRF's own style
    #: See `AdminPaymentViewSet.queryset`: the tenant filter comes from
    #: `TenantFilterMixin`, which only runs if `get_queryset()` is not shadowed.
    queryset = Refund.objects.unfiltered().select_related("payment")
    ordering = ("-created_at",)

    def filter_queryset(self, queryset: Any) -> Any:
        return queryset.filter(
            **_filter_params(
                self.request,
                choices={"status": {str(s) for s in RefundStatus.values}},
                uuids=("payment_id",),
            )
        )

    @action(detail=True, methods=["post"])
    def settle(self, request: Any, pk: Any = None) -> Response:
        """Record that the refund was completed at the gateway."""
        refund = get_object_or_404(self.get_queryset(), pk=pk)
        body = SettleRefundSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        refund = services.settle_refund(
            refund=refund,
            gateway_refund_id=str(body.validated_data.get("gateway_refund_id") or ""),
            settled_by=request.user,
        )
        audit(
            action="payment.refund_settled",
            entity_type="payments.refund",
            entity_id=refund.pk,
            after={
                "amount": str(refund.amount),
                "payment_id": str(refund.payment_id),
                "status": refund.status,
            },
            actor=request.user,
            tenant=refund.tenant,
        )
        body_out = RefundSerializer(refund).data
        body_out["payment_status"] = refund.payment.status
        return Response(body_out)


class AdminPaymentEventViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    TenantScopedViewSet,
):
    """Webhook audit trail for troubleshooting (read-only, admin only).

    Exists because "why did this booking not confirm" is otherwise
    unanswerable, and the answer is almost always in `PaymentEvent.outcome`.

    Scoped to the admin's tenant even though `PaymentEvent` carries no
    `tenant_id`: it is joined back through `gateway_order_id`, which is unique
    across the whole table, against the orders this tenant owns. Rows with no
    matching order (an event for an order this practice never had) are withheld
    rather than shown - `payload` and `signature` are the gateway's own bytes,
    and one tenant reading another's is the leak S §A4 exists to prevent.
    """

    serializer_class = PaymentEventSerializer
    authentication_classes: list[Any] = []  # noqa: RUF012 - DRF's own style
    permission_classes: list[Any] = [IsAdmin]  # noqa: RUF012 - DRF's own style
    queryset = PaymentEvent.objects.all()

    # `super().get_queryset()` would filter on `tenant_id`, and PaymentEvent has
    # no such column - `filter()` would raise FieldError on every request. The
    # tenant scoping is done by hand in `get_queryset()` instead.
    tenant_queryset_override_reason = (
        "PaymentEvent has no tenant column; scoped through gateway_order_id, "
        "which is unique across the whole table, joined to this tenant's orders."
    )
    ordering = ("-received_at",)
    pagination_class = None

    def filter_queryset(self, queryset: Any) -> Any:
        # `gateway` and `event_type` are free-form gateway vocabulary, so they
        # are plain equality (an unknown one correctly yields an empty page).
        # `outcome` is ours, so a typo there is a 400 rather than a silent miss.
        return queryset.filter(
            **_filter_params(
                self.request,
                choices={"outcome": {str(o) for o in PaymentEventOutcome.values}},
            )
            | {
                name: request_value
                for name in ("gateway", "event_type")
                if (request_value := self.request.query_params.get(name))
            }
        )

    def get_queryset(self) -> Any:
        tenant = self.get_tenant()
        if tenant is None:
            return PaymentEvent.objects.none()
        order_ids = (
            PaymentOrder.objects.unfiltered()
            .filter(tenant_id=tenant.pk)
            .exclude(gateway_order_id="")
            .values_list("gateway_order_id", flat=True)
        )
        return (
            PaymentEvent.objects.all()
            .filter(gateway_order_id__in=order_ids)
            .order_by("-received_at")
        )


__all__ = (
    "AdminPaymentEventViewSet",
    "AdminPaymentViewSet",
    "AdminRefundViewSet",
    "CustomerPaymentViewSet",
    "PaymentViewSet",
    "PaymentWebhookView",
)
