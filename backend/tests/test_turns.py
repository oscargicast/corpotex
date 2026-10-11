"""Turn queue (ADR 0010/0018): batching, claim, finish, retries, pause and quiet hours."""

from datetime import datetime, timedelta
from unittest import mock

import pytest
from django.utils import timezone

from core.models import Config
from manager.models import Alert, AlertNotification
from messaging import services
from messaging.models import AllowedNumber, Conversation, Message, Turn
from operations.models import PurchaseOrder
from tests.scenario import build


@pytest.fixture
def scenario(db, sales):
    return build(owner=sales)


def inbound(conversation, text="hola", status="received"):
    return Message.objects.create(conversation=conversation, author="supplier", text=text, status=status, sent_at=timezone.now())


@pytest.mark.django_db
def test_enqueue_reuses_the_pending_turn_and_batches(scenario):
    conversation = scenario["conversation"]
    first = services.enqueue_turn(conversation, "message")
    second = services.enqueue_turn(conversation, "message")
    assert first.id == second.id
    assert Turn.objects.filter(conversation=conversation).count() == 1
    assert second.available_at <= first.created_at + services.BATCH_CAP
    assert second.available_at > timezone.now()


@pytest.mark.django_db
def test_dashboard_turn_is_available_right_away(manager):
    conversation = services.dashboard_conversation(manager)
    turn = services.enqueue_turn(conversation, "message")
    assert turn.available_at <= timezone.now()


@pytest.mark.django_db
def test_claim_returns_the_batch_and_locks_the_conversation(scenario):
    conversation = scenario["conversation"]
    m1, m2 = inbound(conversation, "a"), inbound(conversation, "b")
    turn = services.enqueue_turn(conversation, "message")
    Turn.objects.filter(pk=turn.pk).update(available_at=timezone.now() - timedelta(seconds=1))

    batch = services.claim_next_turn(conversation.id)
    assert batch.message_ids == [m1.id, m2.id]
    assert batch.follow_up_purchase_order_ids == [scenario["purchase_order"].id]  # next_follow_up_at is due
    assert batch.turn.status == "running"
    assert batch.turn.attempts == 1

    # A new pending turn for the same conversation waits until the running one finishes.
    Turn.objects.create(conversation=conversation, reason="message", available_at=timezone.now() - timedelta(seconds=1))
    assert services.claim_next_turn(conversation.id) is None

    services.finish_turn(batch, "sess-1")
    assert Message.objects.filter(id__in=[m1.id, m2.id], status="processed").count() == 2
    conversation.refresh_from_db()
    assert conversation.agent_session == "sess-1"
    assert Turn.objects.get(pk=batch.turn.pk).status == "done"
    scenario["purchase_order"].refresh_from_db()
    assert scenario["purchase_order"].next_follow_up_at > timezone.now()


@pytest.mark.django_db
def test_empty_batch_is_closed_without_calling_the_model(scenario):
    conversation = scenario["conversation"]
    scenario["purchase_order"].next_follow_up_at = None
    scenario["purchase_order"].save()
    scenario["purchase_order"].progress_reports.update(acknowledged_at=timezone.now())  # Not a pending web report.
    turn = Turn.objects.create(conversation=conversation, reason="message", available_at=timezone.now() - timedelta(seconds=1))
    assert services.claim_next_turn(conversation.id) is None
    turn.refresh_from_db()
    assert turn.status == "done"


@pytest.mark.django_db
def test_queue_is_paused_while_claude_is_disconnected(scenario):
    conversation = scenario["conversation"]
    inbound(conversation)
    Turn.objects.create(conversation=conversation, reason="message", available_at=timezone.now() - timedelta(seconds=1))
    config = Config.load()
    config.claude_last_error = "Not logged in"
    config.save()
    assert services.claim_next_turn(conversation.id) is None
    assert Turn.objects.get().status == "pending"


@pytest.mark.django_db
def test_proactive_only_whatsapp_batch_waits_for_the_quiet_hours(scenario, monkeypatch):
    monkeypatch.setattr(services, "QUIET_HOURS", (21, 7))  # Whatever the .env of the machine says.
    conversation = scenario["conversation"]
    scenario["purchase_order"].progress_reports.update(acknowledged_at=timezone.now())
    PurchaseOrder.objects.filter(pk=scenario["purchase_order"].pk).update(next_follow_up_at=timezone.now() - timedelta(days=2))
    turn = Turn.objects.create(conversation=conversation, reason="follow_up", available_at=timezone.now() - timedelta(seconds=1))
    night = timezone.make_aware(datetime(2026, 10, 10, 22, 30))
    with mock.patch("messaging.services.clock.now", return_value=night):
        assert services.claim_next_turn(conversation.id) is None
    turn.refresh_from_db()
    assert turn.status == "pending"
    day = timezone.make_aware(datetime(2026, 10, 10, 9, 30))
    with mock.patch("messaging.services.clock.now", return_value=day):
        batch = services.claim_next_turn(conversation.id)
    assert batch is not None and batch.is_proactive_only()


@pytest.mark.django_db
def test_errors_requeue_and_the_third_one_gives_up(scenario):
    conversation = scenario["conversation"]
    message = inbound(conversation)
    Turn.objects.create(conversation=conversation, reason="message", available_at=timezone.now() - timedelta(seconds=1))
    for attempt in (1, 2):
        batch = services.claim_next_turn(conversation.id)
        assert batch.turn.attempts == attempt
        services.finish_turn(batch, "sess", error="boom")
        pending = Turn.objects.get(conversation=conversation, status="pending")
        pending.available_at = timezone.now() - timedelta(seconds=1)
        pending.save()
    batch = services.claim_next_turn(conversation.id)
    assert batch.turn.attempts == 3
    services.finish_turn(batch, "sess", error="boom")
    assert not Turn.objects.filter(conversation=conversation, status="pending").exists()
    message.refresh_from_db()
    assert message.status == "error"
    assert Alert.objects.filter(kind="turn_failed", status="open").exists()


@pytest.mark.django_db
def test_dashboard_batch_carries_the_alert_notifications(manager, scenario):
    conversation = services.dashboard_conversation(manager)
    notification = AlertNotification.objects.create(alert=scenario["alert"], user=manager)
    Turn.objects.create(conversation=conversation, reason="alert", available_at=timezone.now() - timedelta(seconds=1))
    batch = services.claim_next_turn(conversation.id)
    assert batch.alert_ids == [scenario["alert"].id]
    services.finish_turn(batch, "sess")
    notification.refresh_from_db()
    assert notification.sent_at is not None


@pytest.mark.django_db
def test_recover_stuck_turns_requeues_without_counting_an_attempt(scenario):
    conversation = scenario["conversation"]
    Turn.objects.create(conversation=conversation, reason="message", status="running", attempts=1, available_at=timezone.now())
    assert services.recover_stuck_turns() == 1
    pending = Turn.objects.get(conversation=conversation, status="pending")
    assert pending.attempts == 0
    assert Turn.objects.filter(status="error", error="worker restarted").count() == 1


@pytest.mark.django_db
def test_purchase_order_for_conversation_rejects_other_suppliers(scenario):
    from suppliers.models import Supplier
    from operations.models import PurchaseOrder

    other = Supplier.objects.create(name="Otro Taller", kind="workshop")
    foreign = PurchaseOrder.objects.create(code="PT-0099", supplier=other, suggested_supplier=other)
    assert services.purchase_order_for_conversation(scenario["conversation"], "PT-0001") == scenario["purchase_order"]
    with pytest.raises(services.ForeignPurchaseOrder):
        services.purchase_order_for_conversation(scenario["conversation"], foreign.code)


@pytest.mark.django_db
def test_conversation_for_supplier_prefers_the_chat_with_the_latest_inbound(scenario):
    supplier = scenario["supplier"]
    simulated = supplier.numbers.get(simulated=True)
    sim_conversation = services.conversation_for_number(simulated, Conversation.Channel.SIMULATOR)
    assert services.conversation_for_supplier(supplier) == scenario["conversation"]  # real number first, WhatsApp
    AllowedNumber.objects.filter(pk=scenario["number"].pk).update(id=scenario["number"].pk)  # ids do not matter: simulated goes last
    assert services.conversation_for_supplier(supplier).channel == "whatsapp"
    inbound(sim_conversation, "desde el simulador")
    assert services.conversation_for_supplier(supplier) == sim_conversation


@pytest.mark.django_db
def test_turn_state_has_no_contact_name_for_simulated_numbers(scenario):
    supplier = scenario["supplier"]
    simulated = supplier.numbers.get(simulated=True)
    simulated.name = "Simulador"  # Even a named simulated number greets nobody.
    simulated.save()
    conversation = services.conversation_for_number(simulated, Conversation.Channel.SIMULATOR)
    turn = Turn.objects.create(conversation=conversation, reason="follow_up", available_at=timezone.now())
    state = services.turn_state(services.TurnBatch(turn=turn))
    assert state["supplier"]["contact_name"] == ""
    real_turn = Turn.objects.create(conversation=scenario["conversation"], reason="follow_up", available_at=timezone.now())
    scenario["number"].name = "Rosa"
    scenario["number"].save()
    assert services.turn_state(services.TurnBatch(turn=real_turn))["supplier"]["contact_name"] == "Rosa"


@pytest.mark.django_db
def test_quiet_hours_can_be_disabled_from_settings(scenario, monkeypatch):
    conversation = scenario["conversation"]
    scenario["purchase_order"].progress_reports.update(acknowledged_at=timezone.now())
    PurchaseOrder.objects.filter(pk=scenario["purchase_order"].pk).update(next_follow_up_at=timezone.now() - timedelta(days=2))
    Turn.objects.create(conversation=conversation, reason="follow_up", available_at=timezone.now() - timedelta(seconds=1))
    night = timezone.make_aware(datetime(2026, 10, 10, 22, 30))
    monkeypatch.setattr(services, "QUIET_HOURS", None)
    with mock.patch("messaging.services.clock.now", return_value=night):
        batch = services.claim_next_turn(conversation.id)
    assert batch is not None and batch.is_proactive_only()
