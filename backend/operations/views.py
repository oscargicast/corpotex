from rest_framework import viewsets

from core.permissions import IsManager
from core.serializers import serializer_for

from .models import Order, Payment, PurchaseOrder


class RoleSerializerMixin:
    model = None

    @property
    def role(self) -> str | None:
        if getattr(self, "swagger_fake_view", False):
            return "manager"  # The schema documents the full shape.
        return getattr(self.request.user, "role", None)

    def get_serializer_class(self):
        return serializer_for(self.model, self.role, detail=self.action == "retrieve")

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "role": self.role}

    def filter_exact(self, qs, *names):
        params = self.request.query_params
        for name in names:
            if params.get(name):
                qs = qs.filter(**{name: params[name]})
        return qs


class OrderViewSet(RoleSerializerMixin, viewsets.ReadOnlyModelViewSet):
    model = Order
    queryset = Order.objects.select_related("customer", "brand", "owner").prefetch_related(
        "items__product", "requirements__material", "requirements__product"
    )

    def get_queryset(self):
        qs = self.filter_exact(super().get_queryset(), "status", "risk", "code")
        if self.request.query_params.get("brand"):
            qs = qs.filter(brand__name=self.request.query_params["brand"])
        return qs


class PurchaseOrderViewSet(RoleSerializerMixin, viewsets.ReadOnlyModelViewSet):
    model = PurchaseOrder
    queryset = PurchaseOrder.objects.select_related("supplier", "suggested_supplier", "redistributed_from").prefetch_related(
        "items__requirement__order__customer", "progress_reports", "payments", "alerts", "decisions"
    )

    def get_queryset(self):
        qs = self.filter_exact(super().get_queryset(), "status", "code")
        params = self.request.query_params
        if params.get("kind"):
            qs = qs.filter(supplier__kind=params["kind"])
        if params.get("supplier"):
            qs = qs.filter(supplier_id=params["supplier"])
        if params.get("order"):
            qs = qs.filter(items__requirement__order_id=params["order"]).distinct()
        if params.get("waiting_manager") == "1":
            qs = qs.filter(decisions__status="pending").distinct()
        return qs


class PaymentViewSet(RoleSerializerMixin, viewsets.ReadOnlyModelViewSet):
    model = Payment
    permission_classes = [IsManager]
    queryset = Payment.objects.select_related("purchase_order__supplier").order_by("-id")

    def get_serializer_class(self):
        return serializer_for(Payment, "manager")

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "role": "manager"}

    def get_queryset(self):
        qs = super().get_queryset()
        status = self.request.query_params.get("status")
        if status == "pending":
            qs = qs.filter(paid_at__isnull=True)
        elif status == "paid":
            qs = qs.filter(paid_at__isnull=False)
        return qs
