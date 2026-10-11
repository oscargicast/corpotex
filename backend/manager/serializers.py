from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from core.serializers import DisplayMixin, register

from .models import Alert, Decision


@register(Alert)
class AlertSerializer(DisplayMixin, serializers.ModelSerializer):
    order = serializers.SerializerMethodField()
    purchase_order = serializers.SerializerMethodField()
    material = serializers.SerializerMethodField()

    class Meta:
        model = Alert
        display_fields = ["kind", "severity", "status"]
        role_visible = ("detail",)  # The purchase suggestion is for production too; prices inside are still stripped.
        fields = ["id", "kind", "severity", "status", "text", "detail", "detected_at", "order", "purchase_order", "material"]

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_material(self, obj):
        return {"id": obj.material_id, "sku": obj.material.sku, "name": obj.material.name} if obj.material_id else None

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_order(self, obj):
        return {"id": obj.order_id, "code": obj.order.code} if obj.order_id else None

    @extend_schema_field(OpenApiTypes.OBJECT)
    def get_purchase_order(self, obj):
        if not obj.purchase_order_id:
            return None
        po = obj.purchase_order
        return {"id": po.id, "code": po.code, "supplier_name": po.supplier.name}


@register(Decision)
class DecisionSerializer(DisplayMixin, serializers.ModelSerializer):
    purchase_orders = serializers.SerializerMethodField()
    orders = serializers.SerializerMethodField()

    class Meta:
        model = Decision
        display_fields = ["kind", "status"]
        fields = ["id", "kind", "status", "summary", "detail", "created_at", "resolved_at", "purchase_orders", "orders"]

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_purchase_orders(self, obj):
        return [
            {"id": po.id, "code": po.code, "supplier_name": po.supplier.name}
            for po in obj.purchase_orders.select_related("supplier")
        ]

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_orders(self, obj):
        seen = {}
        for po in obj.purchase_orders.prefetch_related("items__requirement__order__customer"):
            for item in po.items.all():
                order = item.requirement.order
                seen[order.id] = {"id": order.id, "code": order.code, "customer_name": order.customer.name}
        return list(seen.values())
