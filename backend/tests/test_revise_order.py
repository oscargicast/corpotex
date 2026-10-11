"""ADR 0029 §4 (N2): the technical sheet edited by an instruction, with the model mocked. The
change lives on the order (bom_override, stage_overrides); the catalogue recipe never changes."""

from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

import pytest

from core import clock
from core.models import Material, ProductMaterial
from operations import classify, services
from operations.models import Order, PurchaseOrder
from tests.test_consolidated import catalogue  # noqa: F401
from tests.test_magic_order import client_for

PROMISED = date(2026, 12, 15)


@pytest.fixture
def order(catalogue, sales):
    payload = {"customer": "Caja Piura", "brand": "UNICRACK", "promised_on": PROMISED, "items": [{"product": "UNI-POL-01", "quantity": 100}]}
    return services.register_order(payload, actor=sales)[0]


def answer(order, *, buttons=None, fabric="0.25", extra=(), stages=(), understood=True, summary="Cambia la ficha"):
    item = order.items.get()
    materials = [{"existing_sku": "TEL-20", "name": "Jersey 20/1", "qty_per_unit": float(fabric)}, *extra]
    if buttons is not None:
        materials.insert(0, {"existing_sku": "BOT-NX", "name": "Botón NX", "qty_per_unit": buttons})
    return {"understood": understood, "summary": summary, "items": [{"item_id": item.id, "materials": materials}], "stages": list(stages)}


def revise(client, order, body, model_answer=None, **mock_kwargs):
    with mock.patch.object(classify, "complete_sync", return_value=model_answer, **mock_kwargs) as complete:
        response = client.post(f"/api/orders/{order.id}/revise/", body, format="json")
    return response, complete


def need(order, sku):
    return order.requirements.get(kind="material", material__sku=sku).qty_needed


@pytest.mark.django_db
def test_two_more_buttons_per_polo_dry_run_then_apply(order, production):
    client = client_for(production)
    assert need(order, "BOT-NX") == Decimal("300")
    response, complete = revise(client, order, {"instruction": "agrega 2 botones por polo", "dry_run": True}, answer(order, buttons=5))
    assert response.status_code == 200, response.content
    body = response.json()
    [item] = body["proposal"]["items"]
    assert complete.call_count == 1 and "agrega 2 botones por polo" in complete.call_args.args[0]
    assert {m["sku"]: m["qty_per_unit"] for m in item["current"]} == {"BOT-NX": "3", "TEL-20": "0.25"}
    assert {m["sku"]: m["qty_per_unit"] for m in item["materials"]} == {"BOT-NX": "5", "TEL-20": "0.25"}
    assert item["product"] == {"code": "UNI-POL-01", "name": "Polo"} and item["quantity"] == 100
    assert body["summary"] == "Cambia la ficha" and body["warnings"] == [] and "order" not in body
    assert body["current_estimated_on"] == body["estimated_on"] == order.estimated_on.isoformat()  # buttons do not move dates
    assert body["proposal"]["stage_overrides"] == {} and body["proposal"]["stage_current"] == {}
    # A dry run writes nothing.
    order.refresh_from_db()
    assert need(order, "BOT-NX") == Decimal("300") and order.items.get().bom_override is None

    # The proposal comes back as is: applied exactly, no model call.
    response, complete = revise(client, order, {"proposal": body["proposal"]}, side_effect=AssertionError("no model"))
    assert response.status_code == 200, response.content
    applied = response.json()
    complete.assert_not_called()
    assert applied["summary"] == "Polo: Botón NX 3 → 5 unit por prenda."
    assert need(order, "BOT-NX") == Decimal("500") and need(order, "TEL-20") == Decimal("25")
    assert applied["order"]["id"] == order.id
    # The catalogue recipe is untouched.
    assert ProductMaterial.objects.get(product__code="UNI-POL-01", material__sku="BOT-NX").qty_per_unit == Decimal("3")


@pytest.mark.django_db
def test_cutting_takes_three_days_moves_the_estimate(order, manager):
    before = order.estimated_on
    stages = [{"stage": "cutting", "days": 3}]
    response, _ = revise(client_for(manager), order, {"instruction": "el corte toma 3 días"}, {"understood": True, "summary": "Corte de 1 a 3 días", "items": [], "stages": stages})
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["proposal"]["stage_overrides"] == {"cutting": 3} and body["proposal"]["stage_current"] == {"cutting": 1}
    assert body["proposal"]["stage_labels"] == {"cutting": "Corte"}
    assert body["current_estimated_on"] == before.isoformat()
    order.refresh_from_db()
    assert order.stage_overrides == {"cutting": 3} and order.estimated_on == before + timedelta(days=2)
    assert body["estimated_on"] == order.estimated_on.isoformat() and body["order"]["stage_overrides"] == {"cutting": 3}
    [cutting] = [s for s in order.critical_path if s["stage"] == "cutting"]
    assert cutting["name"] == "Corte" and (date.fromisoformat(cutting["end"]) - date.fromisoformat(cutting["start"])).days == 3


@pytest.mark.django_db
def test_a_new_fabric_enters_the_inventory_only_when_applied(order, production):
    client = client_for(production)
    drill = {"sku": "TEL-DRI-01", "name": "Drill", "kind": "fabric", "unit": "m", "qty_per_unit": 1.1}
    model = {"understood": True, "summary": "Tela a drill", "items": [{"item_id": order.items.get().id, "materials": [
        {"existing_sku": "BOT-NX", "name": "Botón NX", "qty_per_unit": 3}, drill]}], "stages": []}
    response, _ = revise(client, order, {"instruction": "cambia la tela a drill", "dry_run": True}, model)
    [item] = response.json()["proposal"]["items"]
    assert {"new": {"sku": "TEL-DRI-01", "name": "Drill", "kind": "fabric", "unit": "m"}, "qty_per_unit": "1.1", "unit": "m"} in item["materials"]
    assert not Material.objects.filter(sku="TEL-DRI-01").exists()  # the dry run rolled it back
    response, _ = revise(client, order, {"proposal": response.json()["proposal"]})
    assert response.json()["summary"] == "Polo: entra Drill 1.1 m, sale Jersey 20/1 por prenda."
    assert Material.objects.get(sku="TEL-DRI-01").stock == Decimal("0")
    assert need(order, "TEL-DRI-01") == Decimal("110") and not order.requirements.filter(material__sku="TEL-20").exists()


@pytest.mark.django_db
def test_an_ordered_requirement_is_untouched_and_reported(order, production):
    services.confirm_order(order, actor=production)
    services.generate_purchase_orders([Material.objects.get(sku="BOT-NX").id], actor=production)
    po = PurchaseOrder.objects.get(items__requirement__material__sku="BOT-NX")
    response, _ = revise(client_for(production), order, {"instruction": "agrega 2 botones por polo"}, answer(order, buttons=5, fabric="0.3"))
    assert response.status_code == 200, response.content
    warnings = response.json()["warnings"]
    assert any(w.startswith("Botón NX: ya pedido en") and po.code in w for w in warnings)
    assert need(order, "BOT-NX") == Decimal("300") and need(order, "TEL-20") == Decimal("30")  # buttons kept, fabric rebuilt


@pytest.mark.django_db
def test_roles_and_failures(order, sales, production):
    model = answer(order, buttons=5)
    assert revise(client_for(sales), order, {"instruction": "agrega 2 botones por polo"}, model)[0].status_code == 403
    client = client_for(production)
    not_understood = revise(client, order, {"instruction": "hazlo bonito"}, {"understood": False, "summary": "No sé qué cambiar.", "items": [], "stages": []})[0]
    assert not_understood.status_code == 400 and not_understood.json()["detail"] == "No sé qué cambiar."
    same = revise(client, order, {"instruction": "deja los botones"}, answer(order, buttons=3))[0]
    assert same.status_code == 400 and same.json()["detail"] == "La instrucción no cambia la ficha técnica."
    down = revise(client, order, {"instruction": "agrega 2 botones por polo"}, side_effect=RuntimeError("model down"))[0]
    assert down.status_code == 502 and "Prueba de nuevo" in down.json()["detail"]
    empty = revise(client, order, {"instruction": "  "})[0]
    assert empty.status_code == 400
    foreign = revise(client, order, {"proposal": {"items": [{"item_id": 999999, "materials": []}]}})[0]
    assert foreign.status_code == 400 and "999999" in foreign.json()["detail"]
    assert client.post("/api/orders/999999/revise/", {"instruction": "x"}, format="json").status_code == 404
    assert Order.objects.get(pk=order.id).items.get().bom_override is None


@pytest.mark.django_db
def test_a_supplier_date_before_its_step_start_is_late_not_backwards(order, production, catalogue):
    services.confirm_order(order, actor=production)
    workshop_po = PurchaseOrder.objects.get(supplier=catalogue["workshop"])
    today = clock.today()
    workshop_po.committed_on = today + timedelta(days=2)
    workshop_po.save(update_fields=["committed_on"])
    order.stage_overrides = {"cutting": 5}  # the plant hands the cut pieces on day 5
    order.save(update_fields=["stage_overrides"])
    order = services.compute_critical_path(Order.objects.get(pk=order.id))
    [sewing] = [s for s in order.critical_path if s["kind"] == "workshop"]
    assert sewing["start"] == sewing["end"] and sewing["late_by"] == 3
    assert all(date.fromisoformat(s["end"]) >= date.fromisoformat(s["start"]) for s in order.critical_path)
    assert all(s["late_by"] is None for s in order.critical_path if s["kind"] != "workshop")
    assert order.get_status_display() == "Confirmada" and Order.Status.BROKEN_DOWN.label == "Con ficha técnica"


@pytest.mark.django_db
def test_a_stale_stored_estimate_is_not_the_changes(order, production):
    """agente, 11/10 04:00: a stored date that the critical path no longer gives (an old seed)
    made "agregar botones" look like it moved the estimate weeks."""
    computed = order.estimated_on
    Order.objects.filter(pk=order.pk).update(estimated_on=computed + timedelta(days=25))
    order.refresh_from_db()
    response, _ = revise(client_for(production), order, {"instruction": "agrega 2 botones por polo", "dry_run": True}, answer(order, buttons=5))
    body = response.json()
    assert body["current_estimated_on"] == body["estimated_on"] == computed.isoformat()
    order.refresh_from_db()
    assert order.estimated_on == computed + timedelta(days=25)  # the dry run wrote nothing


@pytest.mark.django_db
def test_the_summary_names_the_garment_never_the_item_id(order, production):
    item = order.items.get()
    model = answer(order, buttons=5, summary=f"Se agregan 2 botones por polo en el ítem {item.id}: pasan de 3 a 5. El ítem 999 no existe.")
    response, complete = revise(client_for(production), order, {"instruction": "agrega 2 botones por polo", "dry_run": True}, model)
    assert response.json()["summary"] == "Se agregan 2 botones por polo en Polo: pasan de 3 a 5. El ítem 999 no existe."
    assert "nunca por el número de ítem" in complete.call_args.args[0]
