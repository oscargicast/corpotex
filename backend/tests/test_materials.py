"""Inventory endpoints: stock, committed by open orders and what is available."""

from decimal import Decimal

import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import Material
from operations.models import Order, Requirement
from tests.scenario import build


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
