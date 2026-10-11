"""ADR 0030: the manager pauses the agent for one supplier or for all. While paused the agent writes
nothing to that supplier (WhatsApp or simulator): incoming messages are kept, their turns are
born `skipped`, the tick plans no follow-up and a person's request is skipped. The dashboard
assistants never pause. Resuming queues only the first contacts approved during the pause."""

from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from core.models import Config
from manager import follow_up
from messaging import services
from messaging.models import Message, Turn
from operations import follow_up_requests
from operations.models import PurchaseOrder
from suppliers.models import Supplier
from tests.test_follow_up import at, claim, frozen, opening, ten_days  # noqa: F401
from tests.test_magic_order import client_for


def pause_all(paused=True):
    config = Config.load()
    config.agent_paused = paused
    config.save()


def supplier_writes(conversation, text="ya van 400"):
    Message.objects.create(conversation=conversation, author="supplier", text=text, status="received", sent_at=timezone.now())
    return services.enqueue_turn(conversation, "message")


@pytest.mark.django_db
def test_a_paused_supplier_gets_no_turn_but_its_messages_are_kept(ten_days, manager, sales, django_capture_on_commit_callbacks):
    supplier, conversation = ten_days["supplier"], ten_days["conversation"]
    assert client_for(sales).patch(f"/api/suppliers/{supplier.id}/", {"agent_paused": True}, format="json").status_code == 403
    response = client_for(manager).patch(f"/api/suppliers/{supplier.id}/", {"agent_paused": True}, format="json")
    assert response.status_code == 200 and response.json()["agent_paused"] is True
    with mock.patch.object(services, "dispatch_turn") as dispatch, django_capture_on_commit_callbacks(execute=True):
        turn = supplier_writes(conversation)
    dispatch.assert_not_called()
    assert (turn.status, turn.error) == ("skipped", "Agente en pausa")
    message = conversation.messages.get(text="ya van 400")
    assert message.status == "processed"  # kept in the conversation, never answered later
    # Resumed: the next message gets a normal turn, without the one from the pause.
    client_for(manager).patch(f"/api/suppliers/{supplier.id}/", {"agent_paused": False}, format="json")
    with mock.patch.object(services, "dispatch_turn") as dispatch, django_capture_on_commit_callbacks(execute=True):
        turn = supplier_writes(conversation, "¿me confirman el adelanto?")
    assert turn.status == "pending" and dispatch.call_count == 1
    batch = claim(conversation)
    assert [Message.objects.get(pk=i).text for i in batch.message_ids] == ["¿me confirman el adelanto?"]


@pytest.mark.django_db
def test_a_turn_queued_before_the_global_pause_is_skipped_and_assistants_keep_working(ten_days, manager):
    conversation = ten_days["conversation"]
    turn = supplier_writes(conversation)
    assert turn.status == "pending"
    pause_all()
    assert claim(conversation) is None
    turn.refresh_from_db()
    assert (turn.status, turn.error) == ("skipped", "Agente en pausa")
    assistant = services.dashboard_conversation(manager)
    assert services.enqueue_turn(assistant, "message").status == "pending"  # the assistants never pause
    # A turn already running when the pause came cannot send anything either.
    from messaging.exceptions import SendFailed

    with pytest.raises(SendFailed, match="Agente en pausa"):
        services.send_text(conversation, "¿Cómo va?", None)
    assert not conversation.messages.filter(author="agent").exists()


@pytest.mark.django_db
def test_the_tick_plans_nothing_for_a_paused_supplier_nor_during_a_global_pause(ten_days):
    supplier = ten_days["supplier"]
    with frozen(at(15, 8, 30)):
        assert len(follow_up.plan_for_today()) == 1  # the 30 % checkpoint, as in test_follow_up
    Supplier.objects.filter(pk=supplier.pk).update(agent_paused=True)
    with frozen(opening(ten_days, 15) + timedelta(minutes=1)):
        assert follow_up.plan_for_today() == [] and follow_up.enqueue_due_follow_ups() == 0
    Supplier.objects.filter(pk=supplier.pk).update(agent_paused=False)
    pause_all()
    with frozen(opening(ten_days, 15) + timedelta(minutes=1)):
        assert follow_up.plan_for_today() == [] and follow_up.enqueue_due_follow_ups() == 0
    assert not Turn.objects.filter(conversation=ten_days["conversation"]).exists()
    po = PurchaseOrder.objects.get(pk=ten_days["purchase_order"].pk)
    assert po.awaiting_reply_since is None


@pytest.mark.django_db
def test_a_persons_request_to_a_paused_supplier_is_skipped(ten_days, production):
    Supplier.objects.filter(pk=ten_days["supplier"].pk).update(agent_paused=True)
    po = PurchaseOrder.objects.get(pk=ten_days["purchase_order"].pk)
    result = follow_up_requests.request_follow_up([po], actor=production, subject=po.code)
    [row] = result["requests"]
    assert row["status"] == "skipped" and row["skip_reason"] == "agente en pausa"
    assert "el agente está en pausa" in result["detail"]
    assert not Turn.objects.filter(conversation=ten_days["conversation"]).exists()


@pytest.mark.django_db
def test_global_settings_and_resume_send_the_first_contacts_approved_meanwhile(ten_days, manager, production):
    client = client_for(manager)
    assert client_for(production).get("/api/settings/agent/").status_code == 403
    assert client.get("/api/settings/agent/").json() == {"paused": False, "paused_suppliers": 0}
    assert client.patch("/api/settings/agent/", {"paused": True}, format="json").json() == {"paused": True, "paused_suppliers": 0}
    # Approved during the pause: its first contact never went.
    po = ten_days["purchase_order"]
    PurchaseOrder.objects.filter(pk=po.pk).update(status="approved")
    turn = services.enqueue_turn(ten_days["conversation"], "purchase_order_approved")
    assert turn.status == "skipped"
    monitor = client.get("/api/monitor/").json()
    assert monitor["agent"] == {"paused": True, "paused_suppliers": 0}
    assert client.patch("/api/settings/agent/", {"paused": False}, format="json").json()["paused"] is False
    resumed = Turn.objects.get(conversation=ten_days["conversation"], status="pending")
    assert resumed.reason == "purchase_order_approved"
    batch = claim(ten_days["conversation"])
    assert batch.new_purchase_order_ids == [po.id]


@pytest.mark.django_db
def test_supplier_card_and_plant_capacity(ten_days, manager):
    from operations.models import StatusChange

    supplier = ten_days["supplier"]
    plant = Supplier.objects.create(name="Planta Corpotex", kind="workshop", is_in_house=True, weekly_capacity=2000)
    po = ten_days["purchase_order"]
    PurchaseOrder.objects.filter(pk=po.pk).update(supplier=plant)
    delivered = PurchaseOrder.objects.create(code="PT-0099", supplier=supplier, status="delivered")
    StatusChange.objects.create(purchase_order=delivered, status="delivered", at=at(9, 16), actor="agent")
    PurchaseOrder.objects.create(code="PT-0098", supplier=supplier, status="suggested")
    rows = {s["name"]: s for s in client_for(manager).get("/api/suppliers/").json()}
    norte = rows["Confecciones del Norte"]
    assert norte["agent_paused"] is False and norte["whatsapp_ready"] is True
    assert norte["purchase_orders_count"] == 1 and norte["last_delivered_on"] == "2026-10-09"  # the suggestion never reached it
    assert rows["Planta Corpotex"]["whatsapp_ready"] is False and rows["Planta Corpotex"]["last_delivered_on"] is None
    monitor = client_for(manager).get("/api/monitor/").json()
    assert monitor["plant"] == {"name": "Planta Corpotex", "weekly_capacity": 2000, "units_in_progress": 1000, "load_pct": 50.0, "open_purchase_orders": 1}
    assert monitor["agent"] == {"paused": False, "paused_suppliers": 0}
