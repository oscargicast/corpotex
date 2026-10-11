"""Order CRUD by role (ADR 0025 B): edit, cancel, and the catalogue lists for the form."""

from datetime import date
from decimal import Decimal

import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import Brand, Customer, Product, User
from operations import services
from operations.models import Order, PurchaseOrder, Requirement
from tests.test_consolidated import catalogue, order  # noqa: F401


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.get_or_create(user=user)[0].key}")
    return client


@pytest.fixture
def other_sales(db):
    from django.contrib.auth.models import Group

    from core.models import ROLE_GROUPS

    user = User.objects.create_user(username="comercial2", password="x", first_name="Vale")
    user.groups.add(Group.objects.get_or_create(name=ROLE_GROUPS["sales"])[0])
    return user


@pytest.mark.django_db
def test_catalogue_lists_for_the_form(catalogue, sales_client):
    Product.objects.filter(code="UNI-POL-01").update(brand=Brand.objects.get(name="UNICRACK"))
    customers = sales_client.get("/api/customers/").json()
    assert [c["name"] for c in customers] == ["AIDER", "Caja Piura"]
    assert set(customers[0]) == {"id", "name", "ruc", "kind", "kind_display", "address", "lat", "lng"}
    assert [c["name"] for c in sales_client.get("/api/customers/?q=aid").json()] == ["AIDER"]
    products = sales_client.get("/api/products/").json()
    assert products[0]["code"] == "UNI-POL-01" and products[0]["brand"] == {"id": Brand.objects.get(name="UNICRACK").id, "name": "UNICRACK"}
    assert set(products[0]) == {"id", "code", "name", "brand", "image"}
    assert sales_client.get("/api/products/?brand=nexo").json() == []
    assert [p["code"] for p in sales_client.get("/api/products/?q=pol").json()] == ["UNI-POL-01"]


@pytest.mark.django_db
def test_sales_edits_own_order_and_the_breakdown_follows(catalogue, sales, sales_client):
    created = order("CP-2026-0301", "Caja Piura", 400, date(2026, 11, 10), sales)
    assert created.status == "broken_down" and created.requirements.get(kind="workshop").qty_needed == 400
    body = {
        "promised_on": "2026-11-15", "notes": "Entregar en la agencia",
        "items": [{"product": "UNI-POL-01", "quantity": 100, "sizes": {"M": 100}, "unit_price": "28.00"}],
    }
    response = sales_client.patch(f"/api/orders/{created.id}/", body, format="json")
    assert response.status_code == 200, response.content
    data = response.json()
    assert data["promised_on"] == "2026-11-15" and data["notes"] == "Entregar en la agencia" and data["warnings"] == []
    assert data["total_units"] == 100 and created.requirements.get(kind="workshop").qty_needed == 100
    assert created.requirements.get(kind="material", material__sku="BOT-NX").qty_needed == Decimal("300")
    assert sales_client.patch(f"/api/orders/{created.id}/", {"customer": "Fantasma"}, format="json").status_code == 400
    assert sales_client.patch(f"/api/orders/{created.id}/", {"items": [{"product": "NOPE", "quantity": 1, "unit_price": "1"}]}, format="json").status_code == 400


@pytest.mark.django_db
def test_edit_permissions_by_role_and_status(catalogue, sales, production, manager, other_sales, sales_client, manager_client):
    created = order("CP-2026-0301", "Caja Piura", 400, date(2026, 11, 10), sales)
    assert client_for(other_sales).patch(f"/api/orders/{created.id}/", {"notes": "x"}, format="json").status_code == 403
    assert client_for(production).patch(f"/api/orders/{created.id}/", {"notes": "x"}, format="json").status_code == 403
    services.confirm_order(created, actor=production)
    assert sales_client.patch(f"/api/orders/{created.id}/", {"notes": "x"}, format="json").status_code == 403
    # The manager edits a confirmed order: the ordered workshop requirement stays and is reported.
    response = manager_client.patch(f"/api/orders/{created.id}/", {"items": [{"product": "UNI-POL-01", "quantity": 500, "unit_price": "28.00"}]}, format="json")
    assert response.status_code == 200, response.content
    assert response.json()["warnings"] and "Polo" in response.json()["warnings"][0]
    workshop = created.requirements.get(kind="workshop")
    assert workshop.qty_needed == 400 and workshop.status == "ordered"  # untouched: already in a purchase order
    assert created.requirements.get(kind="material", material__sku="BOT-NX").qty_needed == Decimal("1500")  # rebuilt
    assert created.requirements.get(kind="material", material__sku="BOT-NX").status == "open"


@pytest.mark.django_db
def test_cancel_by_role_and_status(catalogue, sales, production, manager, other_sales, sales_client, manager_client):
    mine = order("CP-2026-0301", "Caja Piura", 400, date(2026, 11, 10), sales)
    assert client_for(other_sales).post(f"/api/orders/{mine.id}/cancel/", {}, format="json").status_code == 403
    assert client_for(production).post(f"/api/orders/{mine.id}/cancel/", {}, format="json").status_code == 403
    cancelled = sales_client.post(f"/api/orders/{mine.id}/cancel/", {"reason": "el cliente desistió"}, format="json")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["status_history"][-1]["note"] == "el cliente desistió"

    confirmed = order("CP-2026-0302", "AIDER", 400, date(2026, 11, 12), sales)
    services.confirm_order(confirmed, actor=production)
    assert sales_client.post(f"/api/orders/{confirmed.id}/cancel/", {}, format="json").status_code == 403
    response = manager_client.post(f"/api/orders/{confirmed.id}/cancel/", {}, format="json")
    assert response.status_code == 200 and response.json()["status"] == "cancelled"
    assert set(PurchaseOrder.objects.filter(items__requirement__order=confirmed).values_list("status", flat=True)) == {"cancelled"}
    from manager.models import Decision

    assert not Decision.objects.filter(status="pending", kind="approve_assignment", purchase_orders__items__requirement__order=confirmed).exists()

    producing = order("CP-2026-0303", "AIDER", 100, date(2026, 11, 20), sales)
    Order.objects.filter(pk=producing.pk).update(status="in_production")
    assert manager_client.post(f"/api/orders/{producing.id}/cancel/", {}, format="json").status_code == 400


@pytest.mark.django_db
def test_form_payload_without_code_or_prices_creates_the_order(catalogue, sales_client, manager_client):
    """The dashboard form (F4.3) knows neither the sales system's code nor the sale price."""
    body = {"customer": "Caja Piura", "brand": "UNICRACK", "promised_on": "2026-11-20", "notes": "Para el aniversario",
            "items": [{"product": "UNI-POL-01", "quantity": 120, "color": "azul", "customization": "embroidery"}]}
    first = sales_client.post("/api/orders/", body, format="json")
    assert first.status_code == 201, first.content
    data = first.json()
    assert data["code"].startswith("CP-2026-") and data["notes"] == "Para el aniversario" and "total_amount" not in data  # prices are manager-only
    assert data["status"] == "broken_down" and data["requirements"]
    second = sales_client.post("/api/orders/", body, format="json")
    assert second.status_code == 201 and second.json()["code"] != data["code"]  # No code: never the idempotent 200.
    numbers = sorted(int(c.rsplit("-", 1)[1]) for c in Order.objects.filter(code__startswith="CP-2026-").values_list("code", flat=True))
    assert numbers[-1] == numbers[-2] + 1
    manager_view = manager_client.get(f"/api/orders/{data['id']}/").json()
    assert manager_view["items"][0]["unit_price"] is None and manager_view["total_amount"] == "0.00"
