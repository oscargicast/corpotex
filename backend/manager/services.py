"""Decisions, alerts and who gets told (ADR 0017, 0020)."""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core import clock
from core.models import Config, User
from core.permissions import require_role
from operations.models import Order, PurchaseOrder

from .models import Alert, AlertNotification, Decision

logger = logging.getLogger(__name__)

# Who is told about each alert kind (ADR 0020). The manager gets everything.
ALERT_ROLES = {
    "stalled_purchase_order": ("manager", "production"),  # production only for workshops, see notify_roles
    "no_response": ("manager",),
    "delay": ("manager", "production"),
    "order_in_danger": ("manager", "sales", "production"),
    "no_channel": ("manager",),
    "payment_due": ("manager",),
    "decision_pending": ("manager",),
    "instance_down": ("manager",),
    "turn_failed": ("manager",),
    "style_refresh_failed": ("manager",),
    "claude_disconnected": ("manager",),
}
SEVERITY = {
    "order_in_danger": "critical",
    "delay": "critical",
    "no_channel": "critical",
    "claude_disconnected": "critical",
    "instance_down": "critical",
    "turn_failed": "warning",
}


# --- alerts ---------------------------------------------------------------------------------


def alert_concerns_role(alert: Alert, role: str | None) -> bool:
    """The same rule for `notify_roles` and `GET /api/alerts/?mine=1`: the manager sees all;
    sales what touches the customer's date; production what touches workshops."""
    if role == "manager":
        return True
    po = alert.purchase_order
    if role == "sales":
        return alert.kind in ("order_in_danger", "delay", "no_response")
    if role == "production":
        if alert.kind == "order_in_danger":
            return True
        return bool(po and po.supplier.kind == "workshop" and alert.kind in ("stalled_purchase_order", "delay", "no_response"))
    return False


def alerts_for_role(role: str | None, queryset=None):
    qs = (queryset if queryset is not None else Alert.objects.filter(status="open")).select_related(
        "order", "purchase_order__supplier"
    )
    return [a for a in qs if alert_concerns_role(a, role)]


def open_alert(kind: str, *, text: str, order=None, purchase_order=None, decision=None, severity=None) -> Alert:
    """Idempotent while open: the same (kind, target) returns the existing alert."""
    existing = Alert.objects.filter(
        kind=kind, status="open", order=order, purchase_order=purchase_order, decision=decision
    ).first()
    if existing:
        return existing
    alert = Alert.objects.create(
        kind=kind,
        severity=severity or SEVERITY.get(kind, "warning"),
        order=order,
        purchase_order=purchase_order,
        decision=decision,
        text=text[:300],
        detected_at=clock.now(),
    )
    notify_roles(alert)
    return alert


def resolve_alerts(kind: str, **target) -> int:
    return Alert.objects.filter(kind=kind, status__in=("open", "acknowledged"), **target).update(
        status="resolved", resolved_at=clock.now()
    )


def acknowledge_alert(alert: Alert, *, actor) -> Alert:
    require_role(actor, "manager")
    if alert.status == "open":
        alert.status = "acknowledged"
        alert.save(update_fields=["status", "updated_at"])
    return alert


def notify_roles(alert: Alert) -> list[AlertNotification]:
    """One notification per active user of the target roles, and one assistant turn each.
    Several alerts in the same tick land in the same pending turn (ADR 0020)."""
    from messaging.services import dashboard_conversation, enqueue_turn

    created = []
    for user in User.objects.filter(is_active=True, groups__isnull=False).distinct():
        if not alert_concerns_role(alert, user.role):
            continue
        if AlertNotification.objects.filter(alert=alert, user=user).exists():
            continue
        conversation = dashboard_conversation(user)
        turn = enqueue_turn(conversation, "alert")
        created.append(AlertNotification.objects.create(alert=alert, user=user, turn=turn))
    return created


def repeat_open_alerts_to_manager() -> int:
    """An alert still open a simulated day after the last notice is raised again, manager only."""
    from messaging.services import dashboard_conversation, enqueue_turn

    count = 0
    cutoff = clock.now() - timedelta(days=1)
    for alert in Alert.objects.filter(status="open"):
        for user in User.objects.filter(is_active=True, groups__name="Gerente"):
            last = alert.notifications.filter(user=user).order_by("-id").first()
            if last and last.sent_at and last.sent_at <= cutoff:
                turn = enqueue_turn(dashboard_conversation(user), "alert")
                AlertNotification.objects.create(alert=alert, user=user, turn=turn)
                count += 1
    return count


# --- decisions ------------------------------------------------------------------------------


def create_decision(*, kind: str, purchase_orders, summary: str, detail: dict, conversation=None) -> Decision:
    """Idempotent: an existing pending decision of the same kind that already includes one of
    these purchase orders (or, without purchase orders, the same conversation) is returned."""
    purchase_orders = list(purchase_orders)
    with transaction.atomic():
        if purchase_orders:
            ids = sorted(po.id for po in purchase_orders)
            list(PurchaseOrder.objects.select_for_update().filter(id__in=ids).order_by("id"))
            existing = Decision.objects.filter(kind=kind, status="pending", purchase_orders__id__in=ids).distinct().first()
        else:
            existing = Decision.objects.filter(kind=kind, status="pending", conversation=conversation).first()
        if existing:
            return existing
        decision = Decision.objects.create(kind=kind, summary=summary[:300], detail=detail, conversation=conversation)
        decision.purchase_orders.set(purchase_orders)
    return decision


class DecisionConflict(Exception):
    """Already resolved with a different action (the view answers 409)."""


def resolve_decision(decision: Decision, *, action: str, supplier_id=None, purchase_order_id=None, note: str = "", actor) -> Decision:
    from messaging.services import enqueue_turn
    from operations.services import approve_purchase_orders, compute_critical_path

    require_role(actor, "manager")
    outcome = {"approve": "approved", "reject": "rejected", "change_supplier": "supplier_changed"}[action]
    if decision.status != "pending":
        same = decision.status == outcome and (decision.detail.get("resolution") or {}) == {
            "supplier_id": supplier_id,
            "purchase_order_id": purchase_order_id,
        }
        if same:
            return decision
        raise DecisionConflict(f"Ya está {decision.get_status_display().lower()}")

    with transaction.atomic():
        pos = list(decision.purchase_orders.select_related("supplier"))
        if action == "change_supplier":
            if len(pos) > 1 and purchase_order_id is None:
                raise ValueError("purchase_order_id es obligatorio cuando la decisión tiene más de un pedido")
            target = next((po for po in pos if purchase_order_id in (None, po.id)), None)
            if target is None or supplier_id is None:
                raise ValueError("supplier_id y purchase_order_id deben apuntar a un pedido de la decisión")
            from suppliers.models import Rate, Supplier

            target.supplier = Supplier.objects.get(pk=supplier_id)
            target.save(update_fields=["supplier", "updated_at"])
            # The reference price follows the supplier: the first contact proposes their own rate.
            for item in target.items.select_related("requirement"):
                rate = Rate.objects.filter(
                    supplier=target.supplier, material=item.requirement.material, product=item.requirement.product
                ).order_by("-valid_from").first()
                if rate is not None:
                    item.unit_price = rate.unit_price
                    item.save(update_fields=["unit_price", "updated_at"])
        if decision.kind == "approve_assignment":
            proposed_id = (decision.detail.get("after") or {}).get("route_id")
            if proposed_id:
                from operations.models import Route
                from operations.routes import discard, promote

                proposed = Route.objects.filter(pk=proposed_id).first()
                if proposed is not None:
                    (promote if action in ("approve", "change_supplier") else discard)(proposed)
            if action in ("approve", "change_supplier"):
                approve_purchase_orders(pos, actor=actor)
            else:
                from operations.services import set_status

                for po in pos:
                    if po.status == PurchaseOrder.Status.SUGGESTED:
                        set_status(po, PurchaseOrder.Status.CANCELLED, actor=actor, note=note or "Asignación rechazada")
                for order in {i.requirement.order for po in pos for i in po.items.select_related("requirement__order")}:
                    compute_critical_path(order)
        elif decision.conversation_id:
            enqueue_turn(decision.conversation, "decision")
        decision.status = outcome
        decision.note = note
        decision.resolved_by = actor
        decision.resolved_at = clock.now()
        decision.detail = {**decision.detail, "resolution": {"supplier_id": supplier_id, "purchase_order_id": purchase_order_id}}
        decision.save(update_fields=["status", "note", "resolved_by", "resolved_at", "detail", "updated_at"])
        resolve_alerts("decision_pending", decision=decision)
    return decision


# --- monitor and tick -----------------------------------------------------------------------


def run_monitor() -> dict:
    """Recomputes each open order's risk and opens or resolves alerts. Called by the tick."""
    from operations.services import compute_critical_path

    now = clock.now()
    today = clock.today()
    config = Config.load()
    counts = {"orders": 0, "alerts": 0}
    for order in Order.objects.exclude(status__in=("delivered", "cancelled")):
        compute_critical_path(order)
        counts["orders"] += 1
        if order.risk == "in_danger":
            open_alert("order_in_danger", order=order, text=f"La orden {order.code} de {order.customer.name} llegaría después de lo prometido ({order.risk_reason.lower()})")
        else:
            resolve_alerts("order_in_danger", order=order)

    for po in PurchaseOrder.objects.filter(status__in=PurchaseOrder.OPEN_STATUSES).select_related("supplier"):
        latest = po.progress_reports.order_by("-reported_at").first()
        stalled = po.next_follow_up_at and po.next_follow_up_at < now - timedelta(hours=po.supplier.follow_up_every_hours) and (
            latest is None or latest.reported_at < po.next_follow_up_at
        )
        if stalled:
            open_alert("stalled_purchase_order", purchase_order=po, text=f"{po.supplier.name} no reporta avance del pedido {po.code}")
        else:
            resolve_alerts("stalled_purchase_order", purchase_order=po)
        if po.committed_on and po.committed_on < today and po.status != "delivered":
            open_alert("delay", purchase_order=po, text=f"El pedido {po.code} venció el {po.committed_on:%d/%m} sin entrega")
        else:
            resolve_alerts("delay", purchase_order=po)
        for payment in po.payments.filter(paid_at__isnull=True):
            if payment.is_overdue:
                open_alert("payment_due", purchase_order=po, text=f"Pago {payment.get_kind_display().lower()} del pedido {po.code} vencido")

    Alert.objects.filter(kind__in=("delay", "stalled_purchase_order", "no_response"), status__in=("open", "acknowledged")).exclude(
        purchase_order__status__in=PurchaseOrder.OPEN_STATUSES
    ).update(status="resolved", resolved_at=now)

    for decision in Decision.objects.filter(status="pending", created_at__lt=timezone.now() - timedelta(hours=config.decision_pending_hours)):
        open_alert("decision_pending", decision=decision, text=f"Decisión sin resolver: {decision.summary}")
    counts["alerts"] = Alert.objects.filter(status="open").count()
    return counts
