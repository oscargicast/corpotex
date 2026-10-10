from django.core.exceptions import PermissionDenied
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsManager
from core.serializers import serializer_for

from . import services
from .models import Order, Payment, PurchaseOrder


class RoleSerializerMixin:
    model = None

    @property
    def role(self) -> str | None:
        if getattr(self, "swagger_fake_view", False):
            return "manager"  # The schema documents the full shape.
        return getattr(self.request.user, "role", None)

    def get_serializer_class(self):
        return serializer_for(self.model, self.role, detail=self.action != "list")

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "role": self.role}

    def filter_exact(self, qs, *names):
        params = self.request.query_params
        for name in names:
            if params.get(name):
                qs = qs.filter(**{name: params[name]})
        return qs

    def detail_response(self, obj, http_status=status.HTTP_200_OK):
        cls = serializer_for(self.model, self.role, detail=True)
        return Response(cls(obj, context=self.get_serializer_context()).data, status=http_status)


def _forbidden(exc):
    raise DRFPermissionDenied(str(exc))


class OrderItemInSerializer(serializers.Serializer):
    product = serializers.CharField(help_text="Product code.")
    quantity = serializers.IntegerField(min_value=1)
    sizes = serializers.DictField(required=False)
    color = serializers.CharField(required=False, allow_blank=True)
    customization = serializers.CharField(required=False, allow_blank=True)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2)


class OrderInSerializer(serializers.Serializer):
    """The simulated sales system payload (`docs/api/examples/order-*.json`)."""

    code = serializers.CharField()
    customer = serializers.CharField(help_text="Customer name.")
    brand = serializers.CharField(help_text="Brand name.")
    issued_on = serializers.DateField(required=False)
    promised_on = serializers.DateField()
    items = OrderItemInSerializer(many=True)


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

    @extend_schema(request=OrderInSerializer, responses={201: dict, 200: dict})
    def create(self, request):
        """Register an order (sales or manager). Idempotent by `code`: 201 when new, 200 when it existed."""
        data = OrderInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            order, created = services.register_order(data.validated_data, actor=request.user)
        except PermissionDenied as exc:
            _forbidden(exc)
        return self.detail_response(order, status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @extend_schema(request=None, responses={200: dict})
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        """Production confirms the breakdown; the matching proposes suppliers."""
        order = self.get_object()
        try:
            order = services.confirm_order(order, actor=request.user)
        except PermissionDenied as exc:
            _forbidden(exc)
        return self.detail_response(order)


class ProgressInSerializer(serializers.Serializer):
    units_done = serializers.IntegerField(min_value=0)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    photo = serializers.ImageField(required=False)


class DeliveryInSerializer(serializers.Serializer):
    qty_received = serializers.DecimalField(max_digits=12, decimal_places=2)
    qty_defective = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=0)
    quality = serializers.IntegerField(min_value=1, max_value=5, default=5)
    note = serializers.CharField(required=False, allow_blank=True, default="")


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

    @extend_schema(request=ProgressInSerializer, responses={201: dict})
    @action(detail=True, methods=["post"])
    def progress(self, request, pk=None):
        po = self.get_object()
        data = ProgressInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            services.record_progress(po, actor=request.user, **data.validated_data)
        except PermissionDenied as exc:
            _forbidden(exc)
        po.refresh_from_db()
        return self.detail_response(po, status.HTTP_201_CREATED)

    @extend_schema(request=DeliveryInSerializer, responses={201: dict})
    @action(detail=True, methods=["post"])
    def deliveries(self, request, pk=None):
        po = self.get_object()
        data = DeliveryInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            services.record_delivery(po, actor=request.user, **data.validated_data)
        except PermissionDenied as exc:
            _forbidden(exc)
        po.refresh_from_db()
        return self.detail_response(po, status.HTTP_201_CREATED)


class PayInSerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=Payment.Method.choices)
    receipt = serializers.FileField(required=False)


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
        status_param = self.request.query_params.get("status")
        if status_param == "pending":
            qs = qs.filter(paid_at__isnull=True)
        elif status_param == "paid":
            qs = qs.filter(paid_at__isnull=False)
        return qs

    @extend_schema(request=PayInSerializer, responses={200: dict})
    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        payment = self.get_object()
        data = PayInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        payment = services.mark_payment_paid(payment, actor=request.user, **data.validated_data)
        return Response(serializer_for(Payment, "manager")(payment, context={"role": "manager"}).data)


class PublicReportInSerializer(serializers.Serializer):
    units_done = serializers.IntegerField(min_value=0)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    photo = serializers.ImageField(required=False)


class PublicReportView(APIView):
    """The workshop's public page (`/report/<token>`): no login, the token is the secret.
    Never prices nor the supplier (ADR 0024 C)."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def _po(self, token):
        return (
            PurchaseOrder.objects.select_related("supplier")
            .prefetch_related("items__requirement__product", "progress_reports")
            .filter(report_token=token)
            .first()
        )

    @extend_schema(responses={200: dict})
    def get(self, request, token):
        po = self._po(token)
        if po is None:
            return Response(status=404)
        item = po.items.first()
        product = item.requirement.product if item else None
        latest = po.progress_reports.order_by("-reported_at").first()
        return Response(
            {
                "code": po.code,
                "product": {"name": product.name, "image": product.image.url if product.image else None} if product else None,
                "quantity": str(sum((i.quantity for i in po.items.all()), 0)),
                "committed_on": po.committed_on,
                "units_done": latest.units_done if latest else 0,
            }
        )

    @extend_schema(request=PublicReportInSerializer, responses={201: dict})
    def post(self, request, token):
        if self._po(token) is None:
            return Response(status=404)
        data = PublicReportInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        report = services.record_public_report(token, **data.validated_data)
        return Response({"id": report.id, "units_done": report.units_done, "reported_at": report.reported_at}, status=201)
