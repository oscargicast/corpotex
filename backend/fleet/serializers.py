from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import Vehicle, VehiclePosition


class VehicleSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Vehicle
        fields = [
            "id", "name", "plate", "kind", "kind_display", "capacity_units", "color", "driver_name", "is_active",
            "last_lat", "last_lng", "last_heading", "last_speed_kmh", "last_seen_at", "sim_active",
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


class PositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehiclePosition
        fields = ["lat", "lng", "heading", "speed_kmh", "recorded_at", "source", "route"]


class PositionInSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lng = serializers.FloatField(min_value=-180, max_value=180)
    heading = serializers.FloatField(required=False, allow_null=True)
    speed_kmh = serializers.FloatField(required=False, allow_null=True)
    recorded_at = serializers.DateTimeField(required=False)
    source = serializers.ChoiceField(choices=VehiclePosition.Source.choices, required=False, default=VehiclePosition.Source.DEVICE)


class NextStopSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    position = serializers.IntegerField()
    name = serializers.CharField()
    eta = serializers.DateTimeField(allow_null=True)


class LiveSerializer(serializers.Serializer):
    """Also the payload of the SSE `position` event and of each `snapshot` item."""

    vehicle_id = serializers.IntegerField()
    lat = serializers.FloatField(allow_null=True)
    lng = serializers.FloatField(allow_null=True)
    heading = serializers.FloatField(allow_null=True)
    speed_kmh = serializers.FloatField(allow_null=True)
    at = serializers.DateTimeField(allow_null=True)
    route_id = serializers.IntegerField(allow_null=True)
    next_stop = NextStopSerializer(allow_null=True)
    simulating = serializers.BooleanField()


class SimulateInSerializer(serializers.Serializer):
    speed_factor = serializers.FloatField(min_value=1, max_value=120, default=12)
    interval_s = serializers.IntegerField(min_value=1, max_value=30, default=3)
