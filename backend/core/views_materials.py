"""Inventory for the manager and production (P0 of 10/10): stock, what open orders already
took from it and what is left."""

from decimal import Decimal

from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from operations.models import Order, Requirement

from .models import Material
from .permissions import IsManagerOrProduction
from .serializers import RelativeFileField

OPEN_ORDER_STATUSES = [s for s, _ in Order.Status.choices if s not in ("delivered", "cancelled")]


def _committed_by_material() -> dict[int, Decimal]:
    totals: dict[int, Decimal] = {}
    rows = Requirement.objects.filter(kind="material", order__status__in=OPEN_ORDER_STATUSES).values_list("material_id", "qty_from_stock")
    for material_id, qty in rows:
        totals[material_id] = totals.get(material_id, Decimal("0")) + qty
    return totals


class MaterialSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    unit_display = serializers.CharField(source="get_unit_display", read_only=True)
    image = RelativeFileField(read_only=True)
    committed = serializers.SerializerMethodField()
    available = serializers.SerializerMethodField()

    class Meta:
        model = Material
        fields = ["id", "sku", "name", "kind", "kind_display", "unit", "unit_display", "stock", "committed", "available", "image"]

    def _committed(self, obj) -> Decimal:
        return self.context["committed"].get(obj.id, Decimal("0"))

    def get_committed(self, obj) -> str:
        return str(self._committed(obj).quantize(Decimal("0.01")))

    def get_available(self, obj) -> str:
        return str((obj.stock - self._committed(obj)).quantize(Decimal("0.01")))


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
    `Requirement.qty_from_stock` of open orders; `available = stock - committed`."""

    permission_classes = [IsManagerOrProduction]

    @extend_schema(responses={200: MaterialSerializer(many=True)})
    def get(self, request):
        queryset = Material.objects.order_by("kind", "name")
        if request.query_params.get("kind"):
            queryset = queryset.filter(kind=request.query_params["kind"])
        if request.query_params.get("q"):
            text = request.query_params["q"].strip()
            queryset = queryset.filter(Q(sku__icontains=text) | Q(name__icontains=text))
        context = {"request": request, "committed": _committed_by_material()}
        return Response(MaterialSerializer(queryset, many=True, context=context).data)


class MaterialDetailView(APIView):
    """`GET /api/materials/<id>/`: the list row plus the open orders that take from it."""

    permission_classes = [IsManagerOrProduction]

    @extend_schema(responses={200: MaterialDetailSchema})
    def get(self, request, pk: int):
        material = Material.objects.filter(pk=pk).first()
        if material is None:
            return Response(status=404)
        context = {"request": request, "committed": _committed_by_material()}
        data = MaterialSerializer(material, context=context).data
        requirements = (
            Requirement.objects.filter(material=material, order__status__in=OPEN_ORDER_STATUSES)
            .select_related("order")
            .prefetch_related("purchase_order_items__purchase_order")
            .order_by("order__promised_on", "order_id")
        )
        data["requirements"] = MaterialRequirementSerializer(requirements, many=True).data
        return Response(data)
