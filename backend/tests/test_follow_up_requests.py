"""ADR 0027 §6 (S5): Comercial, Producción or the Gerente ask for progress; the agent asks the
supplier once, and the answer goes back to whoever asked."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import Material
from manager.models import Alert, AlertNotification
from messaging import services
from messaging.models import AllowedNumber, Conversation, Message, Turn
from operations import services as operations_services
from operations.models import FollowUpRequest, PurchaseOrder, PurchaseOrderItem, Requirement
from suppliers.models import Supplier
from tests.scenario import build


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.get_or_create(user=user)[0].key}")
    return client


MONDAY = timezone.make_aware(datetime(2026, 10, 12, 10, 0))


@pytest.fixture
def two_suppliers(db, sales, monkeypatch):
    """CP-2026-0001 waits on the workshop (PT-0001, real number) and on buttons from Avíos Gamarra
    (PI-0002, simulated). Monday 10:00 unless a test says otherwise: the night holds real WhatsApp."""
    monkeypatch.setattr(services, "QUIET_HOURS", None)  # whatever the machine's .env says
    monkeypatch.setattr("core.clock.now", lambda config=None: MONDAY)
    monkeypatch.setattr("core.clock.today", lambda config=None: MONDAY.date())
    data = build(owner=sales)
    gamarra = Supplier.objects.create(name="Avíos Gamarra", kind="material", city="Lima")
    number = AllowedNumber.objects.create(phone="sim-gamarra", supplier=gamarra, active=True, simulated=True)
    conversation = Conversation.objects.create(channel="simulator", allowed_number=number)
    buttons = Material.objects.create(sku="BOT-01", name="Botón", kind="button", unit="unit", stock=0)
    requirement = Requirement.objects.create(order=data["order"], kind="material", material=buttons, qty_needed=3000, status="ordered")
    po = PurchaseOrder.objects.create(code="PI-0002", supplier=gamarra, conversation=conversation, status="confirmed", committed_on=date(2026, 10, 16))
    PurchaseOrderItem.objects.create(purchase_order=po, requirement=requirement, quantity=Decimal("3000"), unit_price=Decimal("0.10"))
    data.update(gamarra=gamarra, gamarra_conversation=conversation, buttons_po=po)
    return data


def claim(conversation):
    Turn.objects.filter(conversation=conversation, status="pending").update(available_at=timezone.now() - timedelta(seconds=1))
    return services.claim_next_turn(conversation.id)


@pytest.mark.django_db
def test_an_order_with_two_suppliers_gets_two_requests_and_two_turns(two_suppliers, sales):
    order = two_suppliers["order"]
    response = client_for(sales).post(f"/api/orders/{order.id}/follow-up/", {}, format="json")
    assert response.status_code == 202, response.content
    body = response.json()
    assert {(r["purchase_order"]["code"], r["status"], r["already_asked"]) for r in body["requests"]} == {("PT-0001", "pending", False), ("PI-0002", "pending", False)}
    assert all(r["id"] for r in body["requests"]) and "Le pedimos avance a Avíos Gamarra y Confecciones del Norte" in body["detail"]
    turns = Turn.objects.filter(reason="follow_up", status="pending")
    assert turns.count() == 2
    for turn in turns:
        assert turn.follow_up["kind"] == "requested" and turn.follow_up["reason"] == "Comercial pide avance de CP-2026-0001"
        assert turn.follow_up["requested_by"] == sales.id
    assert FollowUpRequest.objects.filter(requested_by=sales, status="pending").count() == 2


@pytest.mark.django_db
def test_one_turn_for_two_orders_of_the_same_supplier(two_suppliers, production):
    second = PurchaseOrder.objects.create(code="PT-0002", supplier=two_suppliers["supplier"], conversation=two_suppliers["conversation"], status="confirmed")
    PurchaseOrderItem.objects.create(purchase_order=second, requirement=two_suppliers["requirement"], quantity=200, unit_price=Decimal("6.50"))
    client_for(production).post(f"/api/orders/{two_suppliers['order'].id}/follow-up/", {}, format="json")
    workshop_turns = Turn.objects.filter(conversation=two_suppliers["conversation"], reason="follow_up")
    assert workshop_turns.count() == 1
    assert set(workshop_turns.get().follow_up["purchase_orders"]) == {str(two_suppliers["purchase_order"].id), str(second.id)}
    assert workshop_turns.get().follow_up["reason"] == "Producción pide avance de CP-2026-0001"


@pytest.mark.django_db
def test_an_order_already_waiting_queues_nothing_and_hangs_on_the_wait(two_suppliers, sales):
    po = two_suppliers["purchase_order"]
    asked = MONDAY - timedelta(minutes=40)
    PurchaseOrder.objects.filter(pk=po.pk).update(awaiting_reply_since=asked)
    body = client_for(sales).post(f"/api/orders/{two_suppliers['order'].id}/follow-up/", {}, format="json").json()
    row = next(r for r in body["requests"] if r["purchase_order"]["code"] == "PT-0001")
    assert row["status"] == "asked" and row["already_asked"] is True and row["asked_at"] == timezone.localtime(asked).isoformat()
    assert "ya se le preguntó" in body["detail"] and "te avisamos en el asistente cuando conteste" in body["detail"]
    assert not Turn.objects.filter(conversation=two_suppliers["conversation"]).exists()  # the brake ignores window and mode
    assert Turn.objects.filter(conversation=two_suppliers["gamarra_conversation"], reason="follow_up").count() == 1
    # A request asked less than 2 h ago brakes too, older ones do not.
    gamarra_po = two_suppliers["buttons_po"]
    FollowUpRequest.objects.create(purchase_order=gamarra_po, requested_at=MONDAY, status="asked", asked_at=MONDAY - timedelta(minutes=90))
    Turn.objects.all().delete()
    again = client_for(sales).post(f"/api/purchase-orders/{gamarra_po.id}/follow-up/", {}, format="json")
    assert again.status_code == 403  # sales only asks through the order
    body = client_for(sales).post(f"/api/orders/{two_suppliers['order'].id}/follow-up/", {}, format="json").json()
    assert {r["already_asked"] for r in body["requests"]} == {True} and not Turn.objects.exists()


@pytest.mark.django_db
def test_sales_asks_only_through_the_order_and_dry_run_creates_nothing(two_suppliers, sales, production):
    po = two_suppliers["purchase_order"]
    assert client_for(sales).post(f"/api/purchase-orders/{po.id}/follow-up/", {}, format="json").status_code == 403
    preview = client_for(sales).post(f"/api/orders/{two_suppliers['order'].id}/follow-up/", {"dry_run": True}, format="json")
    assert preview.status_code == 200 and [r["id"] for r in preview.json()["requests"]] == [None, None]
    assert "Le escribiría a" in preview.json()["detail"]
    assert not FollowUpRequest.objects.exists() and not Turn.objects.exists()
    done = client_for(production).post(f"/api/purchase-orders/{po.id}/follow-up/", {}, format="json")
    assert done.status_code == 202 and [r["purchase_order"]["code"] for r in done.json()["requests"]] == ["PT-0001"]
    assert Turn.objects.get(reason="follow_up").follow_up["reason"] == "Producción pide avance de PT-0001"


@pytest.mark.django_db
def test_the_answer_goes_back_to_whoever_asked(two_suppliers, sales, manager, production):
    conversation, po = two_suppliers["conversation"], two_suppliers["purchase_order"]
    client_for(sales).post(f"/api/purchase-orders/{po.id}/follow-up/", {}, format="json")  # 403, sales asks via the order
    client_for(sales).post(f"/api/orders/{two_suppliers['order'].id}/follow-up/", {}, format="json")
    sunday = timezone.make_aware(datetime(2026, 10, 11, 10, 0))  # outside the working days: a person's request still goes
    with mock.patch("core.clock.now", return_value=sunday), mock.patch("core.clock.today", return_value=sunday.date()):
        batch = claim(conversation)
        assert batch is not None and batch.follow_up["kind"] == "requested"
        Message.objects.create(conversation=conversation, author="agent", text="¿Cómo va el PT-0001?", status="sent", sent_at=timezone.now(), turn=batch.turn)
        services.finish_turn(batch, "sess")
    request = FollowUpRequest.objects.get(purchase_order=po)
    po.refresh_from_db()
    assert request.status == "asked" and request.asked_at == sunday and po.awaiting_reply_since == sunday
    assert (po.last_follow_up_kind, po.last_follow_up_at) == ("requested", sunday)
    listing = next(p for p in client_for(production).get("/api/purchase-orders/").json() if p["code"] == "PT-0001")
    assert listing["awaiting_reply"] is True and listing["last_follow_up"] == {"kind": "requested", "at": timezone.localtime(sunday).isoformat(), "awaiting_reply": True}
    assert listing["pending_follow_up"]["status"] == "asked" and listing["pending_follow_up"]["requested_by_role"] == "sales"

    # The supplier answers: the batch carries the open request; the agent closes it.
    Message.objects.create(conversation=conversation, author="supplier", text="Vamos en 400, el jueves entrego", status="received", sent_at=timezone.now())
    services.enqueue_turn(conversation, "message")
    batch = claim(conversation)
    assert batch.follow_up_request_ids == [request.id]
    [open_request] = services.turn_state(batch)["open_follow_up_requests"]
    assert open_request["id"] == request.id and open_request["purchase_order_code"] == "PT-0001"
    assert datetime.fromisoformat(open_request["asked_at"]) == sunday
    assert operations_services.answer_follow_up_requests([request.id], summary="Van 400 de 1000; entrega el jueves") == 1
    services.finish_turn(batch, "sess")
    request.refresh_from_db()
    assert request.status == "answered" and request.answer_summary == "Van 400 de 1000; entrega el jueves"

    notice = Alert.objects.get(kind="follow_up_answered")
    assert {n.user.username for n in AlertNotification.objects.filter(alert=notice)} == {"comercial"}  # only whoever asked
    assert "Vamos en 400" not in notice.text and "Van 400 de 1000" in notice.text  # never the chat's text
    sales_conversation = services.dashboard_conversation(sales)
    turn = Turn.objects.get(conversation=sales_conversation, status="pending")
    assistant = services.claim_next_turn(sales_conversation.id) if Turn.objects.filter(pk=turn.pk).update(available_at=timezone.now()) else None
    payload = services.assistant_turn_state(assistant)["alerts"][0]
    assert payload["kind"] == "follow_up_answered" and payload["answer_summary"] == "Van 400 de 1000; entrega el jueves"
    assert payload["purchase_order"] == {"id": po.id, "code": "PT-0001"} and payload["url"] == f"/purchase-orders/{po.id}"
    services.finish_turn(assistant, "sess-a")
    notice.refresh_from_db()
    assert notice.status == "resolved"  # told once, never repeated to the manager
    detail = client_for(manager).get(f"/api/purchase-orders/{po.id}/").json()
    assert detail["pending_follow_up"]["status"] == "answered" and detail["pending_follow_up"]["answer_summary"] == "Van 400 de 1000; entrega el jueves"
    assert detail["awaiting_reply"] is False


@pytest.mark.django_db
def test_a_skipped_request_hangs_on_the_existing_wait(two_suppliers, production):
    conversation, po = two_suppliers["conversation"], two_suppliers["purchase_order"]
    client_for(production).post(f"/api/purchase-orders/{po.id}/follow-up/", {}, format="json")
    waiting = timezone.now() - timedelta(hours=3)
    PurchaseOrder.objects.filter(pk=po.pk).update(awaiting_reply_since=waiting)  # a checkpoint went meanwhile
    services.finish_turn(claim(conversation), "sess")  # the agent skipped: nothing sent
    request = FollowUpRequest.objects.get(purchase_order=po)
    assert request.status == "asked" and request.asked_at == waiting
    # The order closes before any answer: the request is skipped.
    PurchaseOrder.objects.filter(pk=po.pk).update(status="delivered")
    from manager import services as manager_services

    manager_services.run_monitor()
    request.refresh_from_db()
    assert request.status == "skipped" and request.skip_reason



@pytest.mark.django_db
def test_orders_without_a_channel_are_skipped_with_the_reason(two_suppliers, sales):
    plant = Supplier.objects.create(name="Planta Corpotex", kind="workshop", city="Piura", is_in_house=True)
    mute = Supplier.objects.create(name="Taller Sin Número", kind="workshop", city="Piura")
    for code, supplier in (("PT-0045", plant), ("PT-0046", mute)):
        po = PurchaseOrder.objects.create(code=code, supplier=supplier, status="in_progress")
        PurchaseOrderItem.objects.create(purchase_order=po, requirement=two_suppliers["requirement"], quantity=100, unit_price=Decimal("5"))
    body = client_for(sales).post(f"/api/orders/{two_suppliers['order'].id}/follow-up/", {}, format="json").json()
    rows = {r["purchase_order"]["code"]: r for r in body["requests"]}
    assert (rows["PT-0045"]["status"], rows["PT-0045"]["skip_reason"]) == ("skipped", "sin canal")
    assert (rows["PT-0046"]["status"], rows["PT-0046"]["skip_reason"]) == ("skipped", "sin canal")
    assert "A Planta Corpotex no se le escribe: es la planta propia." in body["detail"]
    assert "A Taller Sin Número no se le puede escribir: no tiene número." in body["detail"]
    assert Turn.objects.filter(reason="follow_up").count() == 2  # the workshop and Gamarra, nobody else


@pytest.mark.django_db
def test_at_night_a_real_whatsapp_waits_until_7_and_the_simulator_goes_now(two_suppliers, sales, monkeypatch):
    night = timezone.make_aware(datetime(2026, 10, 12, 1, 0))
    two_suppliers["purchase_order"].progress_reports.update(acknowledged_at=night)  # nothing but the request in the batch
    monkeypatch.setattr("core.clock.now", lambda config=None: night)
    monkeypatch.setattr("core.clock.today", lambda config=None: night.date())
    body = client_for(sales).post(f"/api/orders/{two_suppliers['order'].id}/follow-up/", {}, format="json").json()
    assert {r["status"] for r in body["requests"]} == {"pending"}
    assert "A Confecciones del Norte se le escribirá a las 07:00: de noche no se le escribe a los proveedores." in body["detail"]
    assert "Le pedimos avance a Avíos Gamarra" in body["detail"] and "WhatsApp" not in body["detail"]
    whatsapp = Turn.objects.get(conversation=two_suppliers["conversation"], reason="follow_up")
    assert whatsapp.available_at == timezone.make_aware(datetime(2026, 10, 12, 7, 0))
    assert claim(two_suppliers["gamarra_conversation"]) is not None  # the simulator answers at once
    whatsapp.available_at = timezone.now() - timedelta(seconds=1)
    whatsapp.save(update_fields=["available_at"])
    assert services.claim_next_turn(two_suppliers["conversation"].id) is None  # and even if dispatched early, the night holds it
