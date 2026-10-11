from decimal import Decimal

from django.core.exceptions import PermissionDenied
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import FollowUpMode
from core.permissions import IsManager
from core.serializers import serializer_for
from messaging.models import AllowedNumber

from . import services
from .models import Currency, Supplier, SupplierKind
from .serializers import AllowedNumberSerializer, SupplierDetailSerializer

SelfRegisteredSchema = inline_serializer(
    "SelfRegistered",
    fields={"id": serializers.IntegerField(), "name": serializers.CharField(), "status": serializers.CharField(), "source": serializers.CharField()},
)
ImportResultSchema = inline_serializer(
    "SupplierImportResult",
    fields={
        "created": serializers.ListField(child=serializers.DictField()),
        "updated": serializers.ListField(child=serializers.DictField()),
        "errors": serializers.ListField(child=serializers.DictField()),
    },
)


class SupplierInSerializer(serializers.Serializer):
    """Registration payload (manager) and self-registration (public). `phone` creates an inactive
    AllowedNumber; `contact_name` is that number's name."""

    name = serializers.CharField(max_length=160)
    kind = serializers.ChoiceField(choices=SupplierKind.choices)
    specialties = serializers.ListField(child=serializers.CharField(max_length=60), required=False, default=list)
    city = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    address = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    lat = serializers.FloatField(required=False, allow_null=True)
    lng = serializers.FloatField(required=False, allow_null=True)
    weekly_capacity = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    lead_time_days = serializers.IntegerField(required=False, min_value=0, default=7)
    follow_up_every_hours = serializers.IntegerField(required=False, min_value=1, default=48)
    currency = serializers.ChoiceField(choices=Currency.choices, required=False, default="PEN")
    phone = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    contact_name = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    rates = serializers.ListField(child=serializers.DictField(), required=False, default=list)


class RateInSerializer(serializers.Serializer):
    """One reference price: the item by id (what the dashboard has), never both."""

    material_id = serializers.IntegerField(required=False, allow_null=True)
    product_id = serializers.IntegerField(required=False, allow_null=True)
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    valid_from = serializers.DateField(required=False, allow_null=True)


class SupplierPatchSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Supplier.Status.choices, required=False)
    contact_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    rates = RateInSerializer(many=True, required=False)
    name = serializers.CharField(max_length=160, required=False)
    kind = serializers.ChoiceField(choices=SupplierKind.choices, required=False)
    specialties = serializers.ListField(child=serializers.CharField(max_length=60), required=False)
    city = serializers.CharField(max_length=80, required=False, allow_blank=True)
    address = serializers.CharField(max_length=200, required=False, allow_blank=True)
    lat = serializers.FloatField(required=False, allow_null=True)
    lng = serializers.FloatField(required=False, allow_null=True)
    weekly_capacity = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    lead_time_days = serializers.IntegerField(required=False, min_value=0)
    follow_up_every_hours = serializers.IntegerField(required=False, min_value=1)
    follow_up_mode = serializers.ChoiceField(
        choices=FollowUpMode.choices, required=False, allow_blank=True, help_text="Empty: the general mode (ADR 0027). Only the manager sets it, not the public form."
    )
    currency = serializers.ChoiceField(choices=Currency.choices, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)
    agent_paused = serializers.BooleanField(required=False, help_text="ADR 0030: the agent writes nothing to this supplier.")


class NumberInSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=40)
    name = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")


class NumberPatchSerializer(serializers.Serializer):
    active = serializers.BooleanField(required=False)
    name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=40, required=False)


class ImportInSerializer(serializers.Serializer):
    file = serializers.FileField()


def _validated(serializer_class, data):
    serializer = serializer_class(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


class SupplierViewSet(viewsets.ReadOnlyModelViewSet):
    """Suppliers and workshops. Manager only (the list carries phone numbers and prices), except
    `self-register/`, which is public (ADR 0024)."""

    permission_classes = [IsManager]
    queryset = Supplier.objects.prefetch_related("numbers", "rates__material", "rates__product")

    def get_serializer_class(self):
        return serializer_for(Supplier, "manager", detail=self.action != "list")

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "role": "manager"}

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        for name in ("kind", "status", "source"):
            if params.get(name):
                qs = qs.filter(**{name: params[name]})
        return qs

    def _detail(self, supplier, http_status=status.HTTP_200_OK):
        supplier = self.get_queryset().get(pk=supplier.pk)  # Fresh: numbers and rates may have just changed.
        cls = serializer_for(Supplier, "manager", detail=True)
        return Response(cls(supplier, context=self.get_serializer_context()).data, status=http_status)

    @extend_schema(request=SupplierInSerializer, responses={201: SupplierDetailSerializer})
    def create(self, request):
        data = _validated(SupplierInSerializer, request.data)
        data["rates"] = [_validated(RateInSerializer, r) for r in data.get("rates") or []]
        try:
            supplier = services.create_supplier(data, actor=request.user)
        except services.NumberConflict as exc:
            raise ValidationError({"phone": str(exc)})
        except services.RateError as exc:
            raise ValidationError({"rates": str(exc)})
        except PermissionDenied as exc:
            raise DRFPermissionDenied(str(exc))
        return self._detail(supplier, status.HTTP_201_CREATED)

    @extend_schema(request=SupplierPatchSerializer, responses={200: SupplierDetailSerializer})
    def partial_update(self, request, pk=None):
        """Approve (`active`) or discard (`inactive`) a pending supplier, or edit its card."""
        try:
            supplier = services.update_supplier(self.get_object(), _validated(SupplierPatchSerializer, request.data), actor=request.user)
        except services.RateError as exc:
            raise ValidationError({"rates": str(exc)})
        return self._detail(supplier)

    @extend_schema(request=SupplierInSerializer, responses={201: SelfRegisteredSchema})
    @action(detail=False, methods=["post"], url_path="self-register", permission_classes=[AllowAny], authentication_classes=[])
    def self_register(self, request):
        """Public form: the supplier lands in `pending_review` with `source = self_registered`."""
        try:
            supplier = services.create_supplier(
                _validated(SupplierInSerializer, request.data), actor=None, source="self_registered", status="pending_review"
            )
        except services.NumberConflict as exc:
            raise ValidationError({"phone": str(exc)})
        return Response(
            {"id": supplier.id, "name": supplier.name, "status": supplier.status, "source": supplier.source}, status=status.HTTP_201_CREATED
        )

    @extend_schema(request=ImportInSerializer, responses={200: ImportResultSchema})
    @action(detail=False, methods=["post"], url_path="import")
    def import_csv(self, request):
        """Multipart CSV with columns name,kind,specialties,city,weekly_capacity,lead_time_days,currency,phone,lat,lng."""
        upload = _validated(ImportInSerializer, request.data)["file"]
        text = upload.read().decode("utf-8-sig", errors="replace")
        return Response(services.import_suppliers_csv(text, actor=request.user))

    @extend_schema(request=NumberInSerializer, responses={201: AllowedNumberSerializer})
    @action(detail=True, methods=["post"])
    def numbers(self, request, pk=None):
        """Adds a phone number, inactive until the manager switches it on."""
        data = _validated(NumberInSerializer, request.data)
        try:
            number = services.add_number(self.get_object(), actor=request.user, **data)
        except services.NumberConflict as exc:
            raise ValidationError({"phone": str(exc)})
        return Response(AllowedNumberSerializer(number).data, status=status.HTTP_201_CREATED)


class SupplierNumberView(APIView):
    """`PATCH /api/suppliers/<id>/numbers/<number_id>/ {active?, name?, phone?}`."""

    permission_classes = [IsManager]

    @extend_schema(request=NumberPatchSerializer, responses={200: AllowedNumberSerializer})
    def patch(self, request, pk: int, number_id: int):
        number = AllowedNumber.objects.filter(pk=number_id, supplier_id=pk).first()
        if number is None:
            return Response(status=404)
        data = _validated(NumberPatchSerializer, request.data)
        try:
            number = services.update_number(number, actor=request.user, **data)
        except services.NumberConflict as exc:
            raise ValidationError({"phone": str(exc)})
        return Response(AllowedNumberSerializer(number).data)
