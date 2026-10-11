from django.core.exceptions import PermissionDenied
from django.db.models import Q
from drf_spectacular.utils import extend_schema, extend_schema_field, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsManager, IsManagerOrProduction
from core.serializers import serializer_for

from . import services
from .exceptions import UnknownReference
from .models import Order, Payment, PurchaseOrder
from .serializers import OrderDetailSerializer, PaymentSerializer, PurchaseOrderDetailSerializer, RouteSerializer

PublicReportSchema = inline_serializer(
    "PublicReport",
    fields={
        "code": serializers.CharField(),
        "product": inline_serializer("PublicReportProduct", fields={"name": serializers.CharField(), "image": serializers.CharField(allow_null=True)}, allow_null=True),
        "quantity": serializers.CharField(),
        "committed_on": serializers.DateField(allow_null=True),
        "units_done": serializers.IntegerField(),
    },
)
PublicReportCreatedSchema = inline_serializer(
    "PublicReportCreated", fields={"id": serializers.IntegerField(), "units_done": serializers.IntegerField(), "reported_at": serializers.DateTimeField()}
)
RoutePairSchema = inline_serializer("RoutePair", fields={"current": RouteSerializer(allow_null=True), "replaced": RouteSerializer(allow_null=True)})


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
        """`?status=a,b` accepts a comma list; the other names are exact matches."""
        params = self.request.query_params
        for name in names:
            if params.get(name):
                values = [v for v in params[name].split(",") if v] if name == "status" else [params[name]]
                qs = qs.filter(**{f"{name}__in": values}) if len(values) > 1 else qs.filter(**{name: values[0]})
        return qs

    def detail_response(self, obj, http_status=status.HTTP_200_OK):
        cls = serializer_for(self.model, self.role, detail=True)
        return Response(cls(obj, context=self.get_serializer_context()).data, status=http_status)


def _forbidden(exc):
    raise DRFPermissionDenied(str(exc))


class OrderItemInSerializer(serializers.Serializer):
    product = serializers.CharField(required=False, allow_blank=True, allow_null=True, help_text="Product code; empty for a made-to-order item.")
    description = serializers.CharField(required=False, allow_blank=True, default="", help_text="Garment, colour, sizes, customizations when there is no product.")
    quantity = serializers.IntegerField(min_value=1)
    sizes = serializers.DictField(required=False)
    color = serializers.CharField(required=False, allow_blank=True)
    customization = serializers.CharField(required=False, allow_blank=True)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)


class OrderInSerializer(serializers.Serializer):
    """The simulated sales system payload (`docs/api/examples/order-*.json`)."""

    code = serializers.CharField(required=False, allow_blank=True, help_text="Optional: CP-YYYY-NNNN is generated when missing.")
    customer = serializers.CharField(help_text="Customer name.")
    brand = serializers.CharField(help_text="Brand name.")
    issued_on = serializers.DateField(required=False)
    promised_on = serializers.DateField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    items = OrderItemInSerializer(many=True)


class OrderPatchSerializer(serializers.Serializer):
    """The order form (ADR 0025 B): header fields and, when present, the full list of items."""

    customer = serializers.CharField(required=False)
    brand = serializers.CharField(required=False)
    issued_on = serializers.DateField(required=False)
    promised_on = serializers.DateField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)
    items = OrderItemInSerializer(many=True, required=False)


class CancelInSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


# Classification (ADR 0025 C): the proposal `classify` returns is what `apply-classification`
# takes back, edited by production, so both share these shapes (schema only: the view validates
# the request loosely and the service checks the references).
class ClassificationNewProductSerializer(serializers.Serializer):
    code = serializers.CharField(required=False, allow_blank=True)
    name = serializers.CharField()
    brand = serializers.CharField(required=False, allow_blank=True)


class ClassificationProductSerializer(serializers.Serializer):
    existing_id = serializers.IntegerField(required=False, allow_null=True, help_text="A catalogue product that fits; otherwise `new`.")
    code = serializers.CharField(required=False, allow_null=True)
    name = serializers.CharField(required=False, allow_null=True)
    new = ClassificationNewProductSerializer(required=False, allow_null=True)


class ClassificationNewMaterialSerializer(serializers.Serializer):
    sku = serializers.CharField(required=False, allow_blank=True)
    name = serializers.CharField()
    kind = serializers.CharField(required=False, help_text="A Material.Kind value.")
    unit = serializers.CharField(required=False, help_text="A Material.Unit value.")


class ClassificationMaterialSerializer(serializers.Serializer):
    sku = serializers.CharField(required=False, allow_null=True, help_text="A known material; otherwise `new`.")
    name = serializers.CharField(required=False, allow_null=True)
    material_id = serializers.IntegerField(required=False, allow_null=True)
    new = ClassificationNewMaterialSerializer(required=False, allow_null=True)
    qty_per_unit = serializers.CharField(help_text="Per garment, in `unit`, as a decimal string.")
    unit = serializers.CharField()
    confidence = serializers.FloatField(required=False)


class ClassificationItemSerializer(serializers.Serializer):
    item_id = serializers.IntegerField()
    description = serializers.CharField()
    product = ClassificationProductSerializer()
    confidence = serializers.FloatField()
    materials = ClassificationMaterialSerializer(many=True)


class ClassificationResultSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()
    items = ClassificationItemSerializer(many=True)


@extend_schema_field(ClassificationProductSerializer)
class ClassificationProductField(serializers.DictField):
    """Validated loosely (the service checks the references); documented as `ClassificationProduct`."""


@extend_schema_field(ClassificationMaterialSerializer)
class ClassificationMaterialField(serializers.DictField):
    """Documented as `ClassificationMaterial`."""


class ClassificationItemInSerializer(serializers.Serializer):
    item_id = serializers.IntegerField()
    product = ClassificationProductField(help_text="{existing_id} or {new: {code, name, brand}}")
    materials = serializers.ListField(child=ClassificationMaterialField(), required=False, default=list, help_text="[{sku} | {new: {sku, name, kind, unit}}, qty_per_unit, unit]")


class ApplyClassificationInSerializer(serializers.Serializer):
    items = ClassificationItemInSerializer(many=True)


class BreakDownInSerializer(serializers.Serializer):
    order_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)


BreakDownResultSchema = inline_serializer(
    "BreakDownResult",
    fields={
        "broken_down": serializers.ListField(child=serializers.CharField(), help_text="Order codes."),
        "skipped": inline_serializer("BreakDownSkipped", fields={"code": serializers.CharField(), "reason": serializers.CharField()}, many=True),
    },
)


class OrderViewSet(RoleSerializerMixin, viewsets.ReadOnlyModelViewSet):
    http_method_names = ["get", "post", "patch", "head", "options"]
    model = Order
    queryset = Order.objects.select_related("customer", "brand", "owner").prefetch_related(
        "items__product", "requirements__material", "requirements__product"
    )

    def get_queryset(self):
        qs = self.filter_exact(super().get_queryset(), "status", "risk", "code")
        params = self.request.query_params
        if params.get("brand"):
            qs = qs.filter(brand__name=params["brand"])
        if params.get("q"):
            qs = qs.filter(code__icontains=params["q"].strip())
        return qs

    @extend_schema(request=OrderInSerializer, responses={201: OrderDetailSerializer, 200: OrderDetailSerializer})
    def create(self, request):
        """Register an order (sales or manager). Idempotent by `code`: 201 when new, 200 when it existed."""
        data = OrderInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            order, created = services.register_order(data.validated_data, actor=request.user)
        except PermissionDenied as exc:
            _forbidden(exc)
        except UnknownReference as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return self.detail_response(order, status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @extend_schema(request=OrderPatchSerializer, responses={200: OrderDetailSerializer})
    def partial_update(self, request, pk=None):
        """Edit an order (sales: own, up to broken_down; manager: any). `items` replaces the
        list and re-breaks down; requirements already ordered stay and come back in `warnings`."""
        order = self.get_object()
        data = OrderPatchSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            order, warnings = services.update_order(order, data.validated_data, actor=request.user)
        except PermissionDenied as exc:
            _forbidden(exc)
        except UnknownReference as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        response = self.detail_response(order)
        response.data["warnings"] = warnings
        return response

    @extend_schema(request=CancelInSerializer, responses={200: OrderDetailSerializer})
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Sales cancels own orders up to broken_down; the manager any order before production."""
        data = CancelInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            order = services.cancel_order(self.get_object(), reason=data.validated_data.get("reason", ""), actor=request.user)
        except PermissionDenied as exc:
            _forbidden(exc)
        except UnknownReference as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return self.detail_response(order)

    @extend_schema(request=None, responses={200: ClassificationResultSerializer})
    @action(detail=True, methods=["post"], permission_classes=[IsManagerOrProduction])
    def classify(self, request, pk=None):
        """Proposal for every item without a catalogue product (Jev + Claude, ADR 0025 C):
        `{order_id, items: [{item_id, description, product: {existing_id, code, name} | {new: {code, name, brand}},
        confidence, materials: [{sku, name, material_id} | {new: {sku, name, kind, unit}}, qty_per_unit, unit, confidence]}]}`."""
        from . import classify as classifier

        try:
            return Response(classifier.classify_order(self.get_object(), actor=request.user))
        except PermissionDenied as exc:
            _forbidden(exc)
        except Exception as exc:  # The model or Jev failed: say so, never a 500 on the form.
            return Response({"detail": f"No se pudo clasificar: {exc}"[:300]}, status=status.HTTP_502_BAD_GATEWAY)

    @extend_schema(request=ApplyClassificationInSerializer, responses={200: OrderDetailSerializer})
    @action(detail=True, methods=["post"], url_path="apply-classification", permission_classes=[IsManagerOrProduction])
    def apply_classification(self, request, pk=None):
        """What production confirmed: creates products, materials and bills of materials, assigns
        them to the items and breaks the order down again (`warnings` lists what was skipped)."""
        from . import classify as classifier

        data = ApplyClassificationInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            order, warnings = classifier.apply_classification(self.get_object(), data.validated_data["items"], actor=request.user)
        except PermissionDenied as exc:
            _forbidden(exc)
        except UnknownReference as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        response = self.detail_response(order)
        response.data["warnings"] = warnings
        return response

    @extend_schema(request=BreakDownInSerializer, responses={200: BreakDownResultSchema})
    @action(detail=False, methods=["post"], url_path="break-down", permission_classes=[IsManagerOrProduction])
    def break_down(self, request):
        """Breaks down every `registered` order (or `order_ids`) against the inventory."""
        data = BreakDownInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            result = services.break_down_orders(data.validated_data.get("order_ids") or None, actor=request.user)
        except PermissionDenied as exc:
            _forbidden(exc)
        return Response(result)

    @extend_schema(request=None, responses={200: OrderDetailSerializer})
    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        """Production confirms the breakdown; the matching proposes suppliers."""
        order = self.get_object()
        try:
            order = services.confirm_order(order, actor=request.user)
        except PermissionDenied as exc:
            _forbidden(exc)
        except UnknownReference as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return self.detail_response(order)


class GenerateInSerializer(serializers.Serializer):
    material_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    supplier_overrides = serializers.DictField(child=serializers.IntegerField(), required=False, default=dict)


GenerateResultSchema = inline_serializer(
    "GenerateResult",
    fields={
        "created": PurchaseOrderDetailSerializer(many=True),
        "decision_id": serializers.IntegerField(allow_null=True),
        "skipped": inline_serializer("GenerateSkipped", fields={"material_id": serializers.IntegerField(), "reason": serializers.CharField()}, many=True),
    },
)


class SupplierNameRefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class PendingPurchaseSerializer(serializers.Serializer):
    material = inline_serializer(
        "PendingPurchaseMaterial",
        fields={
            "id": serializers.IntegerField(),
            "sku": serializers.CharField(),
            "name": serializers.CharField(),
            "kind": serializers.CharField(),
            "unit": serializers.CharField(),
            "image": serializers.CharField(allow_null=True),
        },
    )
    total_to_order = serializers.CharField(help_text="Still to buy across the orders, as a decimal string.")
    orders = inline_serializer(
        "PendingPurchaseOrder",
        fields={
            "id": serializers.IntegerField(),
            "code": serializers.CharField(),
            "customer_name": serializers.CharField(),
            "qty": serializers.CharField(),
            "due_on": serializers.DateField(),
        },
        many=True,
    )
    due_on = serializers.DateField(allow_null=True)
    suggested_supplier = SupplierNameRefSerializer(allow_null=True)
    candidates = inline_serializer(
        "PendingPurchaseCandidate",
        fields={"supplier": SupplierNameRefSerializer(), "unit_price": serializers.CharField(), "currency": serializers.CharField(), "score": serializers.FloatField()},
        many=True,
    )
    lead_time_days = serializers.IntegerField(allow_null=True)
    reference_price = serializers.CharField(allow_null=True, help_text="Manager only; null for production.")
    currency = serializers.CharField(allow_null=True)
    alert_id = serializers.IntegerField(allow_null=True)


class PendingPurchasesView(APIView):
    """`GET /api/requirements/pending/`: open material requirements grouped by material, the
    "Por pedir" screen (ADR 0025 A). Manager and production; prices only for the manager."""

    permission_classes = [IsManagerOrProduction]

    @extend_schema(responses={200: PendingPurchaseSerializer(many=True)})
    def get(self, request):
        raw = request.query_params.get("material_ids", "")
        material_ids = [int(x) for x in raw.split(",") if x.strip().isdigit()] or None
        return Response(services.pending_purchases(with_prices=request.user.role == "manager", material_ids=material_ids))


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
        if params.get("q"):
            text = params["q"].strip()
            qs = qs.filter(Q(code__icontains=text) | Q(items__requirement__order__code__icontains=text)).distinct()
        return qs

    @extend_schema(request=GenerateInSerializer, responses={201: GenerateResultSchema})
    @action(detail=False, methods=["post"], permission_classes=[IsManagerOrProduction])
    def generate(self, request):
        """Consolidated material purchase orders for every open requirement (or `material_ids`):
        one per material with an item per requirement, plus the assignment decision."""
        data = GenerateInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            result = services.generate_purchase_orders(
                data.validated_data.get("material_ids") or None, actor=request.user, supplier_overrides=data.validated_data.get("supplier_overrides") or None
            )
        except PermissionDenied as exc:
            _forbidden(exc)
        except UnknownReference as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        cls = serializer_for(PurchaseOrder, self.role, detail=True)
        return Response(
            {
                "created": cls(result["created"], many=True, context=self.get_serializer_context()).data,
                "decision_id": result["decision"].id if result["decision"] else None,
                "skipped": result["skipped"],
            },
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(request=ProgressInSerializer, responses={201: PurchaseOrderDetailSerializer})
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

    @extend_schema(request=DeliveryInSerializer, responses={201: PurchaseOrderDetailSerializer})
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

    @extend_schema(request=PayInSerializer, responses={200: PaymentSerializer})
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

    @extend_schema(responses={200: PublicReportSchema})
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

    @extend_schema(request=PublicReportInSerializer, responses={201: PublicReportCreatedSchema})
    def post(self, request, token):
        if self._po(token) is None:
            return Response(status=404)
        data = PublicReportInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        report = services.record_public_report(token, **data.validated_data)
        return Response({"id": report.id, "units_done": report.units_done, "reported_at": report.reported_at}, status=201)


class RoutePlanInSerializer(serializers.Serializer):
    date = serializers.DateField()


ROUTE_PREFETCH = ("stops__supplier", "stops__customer", "stops__purchase_order", "stops__order__items")


def route_queryset():
    from .models import Route

    return Route.objects.select_related("vehicle", "recalculated_from").prefetch_related(*ROUTE_PREFETCH)


class RouteListView(APIView):
    """`GET /api/routes/`: all routes (`?date=`, `?status=a,b`; `?fleet=1` only the vehicles'
    trips, `?vehicle_ids=1,2`), or with `?current=1` the pair `{current, replaced}` the map shows
    (ADR 0024)."""

    @extend_schema(responses={200: RoutePairSchema})
    def get(self, request):
        from . import routes
        from .serializers import RouteSerializer

        params = request.query_params
        qs = route_queryset()
        if params.get("current") == "1":
            current = routes.current_route(params.get("date") or None)
            replaced = current.recalculated_from if current and current.recalculated_from_id and current.recalculated_from.status == "replaced" else None
            return Response(
                {
                    "current": RouteSerializer(qs.get(pk=current.pk)).data if current else None,
                    "replaced": RouteSerializer(qs.get(pk=replaced.pk)).data if replaced else None,
                }
            )
        if params.get("date"):
            qs = qs.filter(date=params["date"])
        if params.get("status"):
            qs = qs.filter(status__in=params["status"].split(","))
        if params.get("fleet") == "1":
            qs = qs.filter(vehicle__isnull=False)
        if params.get("vehicle_ids"):
            qs = qs.filter(vehicle_id__in=[int(v) for v in params["vehicle_ids"].split(",") if v.isdigit()])
        return Response(RouteSerializer(qs, many=True).data)


class RouteDetailView(APIView):
    """Any route in any status: the scene opens `before` and `after` side by side."""

    @extend_schema(responses={200: RouteSerializer})
    def get(self, request, pk: int):
        from .serializers import RouteSerializer

        route = route_queryset().filter(pk=pk).first()
        if route is None:
            return Response(status=404)
        return Response(RouteSerializer(route).data)


class RoutePlanView(APIView):
    """`POST /api/routes/plan/ {date}` (manager and production): plans or re-plans that day."""

    permission_classes = [IsManagerOrProduction]

    @extend_schema(request=RoutePlanInSerializer, responses={201: RouteSerializer})
    def post(self, request):
        from . import routes
        from .serializers import RouteSerializer

        data = RoutePlanInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        route = routes.plan_route(data.validated_data["date"], actor=request.user)
        if route is None:
            return Response({"detail": "La planta no tiene coordenadas (Config.plant_lat/plant_lng)."}, status=400)
        return Response(RouteSerializer(route).data, status=201)
