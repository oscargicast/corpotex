import asyncio
from types import SimpleNamespace
from typing import ClassVar

import pytest

from agent import assistant_tools, sdk
from tests.agent_fakes import MISSING_CODE, install


class Rows:
    """Stand-in for Conversation.objects.filter(pk=...): reads and writes the instance."""

    def __init__(self, conversation):
        self.conversation = conversation

    def values_list(self, field, flat=True):
        return SimpleNamespace(get=lambda: getattr(self.conversation, field))

    def update(self, **fields):
        for name, value in fields.items():
            setattr(self.conversation, name, value)


class Conversation(SimpleNamespace):
    registry: ClassVar[dict] = {}

    class objects:
        @staticmethod
        def filter(pk):
            return Rows(Conversation.registry[pk])


def conversation(role="manager"):
    conv = Conversation(
        pk=11, channel="dashboard", pending_action=None, user=SimpleNamespace(role=role)
    )
    Conversation.registry[conv.pk] = conv
    return conv


def batch(turn_id, message_ids=(1,), alert_ids=()):
    return SimpleNamespace(
        turn=SimpleNamespace(pk=turn_id), message_ids=list(message_ids), alert_ids=list(alert_ids)
    )


def tools_for(conv, turn_id, **kwargs):
    return {t.name: t for t in assistant_tools.assistant_tools(conv, batch(turn_id, **kwargs))}


def call(conv, turn_id, name, args):
    out = asyncio.run(tools_for(conv, turn_id)[name].handler(args))
    return out.get("is_error", False), out["content"][0]["text"]


def services(calls, name):
    return [(args, kwargs) for n, args, kwargs in calls.services if n == name]


APPROVE = {"decision_id": 5, "action": "approve"}


@pytest.mark.parametrize(
    "role, expected",
    [
        ("manager", {"resolve_decision", "acknowledge_alert", "mark_payment_paid", "set_clock"}),
        ("production", {"confirm_order", "record_delivery", "record_progress"}),
        ("sales", set()),
    ],
)
def test_toolset_depends_on_role(monkeypatch, role, expected):
    install(monkeypatch)
    assert set(tools_for(conversation(role), 1)) == expected


def test_sales_toolset_has_no_manager_tools(monkeypatch):
    install(monkeypatch)
    assert "resolve_decision" not in tools_for(conversation("sales"), 1)


def test_alert_only_turn_has_no_tools(monkeypatch):
    install(monkeypatch)
    assert tools_for(conversation(), 1, message_ids=(), alert_ids=(3,)) == {}


def test_propose_stores_pending_action_and_returns_preview(monkeypatch):
    calls = install(monkeypatch)
    conv = conversation()
    is_error, text = call(conv, 1, "resolve_decision", {**APPROVE, "confirmed": False})
    assert not is_error and "Aprobar la decisión 5" in text and "(sí/no)" in text
    assert conv.pending_action == {"tool": "resolve_decision", "args": APPROVE, "turn_id": 1}
    assert services(calls, "resolve_decision") == []


def test_write_tool_with_confirmed_true_without_pending_action_refuses(monkeypatch):
    calls = install(monkeypatch)
    is_error, _ = call(conversation(), 2, "resolve_decision", {**APPROVE, "confirmed": True})
    assert is_error and services(calls, "resolve_decision") == []


def test_confirmed_true_from_same_turn_refuses(monkeypatch):
    calls = install(monkeypatch)
    conv = conversation()
    call(conv, 1, "resolve_decision", {**APPROVE, "confirmed": False})
    is_error, _ = call(conv, 1, "resolve_decision", {**APPROVE, "confirmed": True})
    assert is_error and services(calls, "resolve_decision") == []
    assert conv.pending_action is None


def test_confirmed_with_other_args_refuses_and_clears(monkeypatch):
    calls = install(monkeypatch)
    conv = conversation()
    call(conv, 1, "resolve_decision", {**APPROVE, "confirmed": False})
    is_error, _ = call(
        conv, 2, "resolve_decision", {**APPROVE, "action": "reject", "confirmed": True}
    )
    assert is_error and services(calls, "resolve_decision") == []
    assert conv.pending_action is None


def test_confirmed_in_next_turn_runs_with_actor_and_records_card(monkeypatch):
    calls = install(monkeypatch)
    conv = conversation()
    call(conv, 1, "resolve_decision", {**APPROVE, "confirmed": False})
    assert call(conv, 2, "resolve_decision", {**APPROVE, "confirmed": True})[0] is False
    ((decision,), kwargs) = services(calls, "resolve_decision")[0]
    assert decision.pk == 5 and kwargs["action"] == "approve" and kwargs["actor"] is conv.user
    ((_, _, action), _) = services(calls, "record_assistant_action")[0]
    assert action["kind"] == "tool" and action["status"] == "done"
    assert action["links"] == [{"kind": "decision", "id": 5}]
    assert conv.pending_action is None


def test_domain_refusal_records_failed_card(monkeypatch):
    def already_resolved(decision, **kwargs):
        raise ValueError("ya está resuelta con otra acción")

    calls = install(monkeypatch, resolve_decision=already_resolved)
    conv = conversation()
    call(conv, 1, "resolve_decision", {**APPROVE, "confirmed": False})
    is_error, text = call(conv, 2, "resolve_decision", {**APPROVE, "confirmed": True})
    assert is_error and "ya está resuelta" in text
    ((_, _, action), _) = services(calls, "record_assistant_action")[0]
    assert action["status"] == "failed"


def test_missing_object_is_reported_to_the_model(monkeypatch):
    install(monkeypatch)
    is_error, _ = call(
        conversation("production"), 1, "confirm_order", {"code": MISSING_CODE, "confirmed": False}
    )
    assert is_error


def test_stale_pending_action_is_cleared_at_end_of_turn():
    conv = conversation()
    conv.pending_action = {"tool": "set_clock", "args": {}, "turn_id": 1}
    assistant_tools.clear_stale_pending_action(conv, 1)
    assert conv.pending_action is not None  # created in this turn: valid for the next one
    assistant_tools.clear_stale_pending_action(conv, 2)
    assert conv.pending_action is None


def test_finish_posts_reply_and_alert_card(monkeypatch):
    calls = install(monkeypatch)
    conv = conversation()
    reply = sdk.TurnResult("s1", "Listo.")
    assistant_tools.finish_dashboard_turn(conv, batch(1), reply)
    alert_turn = batch(2, message_ids=(), alert_ids=(7, 8))
    assistant_tools.finish_dashboard_turn(conv, alert_turn, sdk.TurnResult("s1", "Aviso"))
    posts = services(calls, "post_assistant_message")
    assert [(args[2], kwargs["action"]) for args, kwargs in posts] == [
        ("Listo.", None),
        ("Aviso", {"kind": "alert", "alert_ids": [7, 8]}),
    ]


def test_failed_turn_posts_nothing(monkeypatch):
    calls = install(monkeypatch)
    failed = sdk.TurnResult("s1", "", error="error_max_turns")
    assistant_tools.finish_dashboard_turn(conversation(), batch(1), failed)
    assert services(calls, "post_assistant_message") == []
