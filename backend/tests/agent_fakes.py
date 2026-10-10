"""In-memory stand-ins for the modules the agent imports lazily (messaging, operations,
manager, core, persona, tools), so the agent's tests run without a database or the SDK."""

import sys
import types
from decimal import Decimal
from types import SimpleNamespace

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

if not settings.configured:  # outside pytest-django (before B1): the agent tests need no DB
    settings.configure()


class NumberNotAllowed(Exception):
    pass


class SendFailed(Exception):
    pass


class ForeignPurchaseOrder(Exception):
    pass


class ManagerApprovalRequired(Exception):
    pass


class FakeModel:
    """Model stand-in: `objects.get(**lookup)` returns a namespace with those fields."""

    def __init_subclass__(cls):
        cls.objects = SimpleNamespace(get=cls.get, select_related=lambda *a: cls.objects)

    @classmethod
    def get(cls, **lookup):
        if MISSING_CODE in lookup.values():
            raise ObjectDoesNotExist(lookup)
        pk = lookup.get("pk", 5)
        return SimpleNamespace(
            pk=pk,
            code=lookup.get("code", "PT-0001"),
            summary="Textiles Lima pide S/ 14",
            text="Orden en peligro",
            amount=Decimal("1875.00"),
            purchase_order=SimpleNamespace(code="PT-0001"),
            purchase_order_id=9,
            get_kind_display=lambda: "Adelanto",
        )


class Decision(FakeModel): ...


class Alert(FakeModel): ...


class Payment(FakeModel): ...


class Order(FakeModel): ...


class PurchaseOrder(FakeModel): ...


FOREIGN_CODE = "PT-9999"
MISSING_CODE = "NOPE"
REPORT_URL = "https://corpotex.oscargicast.com/report/0b6f7c1e-token"


def install(monkeypatch, **overrides):
    """Put fake modules in sys.modules. `overrides` replaces any function by name.

    Every service call lands in `calls.services` as (name, args, kwargs)."""
    calls = SimpleNamespace(
        sent=[],
        finished=[],
        disconnected=[],
        prompts=[],
        services=[],
        NumberNotAllowed=NumberNotAllowed,
    )

    def recorder(name, returns=None):
        def record(*args, **kwargs):
            calls.services.append((name, args, kwargs))
            return returns

        return record

    def send_text(conversation, text, turn):
        calls.sent.append((conversation, text, turn))

    def finish_turn(batch, session_id, error=None):
        calls.finished.append((batch, session_id, error))

    def mark_claude_disconnected(error_text, batch=None):
        calls.disconnected.append((error_text, batch))

    def purchase_order_for_conversation(conversation, code):
        if code == FOREIGN_CODE:
            raise ForeignPurchaseOrder(code)
        if code == MISSING_CODE:
            raise ObjectDoesNotExist(code)
        return SimpleNamespace(code=code)

    def build_prompt(conversation, batch, with_history=False):
        calls.prompts.append(("whatsapp", with_history))
        return "sistema", [{"type": "text", "text": "turno"}]

    def build_assistant_prompt(conversation, batch, with_history=False):
        calls.prompts.append(("dashboard", with_history))
        return "sistema", [{"type": "text", "text": "turno"}]

    modules = {
        "messaging.services": {
            "send_text": send_text,
            "claim_next_turn": lambda conversation_id: None,
            "finish_turn": finish_turn,
            "purchase_order_for_conversation": purchase_order_for_conversation,
            "latest_photo_id": recorder("latest_photo_id", returns=41),
            "message_history": recorder("message_history", returns=[]),
            "record_assistant_action": recorder("record_assistant_action"),
            "post_assistant_message": recorder("post_assistant_message"),
        },
        "messaging.exceptions": {
            "NumberNotAllowed": NumberNotAllowed,
            "SendFailed": SendFailed,
            "ForeignPurchaseOrder": ForeignPurchaseOrder,
        },
        "operations.services": {
            "confirm_purchase_order": recorder("confirm_purchase_order"),
            "record_progress": recorder("record_progress"),
            "cancel_by_supplier": recorder("cancel_by_supplier"),
            "report_url": recorder("report_url", returns=REPORT_URL),
            "mark_report_link_sent": recorder("mark_report_link_sent"),
            "mark_payment_paid": recorder("mark_payment_paid"),
            "confirm_order": recorder("confirm_order"),
            "record_delivery": recorder("record_delivery"),
        },
        "operations.exceptions": {"ManagerApprovalRequired": ManagerApprovalRequired},
        "operations.models": {"Payment": Payment, "Order": Order, "PurchaseOrder": PurchaseOrder},
        "manager.services": {
            "create_decision": recorder("create_decision"),
            "resolve_decision": recorder("resolve_decision"),
            "acknowledge_alert": recorder("acknowledge_alert"),
        },
        "manager.models": {"Decision": Decision, "Alert": Alert},
        "core.clock": {"set_clock": recorder("set_clock")},
        "core.claude_account": {"mark_claude_disconnected": mark_claude_disconnected},
        "agent.persona": {
            "build_prompt": build_prompt,
            "build_assistant_prompt": build_assistant_prompt,
        },
        "agent.tools": {"whatsapp_tools": lambda conversation, batch: []},
        "agent.assistant_tools": {
            "assistant_tools": lambda conversation, batch: [],
            "is_alert_only": lambda batch: False,
            "finish_dashboard_turn": recorder("finish_dashboard_turn"),
        },
    }
    for name, attrs in modules.items():
        module = types.ModuleType(name)
        for attr, value in attrs.items():
            setattr(module, attr, overrides.get(attr, value))
        monkeypatch.setitem(sys.modules, name, module)
    return calls
