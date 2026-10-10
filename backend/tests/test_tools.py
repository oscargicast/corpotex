import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from agent_fakes import FOREIGN_CODE, MISSING_CODE, REPORT_URL, ManagerApprovalRequired, install

from agent import tools


def conversation(active=True):
    number = SimpleNamespace(active=active, simulated=False)
    return SimpleNamespace(pk=7, channel="whatsapp", allowed_number=number)


BATCH = SimpleNamespace(turn="turno", message_ids=[40, 41])


def toolset(conv=None):
    return {t.name: t for t in tools.whatsapp_tools(conv or conversation(), BATCH)}


def call(name, args, conv=None):
    out = asyncio.run(toolset(conv)[name].handler(args))
    return out.get("is_error", False), out["content"][0]["text"]


def services(calls, name):
    return [(args, kwargs) for n, args, kwargs in calls.services if n == name]


def test_names_match_the_glossary(monkeypatch):
    install(monkeypatch)
    assert set(toolset()) == {
        "send_message",
        "confirm_purchase_order",
        "record_progress",
        "report_cancellation",
        "escalate_to_manager",
        "read_history",
        "send_report_link",
    }


def test_send_message_uses_channel_of_conversation(monkeypatch):
    calls = install(monkeypatch)
    conv = conversation()
    assert call("send_message", {"text": "Buenas"}, conv) == (False, "Enviado.")
    assert calls.sent == [(conv, "Buenas", "turno")]


def test_send_message_to_inactive_number_tells_model_without_failing(monkeypatch):
    calls = install(monkeypatch)
    is_error, text = call("send_message", {"text": "Buenas"}, conversation(active=False))
    assert is_error and "no está habilitado" in text
    assert calls.sent == []


def test_confirm_converts_types_for_the_service(monkeypatch):
    calls = install(monkeypatch)
    args = {"code": "PT-0001", "unit_price": 12.5, "committed_on": "2026-10-18", "terms": "50/50"}
    assert call("confirm_purchase_order", args) == (False, "Pedido PT-0001 confirmado.")
    ((po,), kwargs) = services(calls, "confirm_purchase_order")[0]
    assert po.code == "PT-0001"
    assert kwargs == {
        "unit_price": Decimal("12.5"),
        "committed_on": date(2026, 10, 18),
        "terms": "50/50",
    }


def test_confirm_above_rate_tells_model_to_escalate(monkeypatch):
    def above_rate(po, **kwargs):
        raise ManagerApprovalRequired("el precio pasa la tarifa de S/ 12.50")

    install(monkeypatch, confirm_purchase_order=above_rate)
    args = {"code": "PT-0001", "unit_price": 14, "committed_on": "2026-10-18", "terms": ""}
    is_error, text = call("confirm_purchase_order", args)
    assert is_error
    assert "escalate_to_manager" in text and "pasa la tarifa" in text


@pytest.mark.parametrize("code", [FOREIGN_CODE, MISSING_CODE])
def test_tools_reject_foreign_purchase_order(monkeypatch, code):
    calls = install(monkeypatch)
    is_error, _ = call("record_progress", {"code": code, "units_done": 10})
    assert is_error
    assert services(calls, "record_progress") == []


def test_record_progress_attaches_the_photo_of_this_batch(monkeypatch):
    calls = install(monkeypatch)
    call("record_progress", {"code": "PT-0001", "units_done": 120, "note": "foto"})
    assert services(calls, "latest_photo_id") == [(([40, 41],), {})]
    ((_,), kwargs) = services(calls, "record_progress")[0]
    assert kwargs == {"units_done": 120, "note": "foto", "message_id": 41, "actor": None}


def test_escalate_creates_decision_in_this_conversation(monkeypatch):
    calls = install(monkeypatch)
    conv = conversation()
    args = {
        "kind": "price",
        "codes": ["PT-0001"],
        "summary": "Pide S/ 14",
        "detail": "subió el hilo",
    }
    assert call("escalate_to_manager", args, conv)[0] is False
    ((), kwargs) = services(calls, "create_decision")[0]
    assert kwargs["kind"] == "price"
    assert kwargs["conversation"] is conv
    assert [po.code for po in kwargs["purchase_orders"]] == ["PT-0001"]


def test_send_report_link_never_exposes_token_in_prompt(monkeypatch):
    calls = install(monkeypatch)
    is_error, text = call("send_report_link", {"code": "PT-0001", "intro": "Si te es más fácil:"})
    assert not is_error and REPORT_URL not in text
    assert calls.sent[0][1] == f"Si te es más fácil:\n{REPORT_URL}"
    assert len(services(calls, "mark_report_link_sent")) == 1


@pytest.mark.parametrize("intro", ["", "mira https://otro.link", "x" * 201])
def test_report_link_falls_back_to_neutral_template(monkeypatch, intro):
    calls = install(monkeypatch)
    call("send_report_link", {"code": "PT-0001", "intro": intro})
    assert calls.sent[0][1] == f"Para reportar avance y fotos del pedido PT-0001:\n{REPORT_URL}"
