from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from core.serializers import DisplayMixin, RelativeFileField, register
from messaging.models import AllowedNumber

from . import services
from .models import Rate, Supplier


class SupplierRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "kind"]


class AllowedNumberSerializer(serializers.ModelSerializer):
    class Meta:
        model = AllowedNumber
        fields = ["id", "phone", "name", "active", "simulated"]


class RateSerializer(serializers.ModelSerializer):
    material_id = serializers.IntegerField(read_only=True)
    product_id = serializers.IntegerField(read_only=True)
    item_name = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    class Meta:
        model = Rate
        fields = ["id", "material_id", "product_id", "item_name", "image", "unit_price", "valid_from"]

    @extend_schema_field(OpenApiTypes.STR)
    def get_item_name(self, obj):
        item = obj.material or obj.product
        return item.name if item else None

    @extend_schema_field(OpenApiTypes.STR)
    def get_image(self, obj):
        item = obj.material or obj.product
        return item.image.url if item and item.image else None


@register(Supplier)
class SupplierListSerializer(DisplayMixin, serializers.ModelSerializer):
    on_time_score = serializers.SerializerMethodField()
    quality_score = serializers.SerializerMethodField()
    open_purchase_orders = serializers.SerializerMethodField()
    load_pct = serializers.SerializerMethodField()
    numbers_count = serializers.SerializerMethodField()
    active_numbers_count = serializers.SerializerMethodField()
    has_style_notes = serializers.SerializerMethodField()
    whatsapp_ready = serializers.SerializerMethodField()
    purchase_orders_count = serializers.SerializerMethodField()
    last_delivered_on = serializers.SerializerMethodField()

    class Meta:
        model = Supplier
        display_fields = ["kind", "source", "status"]
        fields = [
            "id",
            "name",
            "kind",
            "specialties",
            "city",
            "lat",
            "lng",
            "is_in_house",
            "weekly_capacity",
            "lead_time_days",
            "currency",
            "source",
            "status",
            "on_time_score",
            "quality_score",
            "open_purchase_orders",
            "load_pct",
            "numbers_count",
            "active_numbers_count",
            "has_style_notes",
            "agent_paused",
            "whatsapp_ready",
            "purchase_orders_count",
            "last_delivered_on",
        ]

    def _scores(self, obj):
        if not hasattr(obj, "_scores"):
            obj._scores = services.supplier_scores(obj)
        return obj._scores

    @extend_schema_field(OpenApiTypes.FLOAT)
    def get_on_time_score(self, obj):
        return self._scores(obj)["on_time"]

    @extend_schema_field(OpenApiTypes.FLOAT)
    def get_quality_score(self, obj):
        return self._scores(obj)["quality"]

    @extend_schema_field(OpenApiTypes.INT)
    def get_open_purchase_orders(self, obj):
        return obj.purchase_orders.filter(status__in=services.OPEN).count()

    @extend_schema_field(OpenApiTypes.FLOAT)
    def get_load_pct(self, obj):
        return services.supplier_load(obj)["pct"]

    @extend_schema_field(OpenApiTypes.INT)
    def get_numbers_count(self, obj):
        return obj.numbers.count()

    @extend_schema_field(OpenApiTypes.INT)
    def get_active_numbers_count(self, obj):
        return obj.numbers.filter(active=True).count()

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_has_style_notes(self, obj):
        return bool(obj.notes)

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_whatsapp_ready(self, obj):
        """ADR 0030: the agent can write to it: not the own plant, at least one active number."""
        return not obj.is_in_house and any(n.active for n in obj.numbers.all())

    @extend_schema_field(OpenApiTypes.INT)
    def get_purchase_orders_count(self, obj):
        """Every purchase order it ever got, open or closed (ADR 0030); a suggestion the manager
        has not approved yet never reached it."""
        return obj.purchase_orders.exclude(status="suggested").count()

    @extend_schema_field(OpenApiTypes.DATE)
    def get_last_delivered_on(self, obj):
        """The day of its last delivery (a purchase order reaching `delivered`), or null."""
        from django.db.models import Max
        from django.utils import timezone

        from operations.models import StatusChange

        last = StatusChange.objects.filter(purchase_order__supplier=obj, status="delivered").aggregate(at=Max("at"))["at"]
        return timezone.localtime(last).date() if last else None


@register(Supplier, detail=True)
class SupplierDetailSerializer(SupplierListSerializer):
    numbers = AllowedNumberSerializer(many=True, read_only=True)
    rates = RateSerializer(many=True, read_only=True)
    ratings = serializers.SerializerMethodField()
    purchase_orders = serializers.SerializerMethodField()
    payments_summary = serializers.SerializerMethodField()

    class Meta(SupplierListSerializer.Meta):
        fields = SupplierListSerializer.Meta.fields + [
            "address",
            "follow_up_every_hours",
            "follow_up_mode",
            "notes",
            "source_detail",
            "numbers",
            "rates",
            "ratings",
            "purchase_orders",
            "payments_summary",
        ]

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_ratings(self, obj):
        return [
            {"purchase_order_code": po.code, **po.rating}
            for po in obj.purchase_orders.filter(rating__isnull=False).order_by("-id")
            if po.rating
        ]

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_purchase_orders(self, obj):
        from operations.serializers import PurchaseOrderListSerializer

        return PurchaseOrderListSerializer(obj.purchase_orders.all(), many=True, context=self.context).data

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_payments_summary(self, obj):
        from operations.models import Payment

        payments = Payment.objects.filter(purchase_order__supplier=obj).select_related("purchase_order__supplier")
        return services.payments_summary(payments)
