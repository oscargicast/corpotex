"""ADR 0028 §3c (N7): `classify-draft` in phases, so the form shows progress. `product` is Jev
alone (under a second), `recipe` is Claude plus Jev's materials, `full` is both, as before."""

from unittest import mock

import pytest

from core.models import Product
from operations import classify, jev
from tests.test_consolidated import catalogue  # noqa: F401
from tests.test_magic_order import client_for

POLO = "Polo escolar blanco con escudo bordado"
VEST = "Chaleco reflectivo naranja con cinta plateada"
RECIPE = {
    "product": {"code": "UNI-CHA-01", "name": "Chaleco reflectivo", "brand": "UNICRACK"},
    "materials": [
        {"existing_sku": "TEL-20", "name": "Jersey 20/1", "kind": "fabric", "unit": "kg", "qty_per_unit": 0.3},
        {"sku": "CIN-REF-01", "name": "Cinta reflectiva plateada", "kind": "other", "unit": "m", "qty_per_unit": 1.2},
    ],
    "confidence": 0.8,
}


def draft(client, phase, description):
    body = {"brand": "UNICRACK", "phase": phase, "items": [{"key": "l1", "description": description, "quantity": 120}]}
    response = client.post("/api/orders/classify-draft/", body, format="json")
    assert response.status_code == 200, response.content
    [line] = response.json()["items"]
    return line


@pytest.mark.django_db
def test_phase_product_answers_a_catalogue_polo_in_full_without_claude(catalogue, sales):
    polo = Product.objects.get(code="UNI-POL-01")
    with mock.patch.object(jev, "choose", return_value=("UNI-POL-01", 0.92, {})), mock.patch.object(classify, "complete_sync") as complete:
        line = draft(client_for(sales), "product", POLO)
    complete.assert_not_called()
    assert line["status"] == "classified" and line["product"]["existing_id"] == polo.id and line["confidence"] == 0.92
    assert {m["sku"] for m in line["materials"]} == {"BOT-NX", "TEL-20"}  # the catalogue recipe, as `full` gives it


@pytest.mark.django_db
def test_phase_product_leaves_a_new_garment_new_pending_without_claude(catalogue, production):
    client = client_for(production)
    with mock.patch.object(jev, "choose", return_value=(jev.NEW, 0.81, {})), mock.patch.object(classify, "complete_sync") as complete:
        line = draft(client, "product", VEST)
    complete.assert_not_called()
    assert line == {"key": "l1", "status": "new_pending", "confidence": 0.81}
    # Jev unsure about a catalogue product, or off: still new_pending, Claude is the next phase.
    with mock.patch.object(jev, "choose", return_value=("UNI-POL-01", 0.4, {})), mock.patch.object(classify, "complete_sync") as complete:
        assert draft(client, "product", VEST) == {"key": "l1", "status": "new_pending", "confidence": 0.4}
    with mock.patch.object(jev, "choose", return_value=None), mock.patch.object(classify, "complete_sync") as complete:
        assert draft(client, "product", VEST) == {"key": "l1", "status": "new_pending", "confidence": None}
    complete.assert_not_called()


@pytest.mark.django_db
def test_phase_recipe_skips_the_product_step_and_brings_the_recipe(catalogue, sales):
    client = client_for(sales)
    with mock.patch.object(jev, "choose") as product_step, mock.patch.object(jev, "choose_many", return_value=None), mock.patch.object(
        classify, "complete_sync", return_value=RECIPE
    ) as complete:
        line = draft(client, "recipe", VEST)
    product_step.assert_not_called()
    assert complete.call_count == 1
    assert line["status"] == "classified" and line["product"] == {"new": {"code": "UNI-CHA-01", "name": "Chaleco reflectivo", "brand": "UNICRACK"}}
    assert [m.get("sku") or m["new"]["sku"] for m in line["materials"]] == ["TEL-20", "CIN-REF-01"]

    # `full` (the default) is unchanged: Jev first, then Claude when it says new.
    body = {"brand": "UNICRACK", "items": [{"key": "l1", "description": VEST, "quantity": 120}]}
    with mock.patch.object(jev, "choose", return_value=(jev.NEW, 0.81, {})) as product_step, mock.patch.object(
        jev, "choose_many", return_value=None
    ), mock.patch.object(classify, "complete_sync", return_value=RECIPE):
        [full] = client.post("/api/orders/classify-draft/", body, format="json").json()["items"]
    assert product_step.call_count == 1 and full == line
    assert client.post("/api/orders/classify-draft/", {**body, "phase": "fast"}, format="json").status_code == 400
