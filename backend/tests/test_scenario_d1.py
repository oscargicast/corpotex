"""D1, the end-to-end rehearsal of the demo (planning.md, section E), as one integration test
over the real seed. The model is not called: each agent step runs the same service its tool
calls, so what is checked is everything around the model."""

import base64
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.utils import timezone

from core import clock
from manager import services as manager_services
from manager.models import Alert, AlertNotification, Decision
from messaging import services as messaging_services
from messaging.models import Conversation, Message, Turn
from operations import services
from operations.models import Order, PurchaseOrder, Route
from seed.loader import DATA_DIR, REAL_SUPPLIER_PHONE

pytestmark = pytest.mark.skipif(not (DATA_DIR / "suppliers.json").exists(), reason="seed data not present")
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def claim(conversation):
    """What `run_turn` does before calling the model: take the batch of that conversation."""
    Turn.objects.filter(conversation=conversation, status="pending").update(available_at=timezone.now() - timedelta(seconds=1))
    batch = messaging_services.claim_next_turn(conversation.id)
    assert batch is not None, f"no turn to run on {conversation}"
    return batch


@pytest.mark.django_db
def test_d1_eight_steps(manager_client, sales_client, manager, sales, production, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    call_command("seed_demo", verbosity=0)
    norte = PurchaseOrder.objects.get(code="PT-0038").supplier  # Confecciones del Norte, the real WhatsApp supplier
    assert norte.numbers.filter(phone=REAL_SUPPLIER_PHONE, active=True, simulated=False).exists()

    # (1) Sales registers an order, production confirms, the manager approves the assignment.
    order_payload = {
        "code": "CP-2026-0200", "customer": "Caja Piura", "brand": "UNICRACK", "promised_on": (clock.today() + timedelta(days=12)).isoformat(),
        "items": [{"product": "UNI-POL-01", "quantity": 300, "sizes": {"M": 300}, "unit_price": "28.00"}],
    }
    registered = sales_client.post("/api/orders/", order_payload, format="json")
    assert registered.status_code == 201, registered.content
    order = Order.objects.get(code="CP-2026-0200")
    services.confirm_order(order, actor=production)
    assignment = Decision.objects.filter(kind="approve_assignment", status="pending", purchase_orders__items__requirement__order=order).distinct().get()
    workshop_po = next(po for po in assignment.purchase_orders.select_related("supplier") if po.supplier.kind == "workshop" and not po.supplier.is_in_house)
    if workshop_po.supplier != norte:  # The script wants Confecciones del Norte: the manager changes the supplier.
        resolved = manager_client.post(f"/api/manager/decisions/{assignment.id}/", {"action": "change_supplier", "supplier_id": norte.id, "purchase_order_id": workshop_po.id}, format="json")
    else:
        resolved = manager_client.post(f"/api/manager/decisions/{assignment.id}/", {"action": "approve"}, format="json")
    assert resolved.status_code == 200, resolved.content
    workshop_po.refresh_from_db()
    assert workshop_po.supplier == norte and workshop_po.status == "approved"
    norte_rate = norte.rates.filter(product=workshop_po.items.first().requirement.product).order_by("-valid_from").first().unit_price
    assert workshop_po.items.first().unit_price == norte_rate  # The reference price followed the supplier.
    whatsapp = workshop_po.conversation
    assert whatsapp is not None and whatsapp.channel == "whatsapp" and whatsapp.allowed_number.phone == REAL_SUPPLIER_PHONE
    batch = claim(whatsapp)
    assert workshop_po.id in batch.new_purchase_order_ids
    state = messaging_services.turn_state(batch)
    assert state["supplier"]["name"] == norte.name and any(po["code"] == workshop_po.code for po in state["purchase_orders"])
    messaging_services.finish_turn(batch, "sess-d1")  # The agent wrote the first contact.
    workshop_po.refresh_from_db()
    assert workshop_po.status == "negotiating"

    # (2) Valeria answers with a date: the agent confirms with the reference price.
    committed_on = workshop_po.internal_due_on
    unit_price = workshop_po.items.first().unit_price
    services.confirm_purchase_order(workshop_po, unit_price=unit_price, committed_on=committed_on, terms="50% adelanto por Yape")
    workshop_po.refresh_from_db()
    assert workshop_po.status == "confirmed" and workshop_po.payments.count() == 2

    # (3) Valeria sends progress with a photo: the purchase order shows it.
    photo_message = Message.objects.create(conversation=whatsapp, author="supplier", text="va avanzando", status="received", sent_at=timezone.now())
    photo_message.media.save("avance.png", SimpleUploadedFile("avance.png", PNG, content_type="image/png"), save=True)
    services.record_progress(workshop_po, units_done=120, message_id=photo_message.id, photo=SimpleUploadedFile("avance.png", PNG, content_type="image/png"), actor=None)
    detail = manager_client.get(f"/api/purchase-orders/{workshop_po.id}/").json()
    assert detail["status"] == "in_progress" and detail["units_done"] == 120
    assert detail["progress_reports"][0]["photo"] and detail["progress_reports"][0]["source"] == "whatsapp"

    # (4) The workshop of PT-0038 cancels mid-way: redistribution, decision, new route, order at risk.
    scene_po = PurchaseOrder.objects.get(code="PT-0038")
    scene_order = scene_po.items.first().requirement.order
    old_route = Route.objects.get(date=scene_po.committed_on, status="planned")
    scene_po, created, decision = services.cancel_by_supplier(scene_po, reason="se me malogró la máquina")
    assert scene_po.status == "cancelled_by_supplier" and len(created) >= 2
    assert all(po.redistributed_from == scene_po and po.status == "suggested" for po in created)
    assert decision.status == "pending" and decision.detail["cancelled"]["code"] == "PT-0038"
    assert decision.detail["before"]["route_id"] == old_route.id
    proposed = Route.objects.get(pk=decision.detail["after"]["route_id"])
    assert proposed.status == "proposed" and proposed.recalculated_from == old_route
    assert decision.detail["after"]["estimated_on"] and decision.detail["after"]["currency"] == "PEN"
    manager_services.run_monitor()  # The next tick.
    scene_order.refresh_from_db()
    assert scene_order.risk in ("at_risk", "in_danger")
    pending = manager_client.get("/api/manager/pending/").json()
    assert decision.id in {d["id"] for d in pending["decisions"]}

    # (5) The manager approves from the assistant ("sí"): the same service the tool calls.
    manager_services.resolve_decision(decision, action="approve", actor=manager)
    decision.refresh_from_db()
    assert decision.status == "approved"
    routes = manager_client.get("/api/routes/?current=1").json()
    assert routes["current"]["id"] == proposed.id and routes["replaced"]["id"] == old_route.id
    assert {s["purchase_order"]["code"] for s in routes["replaced"]["stops"] if s["purchase_order"]} == {"PT-0038"}

    # (6) Sales sees the notice without prices.
    sales_order = sales_client.get(f"/api/orders/{scene_order.id}/").json()
    assert "unit_price" not in str(sales_order) and sales_order["estimated_on"]
    if scene_order.risk == "in_danger":
        danger = Alert.objects.get(kind="order_in_danger", order=scene_order, status="open")
        assert AlertNotification.objects.filter(alert=danger, user=sales).exists()
        assert danger.id in {a["id"] for a in sales_client.get("/api/alerts/?mine=1").json()}
        assert "unit_price" not in str(sales_client.get("/api/alerts/?mine=1").json())
    assert sales_client.get(f"/api/purchase-orders/{scene_po.id}/").status_code == 200
    assert "conversation_id" not in sales_client.get(f"/api/purchase-orders/{scene_po.id}/").json()

    # (7) The agent contacts the new workshops on the simulator.
    for po in created:
        po.refresh_from_db()
        if po.supplier.is_in_house:
            assert po.status == "confirmed"
            continue
        assert po.status == "approved" and po.conversation is not None and po.conversation.channel == "simulator"
        batch = claim(po.conversation)
        assert po.id in batch.new_purchase_order_ids
        messaging_services.finish_turn(batch, f"sess-{po.code}")
        po.refresh_from_db()
        assert po.status == "negotiating"
    contacts = manager_client.get("/api/simulator/contacts/").json()
    assert {c["supplier"]["name"] for c in contacts} >= {po.supplier.name for po in created if not po.supplier.is_in_house}

    # (8) The manager marks the advance as paid.
    advance = workshop_po.payments.get(kind="advance")
    paid = manager_client.post(f"/api/payments/{advance.id}/pay/", {"method": "yape"})
    assert paid.status_code == 200 and paid.json()["status"] == "paid"
    monitor = manager_client.get("/api/monitor/").json()
    assert any(row["supplier"]["name"] == norte.name for row in monitor["payments_by_supplier"])
    timeline = [c["status"] for c in manager_client.get(f"/api/purchase-orders/{workshop_po.id}/").json()["status_history"]]
    assert timeline == ["suggested", "approved", "negotiating", "confirmed", "in_progress"]
