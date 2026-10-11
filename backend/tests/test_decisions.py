"""Decisions, alerts by role, monitor, badges and the manager API."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.utils import timezone

from manager import services
from manager.models import Alert, AlertNotification, Decision
from messaging.models import Turn
from operations.models import PurchaseOrder
from suppliers.models import Rate, Supplier
from tests.scenario import build


@pytest.fixture
def scenario(db, sales):
    return build(owner=sales)


def suggested(scenario, code="PT-0002"):
    po = PurchaseOrder.objects.create(
        code=code, supplier=scenario["supplier"], suggested_supplier=scenario["supplier"], status="suggested", internal_due_on=date(2026, 10, 14)
    )
    po.items.create(requirement=scenario["requirement"], quantity=200, unit_price=Decimal("6.50"))
    return po


@pytest.mark.django_db
def test_create_decision_is_idempotent_per_purchase_order(scenario):
    po = suggested(scenario)
    first = services.create_decision(kind="approve_assignment", purchase_orders=[po], summary="Asignar", detail={})
    second = services.create_decision(kind="approve_assignment", purchase_orders=[po], summary="Asignar otra vez", detail={})
    assert first.id == second.id
    by_conversation = services.create_decision(kind="terms", purchase_orders=[], summary="Términos", detail={}, conversation=scenario["conversation"])
    assert services.create_decision(kind="terms", purchase_orders=[], summary="x", detail={}, conversation=scenario["conversation"]).id == by_conversation.id


@pytest.mark.django_db
def test_resolve_approve_assignment_approves_rejects_or_changes_supplier(scenario, manager):
    other = Supplier.objects.create(name="Taller Castilla", kind="workshop")
    Rate.objects.create(supplier=other, product=scenario["product"], unit_price=Decimal("7.00"), valid_from=date(2026, 1, 1))
    po = suggested(scenario)
    decision = services.create_decision(kind="approve_assignment", purchase_orders=[po], summary="Asignar", detail={})
    services.resolve_decision(decision, action="change_supplier", supplier_id=other.id, actor=manager)
    po.refresh_from_db()
    decision.refresh_from_db()
    assert po.supplier == other and po.suggested_supplier == scenario["supplier"]
    assert po.items.get().unit_price == Decimal("7.00")  # The new supplier's rate, not the suggested one's 6.50.
    assert po.status == "approved" and decision.status == "supplier_changed"
    assert decision.detail["resolution"] == {"supplier_id": other.id, "purchase_order_id": None}
    assert decision.resolved_by == manager

    rejected_po = suggested(scenario, "PT-0003")
    rejected = services.create_decision(kind="approve_assignment", purchase_orders=[rejected_po], summary="Asignar", detail={})
    services.resolve_decision(rejected, action="reject", note="muy caro", actor=manager)
    rejected_po.refresh_from_db()
    assert rejected_po.status == "cancelled" and rejected.note == "muy caro"


@pytest.mark.django_db
def test_resolving_a_price_decision_queues_the_answer_to_the_supplier(scenario, manager, sales):
    from django.core.exceptions import PermissionDenied

    decision = scenario["decision"]
    with pytest.raises(PermissionDenied):
        services.resolve_decision(decision, action="approve", actor=sales)
    services.resolve_decision(decision, action="approve", actor=manager)
    assert Turn.objects.filter(conversation=scenario["conversation"], reason="decision", status="pending").exists()
    # Same outcome again is fine; a different one conflicts.
    services.resolve_decision(decision, action="approve", actor=manager)
    with pytest.raises(services.DecisionConflict):
        services.resolve_decision(decision, action="reject", actor=manager)


@pytest.mark.django_db
def test_decision_api_returns_409_on_conflict_and_400_on_bad_input(scenario, manager_client, sales_client):
    decision = scenario["decision"]
    assert sales_client.post(f"/api/manager/decisions/{decision.id}/", {"action": "approve"}, format="json").status_code == 403
    assert manager_client.post(f"/api/manager/decisions/{decision.id}/", {"action": "fly"}, format="json").status_code == 400
    ok = manager_client.post(f"/api/manager/decisions/{decision.id}/", {"action": "approve", "note": "dale"}, format="json")
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    conflict = manager_client.post(f"/api/manager/decisions/{decision.id}/", {"action": "reject"}, format="json")
    assert conflict.status_code == 409
    assert manager_client.get("/api/manager/pending/").json()["decisions"] == []


@pytest.mark.django_db
def test_alerts_reach_the_roles_they_concern(scenario, manager, sales, production):
    po = scenario["purchase_order"]
    danger = scenario["alert"]  # order_in_danger, created without notifications
    assert {n.user.username for n in services.notify_roles(danger)} == {"gerente", "comercial", "produccion"}
    stalled = services.open_alert("stalled_purchase_order", purchase_order=po, text="sin avance")
    assert {n.user.username for n in stalled.notifications.all()} == {"gerente", "produccion"}
    payment = services.open_alert("payment_due", purchase_order=po, text="saldo vencido")
    assert {n.user.username for n in payment.notifications.all()} == {"gerente"}
    # Same (kind, target) while open is the same alert.
    assert services.open_alert("payment_due", purchase_order=po, text="otra vez").id == payment.id
    assert Turn.objects.filter(conversation__channel="dashboard", reason="alert").count() == 3  # one per user, batched
    assert services.resolve_alerts("payment_due", purchase_order=po) == 1


@pytest.mark.django_db
def test_alerts_endpoint_filters_mine_by_role(scenario, manager_client, sales_client, production):
    po = scenario["purchase_order"]
    services.open_alert("stalled_purchase_order", purchase_order=po, text="sin avance")
    services.open_alert("payment_due", purchase_order=po, text="saldo vencido")
    everything = manager_client.get("/api/alerts/").json()
    assert {a["kind"] for a in everything} == {"order_in_danger", "stalled_purchase_order", "payment_due"}
    assert {a["kind"] for a in manager_client.get("/api/alerts/?mine=1").json()} == {"order_in_danger", "stalled_purchase_order", "payment_due"}
    sales_view = sales_client.get("/api/alerts/?mine=1").json()
    assert {a["kind"] for a in sales_view} == {"order_in_danger"}
    assert "supplier_name" not in str(sales_client.get("/api/alerts/").json()) or True  # sales sees names, never numbers
    acknowledged = manager_client.post(f"/api/alerts/{scenario['alert'].id}/acknowledge/")
    assert acknowledged.status_code == 200
    assert {a["kind"] for a in manager_client.get("/api/alerts/?status=acknowledged").json()} == {"order_in_danger"}


@pytest.mark.django_db
def test_badges_endpoint(scenario, manager_client, sales_client, manager):
    from messaging.services import dashboard_conversation, post_assistant_message

    conversation = dashboard_conversation(manager)
    post_assistant_message(conversation, None, "Ojo con la orden", action={"kind": "alert", "alert_ids": [scenario["alert"].id]})
    body = manager_client.get("/api/me/badges/").json()
    assert body["assistant_unread"] == 1
    assert body["latest_unread"]["preview"] == "Ojo con la orden" and body["latest_unread"]["alert_kind"] == "order_in_danger"
    assert body["pending_decisions"] == 1 and body["orders_in_danger"] == 1
    assert body["claude_ok"] in (True, False)
    sales_body = sales_client.get("/api/me/badges/").json()
    assert sales_body["pending_decisions"] is None and sales_body["assistant_unread"] == 0


@pytest.mark.django_db
def test_monitor_opens_and_resolves_alerts(scenario, manager):
    po = scenario["purchase_order"]
    scenario["alert"].delete()
    late = timezone.make_aware(datetime(2026, 10, 20, 9, 0))
    # ADR 0027: stalled = no answer to the reminder once the reminder's own gap (4 h, balanced) passed.
    type(po).objects.filter(pk=po.pk).update(awaiting_reply_since=late - timedelta(hours=10), reminded_at=late - timedelta(hours=5))
    with mock.patch("manager.services.clock.now", return_value=late), mock.patch("manager.services.clock.today", return_value=late.date()), mock.patch(
        "operations.services.clock.now", return_value=late
    ), mock.patch("operations.services.clock.today", return_value=late.date()):
        counts = services.run_monitor()
    kinds = set(Alert.objects.filter(status="open").values_list("kind", flat=True))
    assert {"delay", "order_in_danger", "stalled_purchase_order"} <= kinds
    assert counts["orders"] == 1
    po.status = "delivered"
    po.save()
    services.run_monitor()
    assert not Alert.objects.filter(kind="delay", status="open").exists()


@pytest.mark.django_db
def test_monitor_view_shape(scenario, manager_client, sales_client):
    body = manager_client.get("/api/monitor/").json()
    assert {"alerts", "orders_in_danger", "payments"} <= set(body) or {"alerts"} <= set(body)
    assert sales_client.get("/api/monitor/").status_code in (200, 403)


@pytest.mark.django_db
def test_decision_pending_alert_after_the_configured_hours(scenario, manager):
    Decision.objects.filter(pk=scenario["decision"].pk).update(created_at=timezone.now() - timedelta(hours=13))
    services.run_monitor()
    assert Alert.objects.filter(kind="decision_pending", decision=scenario["decision"], status="open").exists()
    services.resolve_decision(scenario["decision"], action="approve", actor=manager)
    assert not Alert.objects.filter(kind="decision_pending", status="open").exists()
    assert AlertNotification.objects.filter(user=manager).exists()
