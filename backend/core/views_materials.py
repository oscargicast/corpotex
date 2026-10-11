"""Inventory for the manager and production (P0 of 10/10): stock, what open orders already
took from it and what is left."""

from decimal import Decimal

from django.db.models import Q
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from operations.models import Requirement
from operations.services import OPEN_ORDER_STATUSES, committed_stock_by_material, incoming_by_material, to_order_by_material

from .models import Material
from .permissions import IsManagerOrProduction
from .serializers import RelativeFileField

class IncomingPurchaseOrderSerializer(serializers.Serializer):
    """A live purchase order of the material (schema only: built by `incoming_by_material`)."""

    id = serializers.IntegerField()
    code = serializers.CharField()
    status = serializers.CharField()
    status_display = serializers.CharField()
    qty_pending = serializers.CharField(help_text="What its items of this material still have to bring, as a decimal string.")


class MaterialSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    unit_display = serializers.CharField(source="get_unit_display", read_only=True)
    image = RelativeFileField(read_only=True)
    committed = serializers.SerializerMethodField()
    available = serializers.SerializerMethodField()
    to_order = serializers.SerializerMethodField()
    incoming = serializers.SerializerMethodField()

    class Meta:
        model = Material
        fields = ["id", "sku", "name", "kind", "kind_display", "unit", "unit_display", "stock", "committed", "available", "to_order", "incoming", "image"]

    def _committed(self, obj) -> Decimal:
        return self.context["committed"].get(obj.id, Decimal("0"))

    def get_committed(self, obj) -> str:
        return str(self._committed(obj).quantize(Decimal("0.01")))

    def get_available(self, obj) -> str:
        return str((obj.stock - self._committed(obj)).quantize(Decimal("0.01")))

    def get_to_order(self, obj) -> str:
        """Still to buy: the same number as `total_to_order` in "Por pedir" (#81)."""
        return str(self.context["to_order"].get(obj.id, Decimal("0")).quantize(Decimal("0.01")))

    @extend_schema_field(IncomingPurchaseOrderSerializer(many=True))
    def get_incoming(self, obj) -> list:
        return self.context["incoming"].get(obj.id, [])


def material_context(request, material_ids=None) -> dict:
    """The per-material aggregates, computed once for the whole list (no query per row)."""
    return {
        "request": request,
        "committed": committed_stock_by_material(),
        "to_order": to_order_by_material(material_ids),
        "incoming": incoming_by_material(material_ids),
    }


class MaterialRequirementSerializer(serializers.ModelSerializer):
    order_code = serializers.CharField(source="order.code", read_only=True)
    order_id = serializers.IntegerField(read_only=True)
    qty_to_order = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    status = serializers.CharField(source="order.status", read_only=True)
    status_display = serializers.CharField(source="order.get_status_display", read_only=True)

    class Meta:
        model = Requirement
        fields = ["id", "order_id", "order_code", "qty_needed", "qty_from_stock", "qty_to_order", "status", "status_display"]


class MaterialDetailSchema(MaterialSerializer):
    """Schema only: the view adds `requirements` to the list row."""

    requirements = MaterialRequirementSerializer(many=True, read_only=True)

    class Meta(MaterialSerializer.Meta):
        fields = MaterialSerializer.Meta.fields + ["requirements"]


class MaterialListView(APIView):
    """`GET /api/materials/`: every material ordered by kind and name; `?kind=`, `?q=` (sku or name). `committed` is the sum of
    `Requirement.qty_from_stock` of open orders; `available = stock - committed`; `to_order` is what is still to buy
    (as in "Por pedir") and `incoming` the live purchase orders that will bring it."""

    permission_classes = [IsManagerOrProduction]

    @extend_schema(responses={200: MaterialSerializer(many=True)})
    def get(self, request):
        queryset = Material.objects.order_by("kind", "name")
        if request.query_params.get("kind"):
            queryset = queryset.filter(kind=request.query_params["kind"])
        if request.query_params.get("q"):
            text = request.query_params["q"].strip()
            queryset = queryset.filter(Q(sku__icontains=text) | Q(name__icontains=text))
        return Response(MaterialSerializer(queryset, many=True, context=material_context(request)).data)


class MaterialDetailView(APIView):
    """`GET /api/materials/<id>/`: the list row plus the open orders that take from it."""

    permission_classes = [IsManagerOrProduction]

    @extend_schema(responses={200: MaterialDetailSchema})
    def get(self, request, pk: int):
        material = Material.objects.filter(pk=pk).first()
        if material is None:
            return Response(status=404)
        data = MaterialSerializer(material, context=material_context(request, [material.id])).data
        requirements = (
            Requirement.objects.filter(material=material, order__status__in=OPEN_ORDER_STATUSES)
            .select_related("order")
            .prefetch_related("purchase_order_items__purchase_order")
            .order_by("order__promised_on", "order_id")
        )
        data["requirements"] = MaterialRequirementSerializer(requirements, many=True).data
        return Response(data)
