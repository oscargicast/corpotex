"""Fleet and dispatch API (ADR 0026 §3). Writes are for the manager and production; every role
reads (sales sees where its orders are)."""

from datetime import date as date_type

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsManagerOrProduction
from operations import routes
from operations.models import Order, Route
from operations.serializers import RouteSerializer
from operations.views import route_queryset

from . import services
from .models import Vehicle
from .serializers import DispatchPatchSerializer, DispatchSerializer, PlanDayInSerializer, VehicleSerializer

PlanDaySchema = inline_serializer(
    "PlanDay",
    fields={
        "routes": RouteSerializer(many=True),
        "unassigned": inline_serializer(
            "PlanDayUnassigned",
            fields={"order_id": serializers.IntegerField(), "code": serializers.CharField(), "reason": serializers.CharField(), "reason_display": serializers.CharField()},
            many=True,
        ),
        "suggested_next_day": serializers.ListField(child=serializers.IntegerField()),
    },
)


def ids_param(value: str | None) -> list[int]:
    return [int(v) for v in (value or "").split(",") if v.strip().isdigit()]


def date_param(value: str | None):
    try:
        return date_type.fromisoformat(value) if value else None
    except ValueError:
        return None


def route_response(route: Route, status: int = 200) -> Response:
    return Response(RouteSerializer(route_queryset().get(pk=route.pk)).data, status=status)


def conflict(exc: routes.DispatchError) -> Response:
    return Response({"detail": str(exc)}, status=409)


class DispatchListView(APIView):
    """`GET /api/dispatches/?status=ready,delivered&from=&to=&vehicle_ids=&unassigned=1`."""

    @extend_schema(responses={200: DispatchSerializer(many=True)})
    def get(self, request):
        params = request.query_params
        statuses = [s for s in (params.get("status") or "ready,delivered").split(",") if s in ("ready", "delivered")]
        rows = services.dispatches(
            statuses=statuses, date_from=date_param(params.get("from")), date_to=date_param(params.get("to")),
            vehicle_ids=ids_param(params.get("vehicle_ids")), unassigned=params.get("unassigned") == "1",
        )
        return Response(DispatchSerializer(rows, many=True).data)


class DispatchDetailView(APIView):
    """`PATCH /api/dispatches/<order_id>/ {scheduled_on?, vehicle_id?}`: reschedule or move."""

    permission_classes = [IsManagerOrProduction]

    @extend_schema(request=DispatchPatchSerializer, responses={200: DispatchSerializer})
    def patch(self, request, order_id: int):
        order = Order.objects.filter(pk=order_id).first()
        if order is None:
            return Response(status=404)
        data = DispatchPatchSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        vehicle = None
        if data.validated_data.get("vehicle_id") is not None:
            vehicle = Vehicle.objects.filter(pk=data.validated_data["vehicle_id"], is_active=True).first()
            if vehicle is None:
                return Response({"detail": "Ese vehículo no existe o no está activo."}, status=400)
        try:
            routes.move_dispatch(order, scheduled_on=data.validated_data.get("scheduled_on"), vehicle=vehicle, actor=request.user)
        except routes.DispatchError as exc:
            return conflict(exc)
        row = next(r for r in services.dispatches(statuses=("ready",)) if r["order"]["id"] == order.id)
        return Response(DispatchSerializer(row).data)


class VehicleListView(APIView):
    """`GET /api/vehicles/`: the active fleet with its last position."""

    @extend_schema(responses={200: VehicleSerializer(many=True)})
    def get(self, request):
        return Response(VehicleSerializer(Vehicle.objects.filter(is_active=True), many=True).data)


class PlanDayView(APIView):
    """`POST /api/routes/plan-day/ {date, vehicle_ids?, order_ids?}` (ADR 0026 §2)."""

    permission_classes = [IsManagerOrProduction]

    @extend_schema(request=PlanDayInSerializer, responses={201: PlanDaySchema})
    def post(self, request):
        data = PlanDayInSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            plan = routes.plan_day(
                data.validated_data["date"], vehicle_ids=data.validated_data.get("vehicle_ids"), order_ids=data.validated_data.get("order_ids"), actor=request.user
            )
        except routes.DispatchError as exc:
            return Response({"detail": str(exc)}, status=400)
        qs = route_queryset().filter(pk__in=[r.pk for r in plan.routes]).order_by("-vehicle__capacity_units", "id")
        return Response({"routes": RouteSerializer(qs, many=True).data, "unassigned": plan.unassigned, "suggested_next_day": plan.suggested_next_day}, status=201)


class RouteActionView(APIView):
    permission_classes = [IsManagerOrProduction]
    action = ""

    @extend_schema(request=None, responses={200: RouteSerializer})
    def post(self, request, pk: int):
        route = Route.objects.filter(pk=pk).first()
        if route is None:
            return Response(status=404)
        try:
            getattr(routes, f"{self.action}_route")(route, actor=request.user)
        except routes.DispatchError as exc:
            return conflict(exc)
        return route_response(route)


class RouteStartView(RouteActionView):
    """`POST /api/routes/<id>/start/`: planned → in_progress."""

    action = "start"


class RouteCompleteView(RouteActionView):
    """`POST /api/routes/<id>/complete/`: in_progress → completed."""

    action = "complete"


class StopDeliverView(APIView):
    """`POST /api/routes/<id>/stops/<stop_id>/deliver/`: the order goes `delivered`."""

    permission_classes = [IsManagerOrProduction]

    @extend_schema(request=None, responses={200: RouteSerializer})
    def post(self, request, pk: int, stop_id: int):
        route = Route.objects.filter(pk=pk).first()
        stop = route.stops.filter(pk=stop_id).first() if route else None
        if stop is None:
            return Response(status=404)
        try:
            routes.deliver_stop(route, stop, actor=request.user)
        except routes.DispatchError as exc:
            return conflict(exc)
        return route_response(route)
