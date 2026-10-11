from django.db.models import F
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core import clock
from core.models import Config
from core.views_agent import agent_settings
from core.permissions import IsManager
from core.serializers import serializer_for
from operations.models import Order, PurchaseOrder
from operations.serializers import OrderListSerializer
from suppliers.services import payments_by_supplier

from . import services
from .models import Alert, Decision
from .serializers import AlertSerializer, DecisionSerializer

# Response shapes for the schema (the views build these dicts by hand).
MonitorSchema = inline_serializer(
    "Monitor",
    fields={
        "clock": inline_serializer(
            "MonitorClock",
            fields={
                "now": serializers.DateTimeField(),
                "factor": serializers.DecimalField(max_digits=8, decimal_places=2),
                "paused": serializers.BooleanField(),
            },
        ),
        "kpis": inline_serializer(
            "MonitorKpis",
            fields={
                "orders_in_danger": serializers.IntegerField(),
                "orders_at_risk": serializers.IntegerField(),
                "stalled_purchase_orders": serializers.IntegerField(),
                "pending_decisions": serializers.IntegerField(allow_null=True),
                "open_alerts": serializers.IntegerField(),
            },
        ),
        "alerts": AlertSerializer(many=True),
        "decisions": DecisionSerializer(many=True),
        "redistributions": DecisionSerializer(many=True),
        "orders_in_danger": OrderListSerializer(many=True),
        "payments_by_supplier": serializers.ListField(child=serializers.DictField(), allow_null=True),
        "plant": inline_serializer(
            "MonitorPlant",
            fields={
                "name": serializers.CharField(),
                "weekly_capacity": serializers.IntegerField(allow_null=True),
                "units_in_progress": serializers.IntegerField(help_text="Units in the plant's open workshop purchase orders."),
                "load_pct": serializers.FloatField(allow_null=True, help_text="units_in_progress over weekly_capacity, in %; null without a capacity."),
                "open_purchase_orders": serializers.IntegerField(),
            },
            allow_null=True,
            help_text="ADR 0030: the own plant's capacity KPI; null when there is no in-house supplier.",
        ),
        "agent": inline_serializer(
            "MonitorAgent",
            fields={"paused": serializers.BooleanField(), "paused_suppliers": serializers.IntegerField()},
            help_text="ADR 0030: the agent's pause, for a notice on the Monitor.",
        ),
    },
)
BadgesSchema = inline_serializer(
    "Badges",
    fields={
        "assistant_unread": serializers.IntegerField(),
        "latest_unread": inline_serializer(
            "BadgesLatestUnread",
            fields={"id": serializers.IntegerField(), "preview": serializers.CharField(), "alert_kind": serializers.CharField(allow_null=True)},
            allow_null=True,
        ),
        "claude_ok": serializers.BooleanField(),
        "pending_decisions": serializers.IntegerField(allow_null=True),
        "orders_in_danger": serializers.IntegerField(allow_null=True),
        "claude_expired": serializers.BooleanField(allow_null=True),
        "claude_last_error": serializers.CharField(allow_null=True),
        "claude_refresh_expires_at": serializers.DateTimeField(allow_null=True),
    },
)
ManagerPendingSchema = inline_serializer(
    "ManagerPending",
    fields={"decisions": DecisionSerializer(many=True), "orders_in_danger": OrderListSerializer(many=True), "alerts": AlertSerializer(many=True)},
)


def plant_capacity() -> dict | None:
    """ADR 0030: units in the open purchase orders of the own plant over its weekly capacity."""
    from suppliers.models import Supplier
    from suppliers.services import OPEN, supplier_load

    plant = Supplier.objects.filter(is_in_house=True).order_by("id").first()
    if plant is None:
        return None
    load = supplier_load(plant)
    return {
        "name": plant.name,
        "weekly_capacity": plant.weekly_capacity,
        "units_in_progress": int(load["units"]),
        "load_pct": load["pct"],
        "open_purchase_orders": plant.purchase_orders.filter(status__in=OPEN).count(),
    }


class MonitorView(APIView):
    """Everything the Monitor page shows, in one call. Shape agreed with `disenador`
    (frontend/mocks/monitor.json); manager-only parts are `null` for the other roles."""

    @extend_schema(responses={200: MonitorSchema})
    def get(self, request):
        role = request.user.role
        is_manager = role == "manager"
        config = Config.load()
        now = clock.now(config)

        open_alerts = Alert.objects.filter(status="open").select_related("order", "purchase_order__supplier")
        pending = Decision.objects.filter(status="pending")
        in_danger = Order.objects.filter(risk="in_danger").select_related("customer", "brand").prefetch_related("items")
        redistributions = (
            Decision.objects.filter(kind="approve_assignment", purchase_orders__redistributed_from__isnull=False)
            .exclude(status="pending")
            .distinct()
            .order_by("-id")[:3]
        )
        # Stalled: open, follow-up overdue, and no progress reported since that follow-up was due.
        stalled = (
            PurchaseOrder.objects.filter(status__in=PurchaseOrder.OPEN_STATUSES, next_follow_up_at__lt=now)
            .exclude(progress_reports__reported_at__gte=F("next_follow_up_at"))
            .distinct()
        )

        decision_cls = serializer_for(Decision, role)
        context = {"request": request, "role": role}
        return Response(
            {
                "clock": {"now": now, "factor": config.clock_factor, "paused": config.clock_paused},
                "kpis": {
                    "orders_in_danger": in_danger.count(),
                    "orders_at_risk": Order.objects.filter(risk="at_risk").count(),
                    "stalled_purchase_orders": stalled.count(),
                    "pending_decisions": pending.count() if is_manager else None,
                    "open_alerts": open_alerts.count(),
                },
                "alerts": serializer_for(Alert, role)(open_alerts, many=True, context=context).data,
                "decisions": decision_cls(pending, many=True, context=context).data if is_manager else [],
                "redistributions": decision_cls(redistributions, many=True, context=context).data,
                "orders_in_danger": serializer_for(Order, role)(in_danger, many=True, context=context).data,
                "payments_by_supplier": payments_by_supplier() if is_manager else None,
                "plant": plant_capacity(),
                "agent": agent_settings(),
            }
        )


class AlertListView(APIView):
    """Open alerts. `?mine=1` keeps only the ones that concern the caller's role, with the same
    rule the assistant uses to notify (ADR 0020). `?status=` filters; default `open`."""

    @extend_schema(responses={200: AlertSerializer(many=True)})
    def get(self, request):
        role = request.user.role
        status_param = request.query_params.get("status", "open")
        qs = Alert.objects.all() if status_param == "all" else Alert.objects.filter(status=status_param)
        qs = qs.select_related("order", "purchase_order__supplier")
        alerts = services.alerts_for_role(role, qs) if request.query_params.get("mine") == "1" else list(qs)
        return Response(serializer_for(Alert, role)(alerts, many=True, context={"request": request, "role": role}).data)


class BadgesView(APIView):
    """Counters for the menu and the assistant button, polled every 5 s (ADR 0020, 0022)."""

    @extend_schema(responses={200: BadgesSchema})
    def get(self, request):
        from messaging.services import unread_assistant_count
        from messaging.models import Message

        user = request.user
        is_manager = user.role == "manager"
        config = Config.load()
        latest = (
            Message.objects.filter(conversation__channel="dashboard", conversation__user=user, author="agent", read_at__isnull=True)
            .order_by("-sent_at")
            .first()
        )
        claude = _claude_status()
        return Response(
            {
                "assistant_unread": unread_assistant_count(user),
                "latest_unread": (
                    {"id": latest.id, "preview": latest.text[:120], "alert_kind": _alert_kind(latest)} if latest else None
                ),
                "claude_ok": bool(claude.get("connected")) and not claude.get("expired") and not config.claude_last_error,
                "pending_decisions": Decision.objects.filter(status="pending").count() if is_manager else None,
                "orders_in_danger": Order.objects.filter(risk="in_danger").count() if is_manager else None,
                "claude_expired": claude.get("expired") if is_manager else None,
                "claude_last_error": (config.claude_last_error or None) if is_manager else None,
                "claude_refresh_expires_at": claude.get("refresh_token_expires_at") if is_manager else None,
            }
        )


def _alert_kind(message):
    action = message.action or {}
    if action.get("kind") != "alert":
        return None
    from .models import Alert as AlertModel

    first = AlertModel.objects.filter(id__in=action.get("alert_ids", [])).order_by("-severity").first()
    return first.kind if first else None


def _claude_status() -> dict:
    try:
        from core.claude_account import status as claude_status

        return claude_status() or {}
    except Exception:  # The credential module is optional in tests.
        return {}


class ManagerPendingView(APIView):
    permission_classes = [IsManager]

    @extend_schema(responses={200: ManagerPendingSchema})
    def get(self, request):
        context = {"request": request, "role": "manager"}
        return Response(
            {
                "decisions": serializer_for(Decision, "manager")(Decision.objects.filter(status="pending"), many=True, context=context).data,
                "orders_in_danger": serializer_for(Order, "manager")(Order.objects.filter(risk="in_danger"), many=True, context=context).data,
                "alerts": serializer_for(Alert, "manager")(Alert.objects.filter(status="open"), many=True, context=context).data,
            }
        )


class DecisionActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "reject", "change_supplier"])
    supplier_id = serializers.IntegerField(required=False, allow_null=True)
    purchase_order_id = serializers.IntegerField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class DecisionResolveView(APIView):
    """Idempotent: the same action again returns 200 with the current state; a different one, 409."""

    permission_classes = [IsManager]

    @extend_schema(request=DecisionActionSerializer, responses={200: DecisionSerializer})
    def post(self, request, pk: int):
        decision = Decision.objects.filter(pk=pk).first()
        if decision is None:
            return Response(status=404)
        data = DecisionActionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            decision = services.resolve_decision(decision, actor=request.user, **data.validated_data)
        except services.DecisionConflict as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer_for(Decision, "manager")(decision, context={"role": "manager"}).data)


class AlertAcknowledgeView(APIView):
    permission_classes = [IsManager]

    @extend_schema(request=None, responses={200: AlertSerializer})
    def post(self, request, pk: int):
        alert = Alert.objects.filter(pk=pk).first()
        if alert is None:
            return Response(status=404)
        alert = services.acknowledge_alert(alert, actor=request.user)
        return Response(serializer_for(Alert, "manager")(alert, context={"role": "manager"}).data)
