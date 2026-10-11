"""Proactive follow-up settings (ADR 0027 §1): the manager sets the mode, the hours and the
working days; the preview shows today's plan."""

from datetime import datetime

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Config, FollowUpMode
from .permissions import IsManager

MIN_WINDOW_MINUTES = 120


class FollowUpSettingsSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=FollowUpMode.choices, source="follow_up_mode", required=False)
    mode_display = serializers.CharField(source="get_follow_up_mode_display", read_only=True)
    window_start = serializers.TimeField(source="follow_up_window_start", required=False, format="%H:%M", help_text="Lima time, HH:MM.")
    window_end = serializers.TimeField(source="follow_up_window_end", required=False, format="%H:%M", help_text="Lima time, HH:MM.")
    weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6), source="follow_up_weekdays", required=False, help_text="0 = Monday … 6 = Sunday."
    )

    def validate_weekdays(self, value):
        days = sorted(set(value))
        if not days:
            raise serializers.ValidationError("Elige al menos un día.")
        return days

    def validate(self, attrs):
        start = attrs.get("follow_up_window_start", self.instance.follow_up_window_start if self.instance else None)
        end = attrs.get("follow_up_window_end", self.instance.follow_up_window_end if self.instance else None)
        if start and end:
            if start >= end:
                raise serializers.ValidationError({"window_start": "«Desde» tiene que ser antes de «Hasta»."})
            minutes = (datetime.combine(datetime.min, end) - datetime.combine(datetime.min, start)).seconds // 60
            if minutes < MIN_WINDOW_MINUTES:
                raise serializers.ValidationError({"window_end": "La ventana tiene que durar al menos 2 horas."})
        return attrs

    def update(self, instance, validated_data):
        for name, value in validated_data.items():
            setattr(instance, name, value)
        instance.save(update_fields=[*validated_data, "updated_at"])
        return instance


class FollowUpSupplierSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class FollowUpPlanSerializer(serializers.Serializer):
    supplier = FollowUpSupplierSerializer()
    purchase_orders = serializers.ListField(child=serializers.CharField())
    at = serializers.DateTimeField()
    kind = serializers.ChoiceField(choices=[("checkpoint", "Punto de control"), ("reminder", "Recordatorio")])
    reason = serializers.CharField()
    mode = serializers.ChoiceField(choices=FollowUpMode.choices)


class FollowUpSettingsView(APIView):
    """`GET/PATCH /api/settings/follow-up/` (manager only)."""

    permission_classes = [IsManager]

    @extend_schema(responses={200: FollowUpSettingsSerializer})
    def get(self, request):
        return Response(FollowUpSettingsSerializer(Config.load()).data)

    @extend_schema(request=FollowUpSettingsSerializer, responses={200: FollowUpSettingsSerializer})
    def patch(self, request):
        data = FollowUpSettingsSerializer(Config.load(), data=request.data, partial=True)
        data.is_valid(raise_exception=True)
        return Response(FollowUpSettingsSerializer(data.save()).data)


class FollowUpPreviewView(APIView):
    """`GET /api/settings/follow-up/preview/` (manager only): today's plan,
    `[{supplier: {id, name}, purchase_orders: [code], at, kind, reason, mode}]`."""

    permission_classes = [IsManager]

    @extend_schema(responses={200: FollowUpPlanSerializer(many=True)})
    def get(self, request):
        from manager.follow_up import preview

        return Response(FollowUpPlanSerializer(preview(), many=True).data)
