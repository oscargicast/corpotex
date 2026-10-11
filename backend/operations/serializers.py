from decimal import Decimal

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field, inline_serializer
from rest_framework import serializers

from core.models import Customer, Brand, Material, Product
from core.serializers import DisplayMixin, RelativeFileField, register
from suppliers.serializers import SupplierRefSerializer

from .models import (
    Order,
    OrderItem,
    Payment,
    ProgressReport,
    PurchaseOrder,
    PurchaseOrderItem,
    Requirement,
    Route,
    RouteStop,
)

OPEN = PurchaseOrder.OPEN_STATUSES

# Schemas of the computed lists (drf-spectacular only; the data is built by hand below).

class StatusChangeSerializer(serializers.Serializer):
    status = serializers.CharField()
    status_display = serializers.CharField()
    at = serializers.DateTimeField()
    actor = serializers.CharField()
    note = serializers.CharField(allow_blank=True)

class RequirementPurchaseOrderSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    supplier_name = serializers.CharField()
    quantity = serializers.CharField()
    status = serializers.CharField()

class OrderRefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    customer_name = serializers.CharField()

class RedistributedIntoSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    supplier_name = serializers.CharField()
    quantity = serializers.CharField()
    status = serializers.CharField()


def money(value) -> str:
    """Computed amounts as strings with two decimals, like DRF's DecimalField."""
    return str(Decimal(value).quantize(Decimal("0.01")))


def _ref(obj, *fields):
    return {"id": obj.id, **{f: getattr(obj, f) for f in fields}} if obj else None


def _image(obj):
    return obj.image.url if obj and obj.image else None


class ProductRefSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["id", "code", "name", "image"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_image(self, obj):
        return _image(obj)


class MaterialRefSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()

    class Meta:
        model = Material
        fields = ["id", "sku", "name", "unit", "image"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_image(self, obj):
        return _image(obj)


class OrderItemSerializer(DisplayMixin, serializers.ModelSerializer):
    product = ProductRefSerializer(read_only=True, allow_null=True)
    photo_url = RelativeFileField(source="photo", read_only=True, allow_null=True, help_text="`/media/items/...`; null without a photo (ADR 0029 N1).")

    class Meta:
        model = OrderItem
        fields = ["id", "product", "description", "quantity", "sizes", "color", "customization", "unit_price", "photo_url"]


class RequirementSerializer(DisplayMixin, serializers.ModelSerializer):
    material = MaterialRefSerializer(read_only=True)
    product = ProductRefSerializer(read_only=True)
    qty_to_order = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    purchase_orders = serializers.SerializerMethodField()

    class Meta:
        model = Requirement
        display_fields = ["kind", "status"]
        fields = [
            "id",
            "kind",
            "material",
            "product",
            "qty_needed",
            "qty_from_stock",
            "qty_to_order",
            "status",
            "purchase_orders",
        ]

    def _items(self, obj):
        return obj.purchase_order_items.select_related("purchase_order__supplier")

    @extend_schema_field(RequirementPurchaseOrderSerializer(many=True))
    def get_purchase_orders(self, obj):
        return [
            {
                "id": i.purchase_order_id,
                "code": i.purchase_order.code,
                "supplier_name": i.purchase_order.supplier.name,
                "quantity": money(i.quantity),
                "status": i.purchase_order.status,
            }
            for i in self._items(obj)
        ]



class StatusHistoryMixin(serializers.Serializer):
    """`status_history: [{status, status_display, at, actor, note}]` ordered by `at` (10/10 21:40)."""

    status_history = serializers.SerializerMethodField()

    @extend_schema_field(StatusChangeSerializer(many=True))
    def get_status_history(self, obj):
        return [
            {"status": c.status, "status_display": c.status_display, "at": c.at, "actor": c.actor or "system", "note": c.note}
            for c in obj.status_changes.all()
        ]


@register(Order)
class OrderListSerializer(DisplayMixin, serializers.ModelSerializer):
    customer = serializers.SerializerMethodField()
    brand = serializers.SerializerMethodField()
    slack_days = serializers.SerializerMethodField()
    total_units = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()
    purchase_orders_summary = serializers.SerializerMethodField()
    awaiting_reply = serializers.SerializerMethodField()

    class Meta:
        model = Order
        display_fields = ["status", "production_stage", "risk"]
        fields = [
            "id",
            "code",
            "customer",
            "brand",
            "status",
            "production_stage",
            "risk",
            "risk_reason",
            "issued_on",
            "promised_on",
            "estimated_on",
            "slack_days",
            "total_units",
            "total_amount",
            "purchase_orders_summary",
            "awaiting_reply",
            "owner_id",
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_customer(self, obj):
        return _ref(obj.customer, "name")

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_brand(self, obj):
        return _ref(obj.brand, "name")

    @extend_schema_field(OpenApiTypes.INT)
    def get_slack_days(self, obj):
        return (obj.promised_on - obj.estimated_on).days if obj.estimated_on else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_total_units(self, obj):
        return sum(i.quantity for i in obj.items.all())

    @extend_schema_field(OpenApiTypes.STR)
    def get_total_amount(self, obj):
        return money(sum((i.quantity * i.unit_price for i in obj.items.all() if i.unit_price is not None), Decimal("0")))

    def _purchase_orders(self, obj):
        return PurchaseOrder.objects.filter(items__requirement__order=obj).distinct()

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_purchase_orders_summary(self, obj):
        pos = list(self._purchase_orders(obj))
        return {
            "total": len(pos),
            "confirmed": sum(1 for po in pos if po.status in ("confirmed", "in_progress", "delivered")),
            "waiting_manager": sum(1 for po in pos if waiting_manager(po)),
        }


    @extend_schema_field(OpenApiTypes.BOOL)
    def get_awaiting_reply(self, obj):
        """P6b, the "Avance pedido" chip: some open purchase order of the order waits for the
        supplier's answer (a follow-up sent, or a person's request already asked)."""
        from .models import FollowUpRequest

        open_pos = [po for po in self._purchase_orders(obj) if po.status in PurchaseOrder.OPEN_STATUSES]
        if any(po.awaiting_reply_since for po in open_pos):
            return True
        return FollowUpRequest.objects.filter(purchase_order__in=open_pos, status=FollowUpRequest.Status.ASKED).exists()


def waiting_manager(po: PurchaseOrder) -> bool:
    return po.decisions.filter(status="pending").exists()


@register(Order, detail=True)
class OrderDetailSerializer(StatusHistoryMixin, OrderListSerializer):
    owner = serializers.SerializerMethodField()
    items = OrderItemSerializer(many=True, read_only=True)
    requirements = RequirementSerializer(many=True, read_only=True)
    purchase_orders = serializers.SerializerMethodField()
    alerts = serializers.SerializerMethodField()
    redistributions = serializers.SerializerMethodField()

    class Meta(OrderListSerializer.Meta):
        role_visible = ("notes",)  # The order's own notes are for every role; supplier notes stay manager-only.
        fields = OrderListSerializer.Meta.fields + [
            "owner",
            "notes",
            "needs_classification",
            "critical_path",
            "stage_overrides",
            "items",
            "requirements",
            "purchase_orders",
            "alerts",
            "redistributions",
            "status_history",
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_owner(self, obj):
        return _ref(obj.owner, "username", "first_name")

    @extend_schema_field({"type": "array", "items": {"$ref": "#/components/schemas/PurchaseOrderList"}})
    def get_purchase_orders(self, obj):
        role = self.context.get("role")
        from core.serializers import serializer_for

        cls = serializer_for(PurchaseOrder, role)
        return cls(self._purchase_orders(obj), many=True, context=self.context).data

    @extend_schema_field({"type": "array", "items": {"$ref": "#/components/schemas/Alert"}})
    def get_alerts(self, obj):
        from manager.serializers import AlertSerializer

        return AlertSerializer(obj.alerts.filter(status="open"), many=True, context=self.context).data

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_redistributions(self, obj):
        from core.serializers import serializer_for
        from manager.models import Decision

        decisions = (
            Decision.objects.filter(
                kind="approve_assignment",
                purchase_orders__items__requirement__order=obj,
                purchase_orders__redistributed_from__isnull=False,
            )
            .exclude(status="pending")
            .distinct()
            .order_by("-id")[:3]
        )
        cls = serializer_for(Decision, self.context.get("role"))
        return cls(decisions, many=True, context=self.context).data


class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    requirement = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    order_code = serializers.CharField(source="requirement.order.code", read_only=True)

    class Meta:
        model = PurchaseOrderItem
        fields = ["id", "requirement", "name", "image", "order_code", "quantity", "unit_price", "qty_delivered"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_name(self, obj):
        item = obj.requirement.material or obj.requirement.product
        return item.name if item else obj.requirement.get_kind_display()

    @extend_schema_field(OpenApiTypes.STR)
    def get_image(self, obj):
        return _image(obj.requirement.material or obj.requirement.product)

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_requirement(self, obj):
        req = obj.requirement
        return {
            "id": req.id,
            "kind": req.kind,
            "order": {"id": req.order_id, "code": req.order.code},
            "material": MaterialRefSerializer(req.material).data if req.material_id else None,
            "product": ProductRefSerializer(req.product).data if req.product_id else None,
        }


class ProgressReportSerializer(serializers.ModelSerializer):
    photo = serializers.SerializerMethodField()
    source = serializers.CharField(read_only=True)

    class Meta:
        model = ProgressReport
        fields = ["id", "units_done", "note", "photo", "source", "reported_at"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_photo(self, obj):
        """Its own photo, else the image of its WhatsApp or simulator message (reports saved
        before the agent's photos were linked)."""
        from .services import image_name

        if obj.photo:
            return obj.photo.url
        media = obj.message.media if obj.message_id and obj.message else None
        return media.url if media and image_name(media) else None


@register(Payment)
class PaymentSerializer(DisplayMixin, serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    status_display = serializers.SerializerMethodField()
    due_on = serializers.DateField(read_only=True)
    receipt = serializers.SerializerMethodField()
    purchase_order = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        display_fields = ["kind", "method"]
        fields = [
            "id",
            "purchase_order",
            "kind",
            "amount",
            "status",
            "status_display",
            "due_on",
            "paid_at",
            "method",
            "receipt",
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_status_display(self, obj):
        return "Pagado" if obj.paid_at else "Pendiente"

    @extend_schema_field(OpenApiTypes.STR)
    def get_receipt(self, obj):
        return obj.receipt.url if obj.receipt else None

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_purchase_order(self, obj):
        return {"id": obj.purchase_order_id, "code": obj.purchase_order.code, "supplier_name": obj.purchase_order.supplier.name}


class PendingFollowUpSerializer(serializers.Serializer):
    """Schema of `pending_follow_up` (ADR 0027 §6)."""

    requested_by_role = serializers.CharField(allow_null=True)
    requested_by_role_display = serializers.CharField()
    requested_at = serializers.DateTimeField()
    status = serializers.ChoiceField(choices=[("pending", "Pendiente"), ("asked", "Preguntado"), ("answered", "Respondido"), ("skipped", "Sin respuesta")])
    asked_at = serializers.DateTimeField(allow_null=True)
    answered_at = serializers.DateTimeField(allow_null=True)
    answer_summary = serializers.CharField(allow_null=True)


class LastFollowUpSerializer(serializers.Serializer):
    kind = serializers.CharField(help_text="checkpoint, reminder or requested")
    at = serializers.DateTimeField()
    awaiting_reply = serializers.BooleanField()


@register(PurchaseOrder)
class PurchaseOrderListSerializer(DisplayMixin, serializers.ModelSerializer):
    kind = serializers.CharField(read_only=True)
    material = serializers.SerializerMethodField()
    kind_display = serializers.CharField(source="supplier.get_kind_display", read_only=True)
    waiting_manager = serializers.SerializerMethodField()
    supplier = SupplierRefSerializer(read_only=True)
    orders = serializers.SerializerMethodField()
    total_units = serializers.SerializerMethodField()
    units_done = serializers.SerializerMethodField()
    progress_pct = serializers.SerializerMethodField()
    last_progress_at = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()
    currency = serializers.CharField(source="supplier.currency", read_only=True)
    redistributed_from = serializers.SerializerMethodField()
    alert_severity = serializers.SerializerMethodField()
    awaiting_reply = serializers.SerializerMethodField()
    pending_follow_up = serializers.SerializerMethodField()
    last_follow_up = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrder
        display_fields = ["status"]
        fields = [
            "id",
            "code",
            "kind",
            "kind_display",
            "status",
            "waiting_manager",
            "supplier",
            "orders",
            "material",
            "total_units",
            "units_done",
            "progress_pct",
            "internal_due_on",
            "committed_on",
            "last_progress_at",
            "next_follow_up_at",
            "awaiting_reply",
            "pending_follow_up",
            "last_follow_up",
            "total_amount",
            "currency",
            "redistributed_from",
            "alert_severity",
        ]

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_waiting_manager(self, obj):
        return waiting_manager(obj)

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_material(self, obj):
        """The material of a consolidated purchase order (all its items share it); null for workshops."""
        item = obj.items.select_related("requirement__material").first()
        material = item.requirement.material if item else None
        return {"id": material.id, "sku": material.sku, "name": material.name} if material else None

    @extend_schema_field(OrderRefSerializer(many=True))
    def get_orders(self, obj):
        seen = {}
        for item in obj.items.select_related("requirement__order__customer"):
            order = item.requirement.order
            seen[order.id] = {"id": order.id, "code": order.code, "customer_name": order.customer.name}
        return list(seen.values())

    @extend_schema_field(OpenApiTypes.STR)
    def get_total_units(self, obj):
        return money(sum((i.quantity for i in obj.items.all()), Decimal("0")))

    def _latest_progress(self, obj):
        return obj.progress_reports.order_by("-reported_at", "-id").first()

    @extend_schema_field(OpenApiTypes.INT)
    def get_units_done(self, obj):
        latest = self._latest_progress(obj)
        return latest.units_done if latest else 0

    @extend_schema_field(OpenApiTypes.FLOAT)
    def get_progress_pct(self, obj):
        total = Decimal(self.get_total_units(obj))
        if not total:
            return 0
        return round(float(self.get_units_done(obj)) / float(total) * 100, 1)

    @extend_schema_field(OpenApiTypes.DATETIME)
    def get_last_progress_at(self, obj):
        latest = self._latest_progress(obj)
        return latest.reported_at if latest else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_total_amount(self, obj):
        return money(sum((i.quantity * i.unit_price for i in obj.items.all() if i.unit_price is not None), Decimal("0")))

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_redistributed_from(self, obj):
        return _ref(obj.redistributed_from, "code")

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_awaiting_reply(self, obj) -> bool:
        return obj.awaiting_reply_since is not None

    @extend_schema_field(PendingFollowUpSerializer(allow_null=True))
    def get_pending_follow_up(self, obj):
        """The latest progress request (ADR 0027 §6), with the answer once there is one."""
        from .follow_up_requests import pending_follow_up

        return pending_follow_up(obj)

    @extend_schema_field(LastFollowUpSerializer(allow_null=True))
    def get_last_follow_up(self, obj):
        from .follow_up_requests import last_follow_up

        return last_follow_up(obj)

    @extend_schema_field(OpenApiTypes.STR)
    def get_alert_severity(self, obj):
        alert = obj.alerts.filter(status="open").order_by("-severity").first()
        return alert.severity if alert else None


@register(PurchaseOrder, detail=True)
class PurchaseOrderDetailSerializer(StatusHistoryMixin, PurchaseOrderListSerializer):
    suggested_supplier = SupplierRefSerializer(read_only=True)
    report_url = serializers.SerializerMethodField()
    changed_by_manager = serializers.SerializerMethodField()
    candidates = serializers.SerializerMethodField()
    delivered_on = serializers.SerializerMethodField()
    items = PurchaseOrderItemSerializer(many=True, read_only=True)
    progress_reports = ProgressReportSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)
    paid_amount = serializers.SerializerMethodField()
    pending_amount = serializers.SerializerMethodField()
    redistributed_into = serializers.SerializerMethodField()
    pending_decision = serializers.SerializerMethodField()

    class Meta(PurchaseOrderListSerializer.Meta):
        fields = PurchaseOrderListSerializer.Meta.fields + [
            "suggested_supplier",
            "changed_by_manager",
            "rationale",
            "scores",
            "candidates",
            "terms",
            "delivered_on",
            "items",
            "progress_reports",
            "payments",
            "paid_amount",
            "pending_amount",
            "redistributed_into",
            "pending_decision",
            "conversation_id",
            "report_token",
            "report_url",
            "status_history",
        ]

    @extend_schema_field(OpenApiTypes.STR)
    def get_report_url(self, obj):
        from .services import report_url

        return report_url(obj)

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_changed_by_manager(self, obj):
        return bool(obj.suggested_supplier_id and obj.suggested_supplier_id != obj.supplier_id)

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_candidates(self, obj):
        """The full ranking lives in the assignment decision's `detail.proposal`."""
        decision = obj.decisions.filter(kind="approve_assignment").order_by("-id").first()
        if not decision:
            return []
        for entry in decision.detail.get("proposal", []):
            po = entry.get("purchase_order") or {}
            if po.get("code") == obj.code or entry.get("purchase_order_code") == obj.code:
                return entry.get("candidates", [])
        return []

    @extend_schema_field(OpenApiTypes.DATE)
    def get_delivered_on(self, obj):
        delivery = obj.deliveries.order_by("-received_at").first()
        return delivery.received_at.date() if delivery else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_paid_amount(self, obj):
        return money(sum((p.amount for p in obj.payments.all() if p.paid_at), Decimal("0")))

    @extend_schema_field(OpenApiTypes.STR)
    def get_pending_amount(self, obj):
        return money(sum((p.amount for p in obj.payments.all() if not p.paid_at), Decimal("0")))

    @extend_schema_field(RedistributedIntoSerializer(many=True))
    def get_redistributed_into(self, obj):
        return [
            {
                "id": po.id,
                "code": po.code,
                "supplier_name": po.supplier.name,
                "quantity": money(sum((i.quantity for i in po.items.all()), Decimal("0"))),
                "status": po.status,
            }
            for po in obj.redistributed_into.select_related("supplier")
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_pending_decision(self, obj):
        decision = obj.decisions.filter(status="pending").order_by("-id").first()
        if not decision:
            return None
        return {"id": decision.id, "kind": decision.kind, "summary": decision.summary, "detail": decision.detail}


def local_date(value):
    from django.utils import timezone

    return timezone.localtime(value).date() if value else None


class RouteStopSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    supplier = serializers.SerializerMethodField()
    customer = serializers.SerializerMethodField()
    purchase_order = serializers.SerializerMethodField()
    order = serializers.SerializerMethodField()
    units = serializers.SerializerMethodField()
    on_time = serializers.SerializerMethodField()

    class Meta:
        model = RouteStop
        fields = [
            "id", "position", "kind", "kind_display", "name", "address", "lat", "lng", "eta", "delivered_at",
            "supplier", "customer", "purchase_order", "order", "units", "on_time",
        ]

    @extend_schema_field(OpenApiTypes.INT)
    def get_units(self, obj):
        return sum(i.quantity for i in obj.order.items.all()) if obj.order_id else 0

    @extend_schema_field(serializers.BooleanField(allow_null=True))
    def get_on_time(self, obj):
        """Against the promised day: the delivery if done, else the ETA."""
        when = local_date(obj.delivered_at or obj.eta)
        return when <= obj.order.promised_on if obj.order_id and when else None

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_supplier(self, obj):
        return {"id": obj.supplier_id, "name": obj.supplier.name} if obj.supplier_id else None

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_customer(self, obj):
        return {"id": obj.customer_id, "name": obj.customer.name} if obj.customer_id else None

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_purchase_order(self, obj):
        return {"id": obj.purchase_order_id, "code": obj.purchase_order.code} if obj.purchase_order_id else None

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_order(self, obj):
        return {"id": obj.order_id, "code": obj.order.code, "promised_on": obj.order.promised_on} if obj.order_id else None


class RouteSerializer(serializers.ModelSerializer):
    """Routes carry no prices: every role reads them."""

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    name = serializers.SerializerMethodField()
    stops = RouteStopSerializer(many=True, read_only=True)
    stops_count = serializers.SerializerMethodField()
    vehicle = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()

    class Meta:
        model = Route
        fields = [
            "id", "name", "date", "status", "status_display", "distance_km", "duration_min", "path", "recalculated_from", "stops_count", "stops",
            "vehicle", "started_at", "completed_at", "summary", "created_at",
        ]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_vehicle(self, obj):
        v = obj.vehicle
        return {"id": v.id, "name": v.name, "color": v.color, "kind": v.kind, "capacity_units": v.capacity_units} if v else None

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_summary(self, obj):
        """The route's justification (ADR 0026 §2): "4 entregas · 1 450 prendas (73 % de capacidad)
        · 18 km · vuelve 12:40"."""
        from django.utils import timezone

        stops = list(obj.stops.all())
        deliveries = [s for s in stops if s.kind == RouteStop.Kind.DELIVERY]
        units = sum(sum(i.quantity for i in s.order.items.all()) for s in deliveries if s.order_id)
        capacity = obj.vehicle.capacity_units if obj.vehicle_id else None
        pct = round(units * 100 / capacity) if capacity else None
        returns_at = stops[-1].eta if stops else None
        parts = [f"{len(deliveries)} entrega{'s' if len(deliveries) != 1 else ''}", f"{units:,}".replace(",", " ") + " prendas" + (f" ({pct} % de capacidad)" if pct is not None else "")]
        parts.append(f"{float(obj.distance_km):.0f} km")
        if returns_at:
            parts.append(f"vuelve {timezone.localtime(returns_at):%H:%M}")
        return {
            "deliveries": len(deliveries), "delivered": sum(1 for s in deliveries if s.delivered_at), "units": units,
            "capacity_pct": pct, "returns_at": returns_at, "text": " · ".join(parts),
        }

    @extend_schema_field(OpenApiTypes.STR)
    def get_name(self, obj):
        """What the map shows: the delivery day, and whether it recalculates an earlier plan."""
        if obj.vehicle_id:
            return f"{obj.vehicle.name} · {obj.date:%d/%m}"
        name = f"Entregas del {obj.date:%d/%m}"
        if obj.recalculated_from_id and obj.recalculated_from.date != obj.date:
            name += f" (antes {obj.recalculated_from.date:%d/%m})"
        elif obj.recalculated_from_id:
            name += " (recalculada)"
        return name

    @extend_schema_field(OpenApiTypes.INT)
    def get_stops_count(self, obj):
        return max(obj.stops.count() - 2, 0)  # Without the plant at both ends.
