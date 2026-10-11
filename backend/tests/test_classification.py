"""B6.4: classification of made-to-order items with Jev (mocked) and Claude (mocked)."""

from datetime import date
from decimal import Decimal
from unittest import mock

import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import Material, Product, ProductMaterial
from operations import classify, jev, services
from operations.models import Order
from tests.test_consolidated import catalogue  # noqa: F401


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.get_or_create(user=user)[0].key}")
    return client


@pytest.fixture
def order_with_new_garment(catalogue, sales):
    payload = {"customer": "Caja Piura", "brand": "UNICRACK", "promised_on": date(2026, 11, 30),
               "items": [{"product": "UNI-POL-01", "quantity": 50},
                         {"description": "Casaca impermeable azul con capucha, logo bordado", "quantity": 40, "color": "azul", "customization": "bordado"}]}
    return services.register_order(payload, actor=sales)[0]


CLAUDE_PROPOSAL = {
    "product": {"existing_code": None, "code": "UNI-CAS-01", "name": "Casaca impermeable", "brand": "UNICRACK"},
    "materials": [
        {"existing_sku": "TEL-20", "sku": "TEL-20", "name": "Jersey 20/1", "kind": "fabric", "unit": "kg", "qty_per_unit": 0.6},
        {"existing_sku": None, "sku": "CIE-NYL-60", "name": "Cierre nylon 60 cm", "kind": "zipper", "unit": "unit", "qty_per_unit": 1},
    ],
    "confidence": 0.8,
}


@pytest.mark.django_db
def test_classify_with_claude_only(order_with_new_garment, production, sales_client):
    order = order_with_new_garment
    production_client = client_for(production)
    assert sales_client.post(f"/api/orders/{order.id}/classify/", {}, format="json").status_code == 403
    with mock.patch.object(classify, "complete_sync", return_value=CLAUDE_PROPOSAL) as complete, mock.patch.object(jev, "choose", return_value=None):
        response = production_client.post(f"/api/orders/{order.id}/classify/", {}, format="json")
    assert response.status_code == 200, response.content
    body = response.json()
    assert complete.call_count == 1 and "Casaca impermeable azul" in complete.call_args.args[0] and "UNI-POL-01" in complete.call_args.args[0]
    assert len(body["items"]) == 1  # only the item without product
    item = body["items"][0]
    assert item["product"] == {"new": {"code": "UNI-CAS-01", "name": "Casaca impermeable", "brand": "UNICRACK"}} and item["confidence"] == 0.8
    assert item["materials"][0] == {"sku": "TEL-20", "name": "Jersey 20/1", "material_id": Material.objects.get(sku="TEL-20").id, "qty_per_unit": "0.6", "unit": "kg", "confidence": 0.8}
    assert item["materials"][1]["new"] == {"sku": "CIE-NYL-60", "name": "Cierre nylon 60 cm", "kind": "zipper", "unit": "unit"}


@pytest.mark.django_db
def test_jev_picks_a_catalogue_product_without_calling_claude(order_with_new_garment, manager_client):
    order = order_with_new_garment
    polo = Product.objects.get(code="UNI-POL-01")
    with mock.patch.object(classify, "complete_sync") as complete, mock.patch.object(jev, "choose", return_value=("UNI-POL-01", 0.91, {"UNI-POL-01": 0.91, "nuevo": 0.09})):
        body = manager_client.post(f"/api/orders/{order.id}/classify/", {}, format="json").json()
    complete.assert_not_called()
    item = body["items"][0]
    assert item["product"] == {"existing_id": polo.id, "code": "UNI-POL-01", "name": "Polo"} and item["confidence"] == 0.91
    assert {m["sku"] for m in item["materials"]} == {"BOT-NX", "TEL-20"}  # the catalogue BOM


@pytest.mark.django_db
def test_low_confidence_jev_falls_back_to_claude_and_jev_checks_materials(order_with_new_garment, manager_client):
    order = order_with_new_garment
    answers = iter([("nuevo", 0.55, {}), ("TEL-20", 0.9, {}), ("nuevo", 0.7, {})])
    with mock.patch.object(classify, "complete_sync", return_value=CLAUDE_PROPOSAL), mock.patch.object(jev, "choose", side_effect=lambda *a, **k: next(answers)):
        item = manager_client.post(f"/api/orders/{order.id}/classify/", {}, format="json").json()["items"][0]
    assert "new" in item["product"]
    assert item["materials"][0]["sku"] == "TEL-20" and item["materials"][0]["confidence"] == 0.9
    assert "new" in item["materials"][1] and item["materials"][1]["confidence"] == 0.7


@pytest.mark.django_db
def test_apply_creates_product_materials_and_breaks_down(order_with_new_garment, production, sales_client):
    order = order_with_new_garment
    item = order.items.get(product__isnull=True)
    body = {"items": [{"item_id": item.id, "product": {"new": {"code": "UNI-CAS-01", "name": "Casaca impermeable", "brand": "UNICRACK"}},
                       "materials": [{"sku": "TEL-20", "qty_per_unit": "0.6", "unit": "kg"},
                                     {"new": {"sku": "CIE-NYL-60", "name": "Cierre nylon 60 cm", "kind": "zipper", "unit": "unit"}, "qty_per_unit": "1", "unit": "unit"},
                                     {"new": {"sku": "ETQ-X", "name": "Etiqueta", "kind": "other", "unit": "unit"}, "qty_per_unit": "0", "unit": "unit"}]}]}
    assert sales_client.post(f"/api/orders/{order.id}/apply-classification/", body, format="json").status_code == 403
    response = client_for(production).post(f"/api/orders/{order.id}/apply-classification/", body, format="json")
    assert response.status_code == 200, response.content
    data = response.json()
    assert data["needs_classification"] is False and data["status"] == "broken_down"
    assert data["warnings"] == ["Etiqueta: cantidad por prenda vacía, no entra al desglose"]
    product = Product.objects.get(code="UNI-CAS-01")
    assert product.brand.name == "UNICRACK" and set(product.materials.values_list("material__sku", flat=True)) == {"TEL-20", "CIE-NYL-60"}
    zipper = Material.objects.get(sku="CIE-NYL-60")
    assert zipper.kind == "zipper" and zipper.stock == Decimal("0")
    assert ProductMaterial.objects.get(product=product, material__sku="TEL-20").qty_per_unit == Decimal("0.6")
    item.refresh_from_db()
    assert item.product == product
    assert order.requirements.filter(kind="material", material=zipper).exists() and order.requirements.filter(kind="workshop", product=product).exists()
    assert client_for(production).post(f"/api/orders/{order.id}/confirm/", {}, format="json").status_code == 200


@pytest.mark.django_db
def test_apply_with_existing_product_and_bad_item(order_with_new_garment, production):
    order = order_with_new_garment
    item = order.items.get(product__isnull=True)
    polo = Product.objects.get(code="UNI-POL-01")
    client = client_for(production)
    assert client.post(f"/api/orders/{order.id}/apply-classification/", {"items": [{"item_id": 999999, "product": {"existing_id": polo.id}}]}, format="json").status_code == 400
    response = client.post(f"/api/orders/{order.id}/apply-classification/", {"items": [{"item_id": item.id, "product": {"existing_id": polo.id}}]}, format="json")
    assert response.status_code == 200 and response.json()["needs_classification"] is False
    assert Product.objects.count() == 1  # nothing new created


@pytest.mark.django_db
def test_jev_is_off_without_a_key(settings):
    settings.TYPESAFE_API_KEY = ""
    assert jev.choose("x", {"a": "A"}) is None and jev.yes("x", "y") is None
    settings.TYPESAFE_API_KEY = "k"
    with mock.patch.object(jev, "_client", return_value=None):
        assert jev.choose("x", {"a": "A"}) is None
