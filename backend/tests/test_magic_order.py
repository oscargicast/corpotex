"""ADR 0028 (M1): classification while sales writes (`classify-draft`), and orders born broken down
when the form sends the confirmed `classification`."""

from decimal import Decimal
from unittest import mock

import pytest
from django.core.management import call_command
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import Material, Product
from operations import classify, jev
from operations.models import Order
from seed.loader import DATA_DIR
from tests.test_consolidated import catalogue  # noqa: F401

LINE = "300 polos deportivos azul marino, tallas 6 a 14"


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.get_or_create(user=user)[0].key}")
    return client


@pytest.mark.django_db
@pytest.mark.skipif(not (DATA_DIR / "products.json").exists(), reason="seed data not present")
def test_draft_of_a_catalogue_polo_on_the_seed(sales):
    call_command("seed_demo", verbosity=0)
    polo = Product.objects.get(code="UNI-POD-01")
    client = client_for(sales)
    body = {"brand": "UNICRACK", "items": [{"key": "l1", "description": LINE, "quantity": 300}]}
    orders, products = Order.objects.count(), Product.objects.count()

    # Jev recognises the catalogue product: no Claude call.
    with mock.patch.object(jev, "choose", return_value=("UNI-POD-01", 0.9, {})), mock.patch.object(classify, "complete_sync") as complete:
        response = client.post("/api/orders/classify-draft/", body, format="json")
    assert response.status_code == 200, response.content
    [line] = response.json()["items"]
    complete.assert_not_called()
    assert line["key"] == "l1" and line["status"] == "classified" and "item_id" not in line
    assert line["product"] == {"existing_id": polo.id, "code": "UNI-POD-01", "name": polo.name} and line["confidence"] == 0.9
    assert {m["sku"] for m in line["materials"]} == set(polo.materials.values_list("material__sku", flat=True))

    # Without Jev, Claude picks it: same answer, the catalogue's bill of materials.
    proposal = {"product": {"existing_code": "UNI-POD-01", "code": "UNI-POD-01", "name": "Polo", "brand": "UNICRACK"}, "materials": [], "confidence": 0.85}
    with mock.patch.object(jev, "choose", return_value=None), mock.patch.object(jev, "choose_many", return_value=None), mock.patch.object(
        classify, "complete_sync", return_value=proposal
    ) as complete:
        [line] = client.post("/api/orders/classify-draft/", body, format="json").json()["items"]
    assert complete.call_count == 1 and "Pedido para la marca UNICRACK" in complete.call_args.args[0]  # no customer in a draft
    assert line["product"]["existing_id"] == polo.id and line["confidence"] == 0.85
    assert (Order.objects.count(), Product.objects.count()) == (orders, products)  # a draft saves nothing


@pytest.mark.django_db
def test_short_lines_wait_and_a_model_failure_is_that_lines_error(catalogue, sales, production):
    body = {"brand": "UNICRACK", "customer": "Caja Piura", "items": [
        {"key": "short", "description": "polos", "quantity": 300},
        {"key": "noqty", "description": "Casaca cortavientos impermeable", "quantity": None},
        {"key": "boom", "description": "Casaca cortavientos impermeable", "quantity": 150},
    ]}
    with mock.patch.object(jev, "choose", return_value=None), mock.patch.object(classify, "complete_sync", side_effect=RuntimeError("model down")) as complete:
        response = client_for(production).post("/api/orders/classify-draft/", body, format="json")
    assert response.status_code == 200
    rows = {r["key"]: r for r in response.json()["items"]}
    assert rows["short"] == {"key": "short", "status": "pending"} and rows["noqty"] == {"key": "noqty", "status": "pending"}
    assert rows["boom"]["status"] == "error" and "model down" in rows["boom"]["detail"]
    assert complete.call_count == 1 and "Pedido de Caja Piura" in complete.call_args.args[0]
    assert client_for(sales).post("/api/orders/classify-draft/", {**body, "brand": "Fantasma"}, format="json").status_code == 400


def classified_payload(catalogue):
    polo = Product.objects.get(code="UNI-POL-01")
    return {
        "customer": "Caja Piura", "brand": "UNICRACK", "promised_on": "2026-11-30",
        "items": [
            {"key": "a", "description": "Casaca cortavientos impermeable con forro polar", "quantity": 150},
            {"key": "b", "description": "Polo escolar blanco con escudo bordado", "quantity": 100},
        ],
        "classification": {"items": [
            {"key": "a", "product": {"new": {"code": "UNI-CAS-01", "name": "Casaca cortavientos", "brand": "UNICRACK"}},
             "materials": [
                 {"sku": "TEL-20", "qty_per_unit": "0.5", "unit": "kg"},
                 {"new": {"sku": "TEL-TAS-01", "name": "Tela taslan impermeable", "kind": "fabric", "unit": "m"}, "qty_per_unit": "1.6", "unit": "m"},
             ]},
            {"key": "b", "product": {"existing_id": polo.id}},
        ]},
    }


@pytest.mark.django_db
def test_an_order_with_classification_is_born_broken_down(catalogue, sales):
    response = client_for(sales).post("/api/orders/", classified_payload(catalogue), format="json")
    assert response.status_code == 201, response.content
    data = response.json()
    assert data["status"] == "broken_down" and data["needs_classification"] is False and data["warnings"] == []
    order = Order.objects.get(pk=data["id"])
    assert set(order.items.values_list("product__code", flat=True)) == {"UNI-CAS-01", "UNI-POL-01"}
    taslan = Material.objects.get(sku="TEL-TAS-01")
    assert taslan.stock == Decimal("0") and taslan.kind == "fabric"  # a new material lands in the inventory
    needs = {r.material.sku: r.qty_needed for r in order.requirements.filter(kind="material")}
    assert needs["TEL-TAS-01"] == Decimal("240") and needs["TEL-20"] == Decimal("100")  # 150 × 0.5 + 100 × 0.25
    assert order.requirements.filter(kind="workshop").count() == 2


@pytest.mark.django_db
def test_an_item_left_unclassified_keeps_the_order_to_classify(catalogue, sales):
    payload = classified_payload(catalogue)
    payload["classification"]["items"] = [e for e in payload["classification"]["items"] if e["key"] == "b"]
    data = client_for(sales).post("/api/orders/", payload, format="json").json()
    assert data["needs_classification"] is True and data["status"] == "broken_down"
    order = Order.objects.get(pk=data["id"])
    assert order.items.get(description__startswith="Casaca").product is None and order.items.get(description__startswith="Polo").product.code == "UNI-POL-01"
    # Without any classification: exactly as before (ADR 0025 B).
    payload.pop("classification")
    data = client_for(sales).post("/api/orders/", payload, format="json").json()
    assert data["needs_classification"] is True and not Order.objects.get(pk=data["id"]).items.filter(product__isnull=False).exists()


@pytest.mark.django_db
def test_editing_with_classification_and_a_bad_reference_changes_nothing(catalogue, sales):
    client = client_for(sales)
    payload = classified_payload(catalogue)
    bad = {**payload, "classification": {"items": [{"key": "b", "product": {"existing_id": 999999}}]}}
    before = Order.objects.count()
    assert client.post("/api/orders/", bad, format="json").status_code == 400
    assert Order.objects.count() == before  # all or nothing
    plain = {k: v for k, v in payload.items() if k != "classification"}
    order_id = client.post("/api/orders/", plain, format="json").json()["id"]
    edited = client.patch(f"/api/orders/{order_id}/", {"items": payload["items"], "classification": payload["classification"]}, format="json")
    assert edited.status_code == 200, edited.content
    assert edited.json()["needs_classification"] is False
    assert Order.objects.get(pk=order_id).requirements.filter(material__sku="TEL-TAS-01").exists()
