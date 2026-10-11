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
    with (
        mock.patch.object(classify, "complete_sync", return_value=CLAUDE_PROPOSAL),
        mock.patch.object(jev, "choose", return_value=("nuevo", 0.55, {})),
        mock.patch.object(jev, "choose_many", return_value={"m0": ("TEL-20", 0.9, {}), "m1": ("nuevo", 0.7, {})}) as many,
    ):
        item = manager_client.post(f"/api/orders/{order.id}/classify/", {}, format="json").json()["items"][0]
    assert many.call_count == 1 and set(many.call_args.args[1]) == {"m0", "m1"}  # every material in one call
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


@pytest.mark.django_db
def test_claude_picking_a_catalogue_product_returns_its_bill_of_materials(order_with_new_garment, production):
    """Finding of 10/10 22:35 (CP-2026-0161): Claude mapped the polo to UNI-POD-01 but listed new
    materials that `apply_classification` would never create for an existing product."""
    order = order_with_new_garment
    proposal = {
        "product": {"existing_code": "UNI-POL-01", "code": "UNI-POL-01", "name": "Polo", "brand": "UNICRACK"},
        "materials": [{"existing_sku": None, "sku": "TEL-AMA", "name": "Jersey amarillo (franja)", "kind": "fabric", "unit": "kg", "qty_per_unit": 0.01}],
        "confidence": 0.8,
    }
    with mock.patch.object(classify, "complete_sync", return_value=proposal), mock.patch.object(jev, "choose", return_value=None):
        item = client_for(production).post(f"/api/orders/{order.id}/classify/", {}, format="json").json()["items"][0]
    assert item["product"]["code"] == "UNI-POL-01" and item["confidence"] == 0.8
    assert {m["sku"] for m in item["materials"]} == {"BOT-NX", "TEL-20"} and all("new" not in m for m in item["materials"])


@pytest.mark.django_db
def test_plant_processes_are_not_proposed_as_materials(order_with_new_garment, production):
    order = order_with_new_garment
    proposal = {**CLAUDE_PROPOSAL, "materials": CLAUDE_PROPOSAL["materials"] + [
        {"existing_sku": None, "sku": "BOR-ESC-01", "name": "Bordado escudo pecho", "kind": "other", "unit": "unit", "qty_per_unit": 1},
        {"existing_sku": None, "sku": "SUB-ESC-01", "name": "Sublimado escudo", "kind": "other", "unit": "unit", "qty_per_unit": 1},
    ]}
    with mock.patch.object(classify, "complete_sync", return_value=proposal) as complete, mock.patch.object(jev, "choose", return_value=None):
        item = client_for(production).post(f"/api/orders/{order.id}/classify/", {}, format="json").json()["items"][0]
    assert [m.get("sku") or m["new"]["sku"] for m in item["materials"]] == ["TEL-20", "CIE-NYL-60"]
    assert complete.call_count == 1 and "se hacen en la planta" in classify.SYSTEM_PROMPT


@pytest.mark.django_db
def test_a_new_material_that_extends_a_known_sku_stays_the_known_one(order_with_new_garment, production):
    """Finding of 10/10 22:40: "TEL-ALG-30-AM" (the same jersey in yellow) came out as a new
    material next to TEL-ALG-30. Colour and size go in the order, not in a new SKU."""
    order = order_with_new_garment
    proposal = {**CLAUDE_PROPOSAL, "materials": [
        {"existing_sku": "TEL-20", "sku": "TEL-20", "name": "Jersey 20/1", "kind": "fabric", "unit": "kg", "qty_per_unit": 0.5},
        {"existing_sku": None, "sku": "TEL-20-AZM", "name": "Jersey 20/1 azul marino", "kind": "fabric", "unit": "kg", "qty_per_unit": 0.1},
        {"existing_sku": None, "sku": "BOTON-X", "name": "botón nx", "kind": "button", "unit": "unit", "qty_per_unit": 4},
        {"existing_sku": None, "sku": "CIE-NYL-60", "name": "Cierre nylon 60 cm", "kind": "zipper", "unit": "unit", "qty_per_unit": 1},
    ]}
    with mock.patch.object(classify, "complete_sync", return_value=proposal) as complete, mock.patch.object(jev, "choose", return_value=None):
        item = client_for(production).post(f"/api/orders/{order.id}/classify/", {}, format="json").json()["items"][0]
    rows = {m.get("sku") or m["new"]["sku"]: m for m in item["materials"]}
    assert list(rows) == ["TEL-20", "BOT-NX", "CIE-NYL-60"]
    assert rows["TEL-20"]["qty_per_unit"] == "0.6" and rows["TEL-20"]["material_id"] == Material.objects.get(sku="TEL-20").id
    assert rows["BOT-NX"]["material_id"] == Material.objects.get(sku="BOT-NX").id  # same name, any case
    assert "new" in rows["CIE-NYL-60"]
    assert "reusa el SKU existente" in complete.call_args.args[0] and "el bordado puede pedir hilo de bordar" in complete.call_args.args[0]



# --- Jev against a stand-in for the typesafe-sdk package (the image may not have it) ------------


class FakeChoice:
    def __init__(self, criteria, instructions=None):
        self.criteria, self.instructions = criteria, instructions


class FakeNoul:
    def __init__(self, instructions=None, criteria=None):
        self.instructions = instructions


class FakeClient:
    """Records each `system_one` call; answers from `script` (a list of {name: (choice, confidence)}) or raises it."""

    calls: list = []
    script: list = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def system_one(self, state, questions, timeout=None):
        from types import SimpleNamespace

        FakeClient.calls.append((state, dict(questions), {**self.kwargs, "call_timeout": timeout}))
        step = FakeClient.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return SimpleNamespace(
            choices={name: SimpleNamespace(choice=c, confidence=conf, probabilities={c: conf}) for name, (c, conf) in step.items()},
            nouls={},
        )


@pytest.fixture
def fake_sdk(settings, monkeypatch):
    import sys
    import types

    module = types.ModuleType("typesafe_sdk")
    module.Choice, module.Noul, module.TypeSafeClient = FakeChoice, FakeNoul, FakeClient
    module.RetryPolicy = lambda **kwargs: kwargs
    monkeypatch.setitem(sys.modules, "typesafe_sdk", module)
    settings.TYPESAFE_API_KEY = "test-key"
    FakeClient.calls, FakeClient.script = [], []
    return FakeClient


@pytest.mark.django_db
def test_jev_failure_gives_exactly_the_claude_result(order_with_new_garment, production, settings, fake_sdk):
    order = order_with_new_garment
    client = client_for(production)
    settings.TYPESAFE_API_KEY = ""
    with mock.patch.object(classify, "complete_sync", return_value=CLAUDE_PROPOSAL):
        claude_only = client.post(f"/api/orders/{order.id}/classify/", {}, format="json").json()
    settings.TYPESAFE_API_KEY = "test-key"
    fake_sdk.script = [RuntimeError("503 from api.typesafe.ai"), RuntimeError("timeout")]
    with mock.patch.object(classify, "complete_sync", return_value=CLAUDE_PROPOSAL), mock.patch.object(jev.logger, "warning") as warning:
        response = client.post(f"/api/orders/{order.id}/classify/", {}, format="json")
    assert response.status_code == 200 and response.json() == claude_only
    assert len(fake_sdk.calls) == 2 and warning.call_count == 2  # product, then materials; both logged


@pytest.mark.django_db
def test_jev_asks_the_product_then_every_material_in_one_call(order_with_new_garment, production, fake_sdk):
    """Two calls per item at most; the #87 guards hold when Jev answers: processes are never asked,
    a SKU Jev invents is ignored, "nuevo" does not undo the dedupe, and Jev does not fold a new
    material into an existing one (the snap fastener stays new)."""
    order = order_with_new_garment
    proposal = {**CLAUDE_PROPOSAL, "materials": [
        {"existing_sku": None, "sku": "TEL-20-AZM", "name": "Jersey 20/1 azul", "kind": "fabric", "unit": "kg", "qty_per_unit": 0.6},
        {"existing_sku": None, "sku": "BOT-NUEVO", "name": "Botón de presión", "kind": "button", "unit": "unit", "qty_per_unit": 4},
        {"existing_sku": None, "sku": "CIE-NYL-60", "name": "Cierre nylon 60 cm", "kind": "zipper", "unit": "unit", "qty_per_unit": 1},
        {"existing_sku": None, "sku": "BOR-ESC", "name": "Bordado escudo", "kind": "other", "unit": "unit", "qty_per_unit": 1},
    ]}
    fake_sdk.script = [
        {"choice": ("nuevo", 0.93)},
        {"m0": ("nuevo", 0.8), "m1": ("BOT-NX", 0.85), "m2": ("CIE-FANTASMA", 0.99)},
    ]
    with mock.patch.object(classify, "complete_sync", return_value=proposal):
        item = client_for(production).post(f"/api/orders/{order.id}/classify/", {}, format="json").json()["items"][0]
    assert len(fake_sdk.calls) == 2
    product_call, materials_call = fake_sdk.calls
    assert set(product_call[1]) == {"choice"} and "UNI-POL-01" in product_call[1]["choice"].criteria
    assert set(materials_call[1]) == {"m0", "m1", "m2"}  # the embroidery was never asked
    assert set(materials_call[1]["m0"].criteria) == {"BOT-NX", "TEL-20", "nuevo"}
    assert materials_call[2]["retry"] == {"max_retries": 0} and 0 < materials_call[2]["call_timeout"] <= jev.ITEM_BUDGET_SECONDS
    rows = [(m.get("sku") or m["new"]["sku"], m["confidence"]) for m in item["materials"]]
    assert rows == [("TEL-20", 0.8), ("BOT-NUEVO", 0.8), ("CIE-NYL-60", 0.8)]


@pytest.mark.django_db
def test_jev_picks_the_catalogue_product_and_skips_claude(order_with_new_garment, production, fake_sdk):
    order = order_with_new_garment
    fake_sdk.script = [{"choice": ("UNI-POL-01", 0.9)}]
    with mock.patch.object(classify, "complete_sync") as complete:
        item = client_for(production).post(f"/api/orders/{order.id}/classify/", {}, format="json").json()["items"][0]
    complete.assert_not_called()
    assert item["product"]["code"] == "UNI-POL-01" and item["confidence"] == 0.9 and len(fake_sdk.calls) == 1


def test_jev_budget_counts_only_its_own_calls(settings, fake_sdk):
    budget = jev.Budget(1.0)
    budget.spend(0.6)
    assert jev.choose("x", {"a": "A"}, budget=budget) is None and fake_sdk.calls == []  # 0.4 s left: not worth a call
    fresh = jev.Budget()
    fake_sdk.script = [{"choice": ("a", 0.7)}]
    assert jev.choose("x", {"a": "A", "nuevo": "N"}, budget=fresh) == ("a", 0.7, {"a": 0.7})
    assert fresh.remaining() < jev.ITEM_BUDGET_SECONDS



@pytest.mark.django_db
def test_the_classifier_and_the_photo_use_classify_model(order_with_new_garment, settings):
    """CLASSIFY_MODEL (faster) for generation in the form; AGENT_MODEL stays for the agents."""
    settings.CLASSIFY_MODEL, settings.AGENT_MODEL = "claude-sonnet-5-5", "claude-opus-5-5"
    with mock.patch("agent.sdk.complete", new=mock.AsyncMock(return_value=CLAUDE_PROPOSAL)) as complete:
        classify.complete_sync("prompt", schema=classify.PROPOSAL_SCHEMA)
    assert complete.call_args.kwargs["model"] == "claude-sonnet-5-5" and complete.call_args.kwargs["effort"] == "low"
    assert complete.call_args.kwargs["max_turns"] == 1  # no tools, one turn
    from operations import describe

    with mock.patch("agent.sdk.complete", new=mock.AsyncMock(return_value={"description": "Polo blanco"})) as complete:
        describe.describe(b"img", "image/png")
    assert complete.call_args.kwargs["model"] == "claude-sonnet-5-5" and complete.call_args.kwargs["max_turns"] == 1
    settings.CLASSIFY_MODEL = ""
    assert classify.classify_model() == "claude-opus-5-5"  # empty falls back to AGENT_MODEL


@pytest.mark.django_db
def test_the_catalogue_is_cached_until_it_changes(order_with_new_garment):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    first = classify._catalogue()
    with CaptureQueriesContext(connection) as again:
        second = classify._catalogue()
    assert second is first and len(again) == 3  # only the three version aggregates
    Material.objects.create(sku="TEL-NUEVA", name="Tela nueva", kind="fabric", unit="m", stock=0)
    third = classify._catalogue()
    assert third is not first and "TEL-NUEVA" in {m.sku for m in third[1]}
    classify._catalogue_cache["at"] -= classify.CATALOGUE_TTL + 1  # stale by age even if nothing changed
    assert classify._catalogue() is not third


def test_the_jev_client_is_built_once_per_process(settings, fake_sdk):
    built = []
    original = fake_sdk.__init__

    def counting(self, **kwargs):
        built.append(kwargs)
        original(self, **kwargs)

    with mock.patch.object(fake_sdk, "__init__", counting):
        fake_sdk.script = [{"choice": ("a", 0.9)}, {"choice": ("a", 0.8)}]
        jev.choose("x", {"a": "A", "nuevo": "N"})
        jev.choose("y", {"a": "A", "nuevo": "N"})
    assert len(built) == 1 and len(fake_sdk.calls) == 2 and all(call[2]["call_timeout"] > 0 for call in fake_sdk.calls)
