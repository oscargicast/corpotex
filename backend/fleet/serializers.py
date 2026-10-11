from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Vehicle


class VehicleSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Vehicle
        fields = [
            "id", "name", "plate", "kind", "kind_display", "capacity_units", "color", "driver_name", "is_active",
            "last_lat", "last_lng", "last_heading", "last_speed_kmh", "last_seen_at",
        ]


class DispatchOrderSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    customer_name = serializers.CharField()
    units = serializers.IntegerField()
    promised_on = serializers.DateField()


class DispatchSerializer(serializers.Serializer):
    """A customer order on its way out (ADR 0026 §3). `dispatch` is the delivery to the
    customer; `Delivery` is a supplier's delivery at the plant."""

    order = DispatchOrderSerializer()
    status = serializers.CharField()
    scheduled_on = serializers.DateField()
    delivered_at = serializers.DateTimeField(allow_null=True)
    address = serializers.CharField(allow_blank=True)
    lat = serializers.FloatField(allow_null=True)
    lng = serializers.FloatField(allow_null=True)
    route_id = serializers.IntegerField(allow_null=True)
    vehicle = serializers.SerializerMethodField()
    stop = serializers.SerializerMethodField()
    on_time = serializers.BooleanField(allow_null=True)

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_vehicle(self, obj):
        return obj["vehicle"]

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_stop(self, obj):
        return obj["stop"]


class DispatchPatchSerializer(serializers.Serializer):
    scheduled_on = serializers.DateField(required=False)
    vehicle_id = serializers.IntegerField(required=False)


class PlanDayInSerializer(serializers.Serializer):
    date = serializers.DateField()
    vehicle_ids = serializers.ListField(child=serializers.IntegerField(), required=False)
    order_ids = serializers.ListField(child=serializers.IntegerField(), required=False)
