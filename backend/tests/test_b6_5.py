"""B6.5: bulk breakdown, merging into a suggested purchase order, list filters and search."""

from datetime import date
from decimal import Decimal

import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from manager.models import Decision
from operations import services
from operations.models import Order, PurchaseOrder
from tests.test_consolidated import catalogue, order  # noqa: F401  (fixtures and helpers)


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.get_or_create(user=user)[0].key}")
    return client


@pytest.mark.django_db
def test_bulk_breakdown(catalogue, sales, production, sales_client):
    a = order("CP-2026-0301", "Caja Piura", 100, date(2026, 11, 10), sales)
    b = order("CP-2026-0302", "AIDER", 100, date(2026, 11, 12), sales)
    Order.objects.filter(pk__in=[a.pk, b.pk]).update(status="registered")  # As the sales system would leave them.
    production_client = client_for(production)
    assert sales_client.post("/api/orders/break-down/", {}, format="json").status_code == 403
    response = production_client.post("/api/orders/break-down/", {}, format="json")
    assert response.status_code == 200
    assert response.json() == {"broken_down": ["CP-2026-0301", "CP-2026-0302"], "skipped": []}
    assert set(Order.objects.filter(pk__in=[a.pk, b.pk]).values_list("status", flat=True)) == {"broken_down"}
    again = production_client.post("/api/orders/break-down/", {"order_ids": [a.id, 999999]}, format="json").json()
    assert again["broken_down"] == [] and again["skipped"] == [{"code": "CP-2026-0301", "reason": "ya está en estado «Con ficha técnica»"}, {"code": "999999", "reason": "no existe"}]


@pytest.mark.django_db
def test_generate_adds_new_requirements_to_the_suggested_purchase_order(catalogue, sales, production, manager, manager_client):
    a = order("CP-2026-0301", "Caja Piura", 400, date(2026, 11, 10), sales)  # 1100 buttons after stock
    services.confirm_order(a, actor=production)
    first = services.generate_purchase_orders([catalogue["buttons"].id], actor=production)
    po = first["created"][0]
    decision = first["decision"]
    assert po.items.count() == 1 and po.internal_due_on == date(2026, 11, 5)

    b = order("CP-2026-0302", "AIDER", 500, date(2026, 11, 2), sales)  # 1500 buttons, earlier deadline
    services.confirm_order(b, actor=production)
    second = services.generate_purchase_orders([catalogue["buttons"].id], actor=production)
    assert [p.pk for p in second["created"]] == [po.pk]  # The same purchase order, no second one.
    assert PurchaseOrder.objects.filter(supplier__kind="material").count() == 1
    po.refresh_from_db()
    assert po.items.count() == 2 and sum(i.quantity for i in po.items.all()) == Decimal("2600") and po.internal_due_on == date(2026, 10, 28)
    assert second["decision"].pk == decision.pk
    assert Decision.objects.filter(kind="approve_assignment", status="pending", purchase_orders__supplier__kind="material").distinct().count() == 1
    decision.refresh_from_db()
    entry = next(e for e in decision.detail["proposal"] if e["purchase_order_code"] == po.code)
    assert entry["quantity"] == "2600.00" and {o["code"] for o in entry["orders"]} == {"CP-2026-0301", "CP-2026-0302"} and entry["merged"] is True
    detail = manager_client.get(f"/api/purchase-orders/{po.id}/").json()
    assert {o["code"] for o in detail["orders"]} == {"CP-2026-0301", "CP-2026-0302"} and detail["total_units"] == "2600.00"
    # Once approved, a later requirement gets its own purchase order.
    from manager.services import resolve_decision

    resolve_decision(decision, action="approve", actor=manager)
    c = order("CP-2026-0303", "AIDER", 100, date(2026, 11, 20), sales)
    services.confirm_order(c, actor=production)
    third = services.generate_purchase_orders([catalogue["buttons"].id], actor=production)
    assert third["created"][0].pk != po.pk and PurchaseOrder.objects.filter(supplier__kind="material").count() == 2


@pytest.mark.django_db
def test_list_filters_accept_status_lists_and_search(catalogue, sales, production, manager_client):
    a = order("CP-2026-0301", "Caja Piura", 100, date(2026, 11, 10), sales)
    b = order("CP-2026-0310", "AIDER", 100, date(2026, 11, 12), sales)
    services.confirm_order(b, actor=production)
    assert {o["code"] for o in manager_client.get("/api/orders/?status=broken_down,confirmed").json()} == {"CP-2026-0301", "CP-2026-0310"}
    assert [o["code"] for o in manager_client.get("/api/orders/?status=confirmed").json()] == ["CP-2026-0310"]
    assert [o["code"] for o in manager_client.get("/api/orders/?q=031").json()] == ["CP-2026-0310"]
    assert [o["code"] for o in manager_client.get("/api/orders/?q=cp-2026-030").json()] == ["CP-2026-0301"]
    po = PurchaseOrder.objects.get(items__requirement__order=b)
    assert [p["code"] for p in manager_client.get(f"/api/purchase-orders/?q={po.code[:4].lower()}").json()] == [po.code]
    assert [p["code"] for p in manager_client.get("/api/purchase-orders/?q=0310").json()] == [po.code]  # by order code
    assert manager_client.get("/api/purchase-orders/?status=suggested,approved&q=zzz").json() == []
    assert [p["code"] for p in manager_client.get("/api/purchase-orders/?status=suggested,approved").json()] == [po.code]
