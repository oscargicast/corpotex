"""ADR 0027 (S1): proactive follow-up planned by code inside the manager's window, one message per
supplier and day plus a reminder; the agent decides whether to write (S2)."""

from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from unittest import mock

import pytest
from django.utils import timezone

from core.models import Config
from manager import follow_up, services as manager_services
from manager.models import Alert
from messaging import services
from messaging.models import Message, Turn
from operations.models import ProgressReport, PurchaseOrder, PurchaseOrderItem, StatusChange
from tests.scenario import build


def at(day: int, hour: int = 10, minute: int = 0) -> datetime:
    return timezone.make_aware(datetime(2026, 10, day, hour, minute))


@contextmanager
def frozen(when: datetime):
    """Both the planner and the turn machinery read `core.clock`."""
    with mock.patch("core.clock.now", return_value=when), mock.patch("core.clock.today", return_value=timezone.localtime(when).date()):
        yield


@pytest.fixture
def ten_days(db, sales):
    """A workshop order confirmed on Monday 12/10 for Thursday 22/10: a 10-day term."""
    data = build(owner=sales)
    po = data["purchase_order"]
    po.progress_reports.all().delete()
    PurchaseOrder.objects.filter(pk=po.pk).update(status="in_progress", committed_on=date(2026, 10, 22), internal_due_on=date(2026, 10, 22), next_follow_up_at=None)
    StatusChange.objects.create(purchase_order=po, status="confirmed", at=at(12, 9), actor="agent")
    data["purchase_order"] = PurchaseOrder.objects.get(pk=po.pk)
    return data


def opening(data, day: int) -> datetime:
    """The supplier's first slot of the day: 09:00 plus its fixed offset."""
    return at(day, 9) + follow_up.offset_for(data["supplier"])


def claim(conversation):
    Turn.objects.filter(conversation=conversation, status="pending").update(available_at=timezone.now() - timedelta(seconds=1))
    return services.claim_next_turn(conversation.id)


def agent_says(batch, text="¿Cómo va el avance?"):
    from core import clock

    Message.objects.create(conversation=batch.turn.conversation, author="agent", text=text, status="sent", sent_at=clock.now(), turn=batch.turn)


def test_checkpoints_of_a_ten_day_order_by_mode():
    assert follow_up.checkpoint_days("minimal", 10) == {5: "punto de control del 50 %", 9: "víspera de la entrega"}
    assert follow_up.checkpoint_days("balanced", 10) == {3: "punto de control del 30 %", 6: "punto de control del 60 %", 8: "punto de control del 85 %", 9: "víspera de la entrega"}
    assert set(follow_up.checkpoint_days("high", 10)) == set(range(1, 10)) and follow_up.checkpoint_days("high", 10)[4] == "control diario"
    assert follow_up.checkpoint_days("balanced", 1) == {}  # a one-day order is "delivery today/tomorrow"


@pytest.mark.django_db
def test_checkpoint_days_in_each_mode_on_the_real_plan(ten_days):
    supplier = ten_days["supplier"]
    # Without units there is no "behind" nor "no report" case: only checkpoints, plus "entrega hoy"
    # on 22/10, which goes in every mode. 18/10 is Sunday.
    PurchaseOrderItem.objects.filter(purchase_order=ten_days["purchase_order"]).delete()
    expected = {"minimal": {17, 21, 22}, "balanced": {15, 19, 20, 21, 22}, "high": {13, 14, 15, 16, 17, 19, 20, 21, 22}}  # day 5 = 17/10
    for mode, days in expected.items():
        supplier.follow_up_mode = mode
        supplier.save(update_fields=["follow_up_mode"])
        planned = set()
        for day in range(12, 23):
            with frozen(at(day, 9, 30)):
                if follow_up.plan_for_today():
                    planned.add(day)
        assert planned == days, mode
    # Balanced's 60 % falls on Sunday 18/10 and moves to Monday 19/10.
    supplier.follow_up_mode = ""
    supplier.save(update_fields=["follow_up_mode"])
    with frozen(at(19, 9, 30)):
        assert follow_up.plan_for_today()[0].reason == "punto de control del 60 %"


@pytest.mark.django_db
def test_checkpoint_goes_once_inside_the_window_and_starts_the_wait(ten_days):
    conversation, po = ten_days["conversation"], ten_days["purchase_order"]
    with frozen(at(15, 8, 30)):  # before the window
        assert follow_up.enqueue_due_follow_ups() == 0
        plan = follow_up.plan_for_today()
        assert [(p.kind, p.reason, p.at) for p in plan] == [("checkpoint", "punto de control del 30 %", opening(ten_days, 15))]
    slot = opening(ten_days, 15) + timedelta(minutes=1)
    with frozen(slot):
        assert follow_up.enqueue_due_follow_ups() == 1
        assert follow_up.enqueue_due_follow_ups() == 0  # one turn at a time
        turn = Turn.objects.get(conversation=conversation, status="pending")
        assert turn.reason == "follow_up" and turn.follow_up["kind"] == "checkpoint" and turn.follow_up["mode"] == "balanced"
        batch = claim(conversation)
        assert batch.follow_up["reason"] == "punto de control del 30 %" and batch.follow_up_purchase_order_ids == [po.id]
        state = services.turn_state(batch)
        assert set(state["follow_up"]) == {"mode", "kind", "reason", "last_supplier_message_at", "last_agent_message_at", "last_supplier_message", "last_agent_message", "pending_decisions"}
        row = next(p for p in state["purchase_orders"] if p["code"] == po.code)
        assert row["follow_up_reason"] == "punto de control del 30 %" and row["expected_units"] == 300 and row["total_units"] == 1000
        assert row["awaiting_reply_since"] is None and row["follow_up_note"] == "" and state["follow_up"]["pending_decisions"][0]["kind"] == "price"
        agent_says(batch)
        services.finish_turn(batch, "sess")
    po.refresh_from_db()
    assert po.last_follow_up_on == date(2026, 10, 15) and po.awaiting_reply_since is not None and po.reminded_at is None
    with frozen(at(15, 12)):
        assert follow_up.enqueue_due_follow_ups() == 0  # the day's message went; the reminder waits 4 h


@pytest.mark.django_db
def test_no_report_past_30_percent_is_always_considered(ten_days):
    ten_days["supplier"].follow_up_mode = "minimal"
    ten_days["supplier"].save(update_fields=["follow_up_mode"])
    with frozen(at(17, 9, 30)):  # day 5 of 10, no report at all: written even in minimal
        assert follow_up.plan_for_today()[0].reason == "sin reporte de avance (50 % del plazo)"


@pytest.mark.django_db
def test_balanced_skips_the_checkpoint_when_progress_is_on_pace(ten_days):
    po = ten_days["purchase_order"]
    ProgressReport.objects.create(purchase_order=po, units_done=300, reported_at=at(14, 17))  # 30 % on day 3: on pace
    with frozen(at(15, 9, 30)):
        assert follow_up.plan_for_today() == []
    ProgressReport.objects.filter(purchase_order=po).update(units_done=100)  # 10 % against 30 %: behind, always considered
    with frozen(at(15, 9, 30)):
        assert follow_up.plan_for_today()[0].reason == "avance atrasado (10 % contra 30 % esperado)"


@pytest.mark.django_db
def test_reminder_after_4_hours_then_stalled_until_the_supplier_answers(ten_days):
    conversation, po = ten_days["conversation"], ten_days["purchase_order"]
    PurchaseOrder.objects.filter(pk=po.pk).update(last_follow_up_on=date(2026, 10, 15), awaiting_reply_since=at(15, 10, 5))
    with frozen(at(15, 13)):
        plan = follow_up.plan_for_today()
        assert [(p.kind, p.at, p.reason) for p in plan] == [("reminder", at(15, 14, 5), "sin respuesta desde las 10:05")]
        assert follow_up.enqueue_due_follow_ups() == 0
    with frozen(at(15, 14, 6)):
        assert follow_up.enqueue_due_follow_ups() == 1
        batch = claim(conversation)
        assert batch.follow_up["kind"] == "reminder"
        agent_says(batch, "¿Me confirma?")
        services.finish_turn(batch, "sess")
    po.refresh_from_db()
    assert po.reminded_at == at(15, 14, 6) and po.awaiting_reply_since == at(15, 10, 5)
    with frozen(at(15, 18, 10)):
        assert follow_up.plan_for_today() == []  # no second reminder
        manager_services.run_monitor()
        assert Alert.objects.filter(kind="stalled_purchase_order", purchase_order=po, status="open").exists()
        Message.objects.create(conversation=conversation, author="supplier", text="Vamos en 400", status="received", sent_at=timezone.now())
        services.enqueue_turn(conversation, "message")  # an inbound message clears the wait
        po.refresh_from_db()
        assert po.awaiting_reply_since is None and po.reminded_at is None
        manager_services.run_monitor()
        assert not Alert.objects.filter(kind="stalled_purchase_order", purchase_order=po, status="open").exists()


@pytest.mark.django_db
def test_skipping_still_spends_the_day_and_a_skipped_reminder_still_alerts(ten_days):
    conversation, po = ten_days["conversation"], ten_days["purchase_order"]
    with frozen(opening(ten_days, 15) + timedelta(minutes=1)):
        follow_up.enqueue_due_follow_ups()
        batch = claim(conversation)
        PurchaseOrder.objects.filter(pk=po.pk).update(follow_up_note="Ya avisó que entrega el lunes")  # what skip_follow_up writes
        services.finish_turn(batch, "sess")
    po.refresh_from_db()
    assert po.last_follow_up_on == date(2026, 10, 15) and po.awaiting_reply_since is None and po.follow_up_note
    PurchaseOrder.objects.filter(pk=po.pk).update(awaiting_reply_since=at(15, 10, 5))
    with frozen(at(15, 14, 6)):
        follow_up.enqueue_due_follow_ups()
        services.finish_turn(claim(conversation), "sess")  # the agent skipped the reminder
    po.refresh_from_db()
    assert po.reminded_at == at(15, 14, 6) and po.awaiting_reply_since == at(15, 10, 5)  # still waiting
    with frozen(at(15, 18, 10)):
        manager_services.run_monitor()
    assert Alert.objects.filter(kind="stalled_purchase_order", purchase_order=po, status="open").exists()  # the manager still learns of the silence


@pytest.mark.django_db
def test_nothing_is_queued_outside_the_window_or_on_sunday(ten_days):
    with frozen(at(15, 18, 30)):
        assert follow_up.enqueue_due_follow_ups() == 0
    with frozen(at(18, 10)):  # Sunday
        assert follow_up.plan_for_today() == [] and follow_up.enqueue_due_follow_ups() == 0
    config = Config.load()
    config.follow_up_weekdays = [0, 1, 2, 3, 4, 5, 6]
    config.save()
    with frozen(at(18, 10)):
        assert follow_up.plan_for_today()  # once the manager adds Sunday, the 60 % checkpoint goes that day
    assert not Turn.objects.filter(reason="follow_up").exists()


@pytest.mark.django_db
def test_follow_up_turn_waits_for_the_window_even_if_queued(ten_days):
    conversation = ten_days["conversation"]
    with frozen(opening(ten_days, 15) + timedelta(minutes=1)):
        follow_up.enqueue_due_follow_ups()
    with frozen(at(15, 19)):
        assert claim(conversation) is None  # Claude was paused until after 18:00: it waits for the next window
    assert Turn.objects.get(conversation=conversation, reason="follow_up").status == "pending"


@pytest.mark.django_db
def test_one_turn_for_a_supplier_with_two_orders(ten_days):
    first = ten_days["purchase_order"]
    second = PurchaseOrder.objects.create(
        code="PT-0002", supplier=ten_days["supplier"], conversation=ten_days["conversation"], status="confirmed", committed_on=date(2026, 10, 16), internal_due_on=date(2026, 10, 16)
    )
    PurchaseOrderItem.objects.create(purchase_order=second, requirement=ten_days["requirement"], quantity=200, unit_price="6.50")
    StatusChange.objects.create(purchase_order=second, status="confirmed", at=at(13, 9), actor="agent")
    with frozen(opening(ten_days, 15) + timedelta(minutes=1)):
        assert follow_up.enqueue_due_follow_ups() == 1
    turn = Turn.objects.get(reason="follow_up")
    assert set(turn.follow_up["purchase_orders"]) == {str(first.id), str(second.id)}
    assert turn.follow_up["reason"] == "PT-0002: entrega mañana; PT-0001: punto de control del 30 %"  # soonest delivery first


@pytest.mark.django_db
def test_follow_up_settings_api(ten_days, manager_client, sales_client, production):
    body = manager_client.get("/api/settings/follow-up/").json()
    assert body == {"mode": "balanced", "mode_display": "Balanceado", "window_start": "09:00", "window_end": "18:00", "weekdays": [0, 1, 2, 3, 4, 5]}
    assert sales_client.get("/api/settings/follow-up/").status_code == 403
    assert manager_client.patch("/api/settings/follow-up/", {"window_start": "18:00", "window_end": "09:00"}, format="json").status_code == 400
    assert manager_client.patch("/api/settings/follow-up/", {"window_start": "09:00", "window_end": "10:30"}, format="json").status_code == 400
    assert manager_client.patch("/api/settings/follow-up/", {"weekdays": []}, format="json").status_code == 400
    changed = manager_client.patch("/api/settings/follow-up/", {"mode": "minimal", "window_start": "08:00", "weekdays": [5, 0, 0, 2]}, format="json")
    assert changed.status_code == 200, changed.content
    assert changed.json() == {"mode": "minimal", "mode_display": "Mínimo", "window_start": "08:00", "window_end": "18:00", "weekdays": [0, 2, 5]}
    manager_client.patch("/api/settings/follow-up/", {"mode": "balanced", "window_start": "09:00", "weekdays": [0, 1, 2, 3, 4, 5]}, format="json")
    with frozen(at(15, 9, 30)):
        plan = manager_client.get("/api/settings/follow-up/preview/").json()
    assert plan == [{"supplier": {"id": ten_days["supplier"].id, "name": "Confecciones del Norte"}, "purchase_orders": ["PT-0001"], "at": plan[0]["at"], "kind": "checkpoint", "reason": "punto de control del 30 %", "mode": "balanced"}]
    assert sales_client.get("/api/settings/follow-up/preview/").status_code == 403

    supplier_url = f"/api/suppliers/{ten_days['supplier'].id}/"
    assert manager_client.patch(supplier_url, {"follow_up_mode": "minimal"}, format="json").json()["follow_up_mode"] == "minimal"
    assert manager_client.patch(supplier_url, {"follow_up_mode": ""}, format="json").json()["follow_up_mode"] == ""
    assert manager_client.patch(supplier_url, {"follow_up_mode": "mucho"}, format="json").status_code == 400


@pytest.mark.django_db
def test_an_overdue_reminder_from_an_earlier_day_still_goes(ten_days):
    """agente, 11/10: a reminder due yesterday (tick down, window changed) must not be lost."""
    po = ten_days["purchase_order"]
    PurchaseOrder.objects.filter(pk=po.pk).update(last_follow_up_on=date(2026, 10, 14), awaiting_reply_since=at(14, 10, 0))  # due 14/10 14:00, never sent
    with frozen(at(16, 11)):
        plan = follow_up.plan_for_today()
        assert [(p.kind, p.reason, p.at) for p in plan] == [("reminder", "sin respuesta desde el 14/10", at(14, 14, 0))]
        assert follow_up.enqueue_due_follow_ups() == 1
