"""Inventory endpoints: stock, committed by open orders and what is available."""

from decimal import Decimal

import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import Material
from operations.models import Order, Requirement
from tests.scenario import build
from tests.test_consolidated import catalogue  # noqa: F401


@pytest.fixture
def scenario(db, sales):
    data = build(owner=sales)
    fabric = Material.objects.get(sku="TEL-ALG-20-1")  # stock 120
    Requirement.objects.create(order=data["order"], kind="material", material=fabric, qty_needed=250, qty_from_stock=100)
    closed = Order.objects.create(
        code="CP-2026-0000", customer=data["customer"], brand=data["brand"], status="delivered", issued_on="2026-09-01", promised_on="2026-09-20"
    )
    Requirement.objects.create(order=closed, kind="material", material=fabric, qty_needed=50, qty_from_stock=50)  # Not committed any more.
    Material.objects.create(sku="BOT-01", name="Botón", kind="button", unit="unit", stock=5000)
    data["fabric"] = fabric
    return data


@pytest.mark.django_db
def test_materials_list_for_manager_and_production(scenario, manager_client, production):
    body = manager_client.get("/api/materials/").json()
    assert [m["sku"] for m in body] == ["BOT-01", "TEL-ALG-20-1"]  # by kind, then name
    fabric = body[1]
    assert fabric["stock"] == "120.00" and fabric["committed"] == "100.00" and fabric["available"] == "20.00"
    assert fabric["kind_display"] == "Tela" and fabric["unit_display"] == "kg"
    assert body[0]["committed"] == "0.00" and body[0]["available"] == "5000.00"
    production_client = APIClient()
    production_client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.get_or_create(user=production)[0].key}")
    assert production_client.get("/api/materials/").status_code == 200
    assert production_client.get("/api/materials/?kind=button").json()[0]["sku"] == "BOT-01"
    assert [m["sku"] for m in production_client.get("/api/materials/?q=algod").json()] == ["TEL-ALG-20-1"]


@pytest.mark.django_db
def test_materials_are_hidden_from_sales(scenario, sales_client, anonymous_client):
    assert sales_client.get("/api/materials/").status_code == 403
    assert sales_client.get(f"/api/materials/{scenario['fabric'].id}/").status_code == 403
    assert anonymous_client.get("/api/materials/").status_code == 401


@pytest.mark.django_db
def test_material_detail_lists_open_requirements(scenario, manager_client):
    response = manager_client.get(f"/api/materials/{scenario['fabric'].id}/")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] == "20.00"
    assert [r["order_code"] for r in body["requirements"]] == ["CP-2026-0001"]
    requirement = body["requirements"][0]
    assert requirement["qty_needed"] == "250.00" and requirement["qty_from_stock"] == "100.00" and requirement["qty_to_order"] == "150.00"
    assert requirement["status"] == "sourcing" and requirement["status_display"]
    assert manager_client.get("/api/materials/999999/").status_code == 404


@pytest.mark.django_db
def test_available_never_goes_negative_after_breakdowns(manager_client, sales, scenario):
    from operations import services

    payload = {"code": "CP-2026-0101", "customer": "Caja Piura", "brand": "UNICRACK", "promised_on": __import__("datetime").date(2026, 11, 10), "items": [{"product": "POLO-ESC-01", "quantity": 2000, "unit_price": "18.00"}]}
    services.register_order(payload, actor=sales)  # needs 500 kg of a 120 kg stock with 100 already reserved
    row = next(m for m in manager_client.get("/api/materials/").json() if m["sku"] == "TEL-ALG-20-1")
    assert row["committed"] == "120.00" and row["available"] == "0.00"


@pytest.mark.django_db
def test_to_order_and_incoming_say_when_a_material_goes_out_to_buy(catalogue, sales, production, manager):
    """Oscar, 10/10 00:00: the inventory shows what is still to buy (the "Por pedir" number) and
    the live purchase orders that will bring each material."""
    from datetime import date
    from decimal import Decimal

    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from operations import services
    from operations.models import PurchaseOrder, PurchaseOrderItem
    from tests.test_consolidated import order

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.get_or_create(user=production)[0].key}")
    fabric = catalogue["fabric"]  # jersey in kg, nothing in stock, 0.25 kg per polo
    a = order("CP-2026-0401", "Caja Piura", 1600, date(2026, 11, 20), sales)  # 400 kg open
    b = order("CP-2026-0402", "AIDER", 2400, date(2026, 11, 25), sales)  # 600 kg, covered below
    services.confirm_order(a, actor=production)
    services.confirm_order(b, actor=production)
    approved = PurchaseOrder.objects.create(code="PI-0950", supplier=catalogue["textil"], status="approved", internal_due_on=date(2026, 11, 1))
    PurchaseOrderItem.objects.create(
        purchase_order=approved, requirement=b.requirements.get(kind="material", material=fabric), quantity=Decimal("600"), unit_price=Decimal("8.00"), qty_delivered=Decimal("200")
    )

    with CaptureQueriesContext(connection) as first:
        rows = {m["sku"]: m for m in client.get("/api/materials/").json()}
    assert rows["TEL-20"]["to_order"] == "400.00"
    assert rows["TEL-20"]["incoming"] == [{"id": approved.id, "code": "PI-0950", "status": "approved", "status_display": "Aprobado", "qty_pending": "400.00"}]
    assert rows["BOT-NX"]["incoming"] == []
    # The same number as "Por pedir", material by material.
    pending = {g["material"]["sku"]: g["total_to_order"] for g in services.pending_purchases(with_prices=False)}
    assert {sku: row["to_order"] for sku, row in rows.items()} == {sku: pending.get(sku, "0.00") for sku in rows}

    detail = client.get(f"/api/materials/{fabric.id}/").json()
    assert detail["to_order"] == "400.00" and detail["incoming"][0]["qty_pending"] == "400.00" and detail["requirements"]

    # No query per material, requirement or purchase order: more of them, same number of queries.
    for n, customer in ((3, "Caja Piura"), (4, "AIDER")):
        extra = order(f"CP-2026-040{n}", customer, 100 * n, date(2026, 12, n), sales)
        services.confirm_order(extra, actor=production)
    services.generate_purchase_orders(actor=production)
    with CaptureQueriesContext(connection) as second:
        client.get("/api/materials/")
    assert len(second) == len(first), [q["sql"][:80] for q in second.captured_queries]
    sales_client = APIClient()
    sales_client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.get_or_create(user=sales)[0].key}")
    assert sales_client.get("/api/materials/").status_code == 403  # manager and production only, as before
