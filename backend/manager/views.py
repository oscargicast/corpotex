from django.db.models import F
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from core import clock
from core.models import Config
from core.serializers import serializer_for
from operations.models import Order, PurchaseOrder
from suppliers.services import payments_by_supplier

from .models import Alert, Decision


class MonitorView(APIView):
    """Everything the Monitor page shows, in one call. Shape agreed with `disenador`
    (frontend/mocks/monitor.json); manager-only parts are `null` for the other roles."""

    @extend_schema(responses={200: dict})
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
            }
        )
