"""The status timeline (10/10 21:40): one row per transition, with who did it."""

from datetime import date
from decimal import Decimal

import pytest

from operations import services
from operations.models import PurchaseOrder, StatusChange
from suppliers.models import Rate, Supplier
from tests.scenario import build


@pytest.fixture
def scenario(db, sales):
    data = build(owner=sales)
    other = Supplier.objects.create(name="Taller Castilla", kind="workshop", city="Piura", weekly_capacity=2000)
    Rate.objects.create(supplier=other, product=data["product"], unit_price=Decimal("7.00"), valid_from=date(2026, 1, 1))
    return data


def payload(code="CP-2026-0002"):
    return {"code": code, "customer": "Caja Piura", "brand": "UNICRACK", "promised_on": date(2026, 10, 30), "items": [{"product": "POLO-ESC-01", "quantity": 100, "unit_price": "18.00"}]}


@pytest.mark.django_db
def test_order_and_purchase_order_timelines_follow_the_flow(scenario, sales, production, manager):
    order, _ = services.register_order(payload(), actor=sales)
    services.confirm_order(order, actor=production)
    po = PurchaseOrder.objects.filter(items__requirement__order=order, supplier__kind="workshop").get()
    services.approve_purchase_orders([po], actor=manager)
    services.confirm_purchase_order(po, unit_price="6.50", committed_on=date(2026, 10, 20))
    services.record_progress(po, units_done=50, message_id=None, actor=None)  # public page
    services.record_delivery(po, qty_received=100, actor=production)

    order_history = [(c.status, c.actor) for c in order.status_changes.all()]
    assert order_history == [("registered", "comercial"), ("broken_down", "system"), ("confirmed", "produccion"), ("sourcing", "gerente"), ("in_production", "system")]
    po_history = [(c.status, c.actor) for c in po.status_changes.all()]
    assert po_history == [("suggested", "system"), ("approved", "gerente"), ("confirmed", "agent"), ("in_progress", "system"), ("delivered", "produccion")]
    ats = [c.at for c in po.status_changes.all()]
    assert ats == sorted(ats)
    assert "Calificación" in po.status_changes.last().note


@pytest.mark.django_db
def test_set_status_writes_nothing_when_unchanged(scenario):
    po = scenario["purchase_order"]
    services.set_status(po, po.status, actor="agent")
    assert StatusChange.objects.filter(purchase_order=po).count() == 0
    services.set_status(po, "negotiating", actor="agent", note="x")
    po.refresh_from_db()
    assert po.status == "negotiating" and StatusChange.objects.filter(purchase_order=po).count() == 1


@pytest.mark.django_db
def test_status_history_in_the_api_for_every_role(scenario, sales_client, manager_client, manager):
    po = scenario["purchase_order"]
    services.cancel_by_supplier(po, reason="se me enfermó la gente")
    body = sales_client.get(f"/api/purchase-orders/{po.id}/").json()
    assert body["status_history"][-1]["status"] == "cancelled_by_supplier"
    assert body["status_history"][-1]["status_display"] == po.get_status_display()
    assert body["status_history"][-1]["actor"] == "agent" and body["status_history"][-1]["note"] == "se me enfermó la gente"
    assert set(body["status_history"][-1]) == {"status", "status_display", "at", "actor", "note"}
    order = manager_client.get(f"/api/orders/{scenario['order'].id}/").json()
    assert "status_history" in order and isinstance(order["status_history"], list)
