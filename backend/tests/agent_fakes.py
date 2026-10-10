"""In-memory stand-ins for the modules the agent imports lazily (messaging, operations,
manager, core, persona, tools), so the agent's tests run without a database or the SDK."""

import sys
import types
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
        },
        "operations.exceptions": {"ManagerApprovalRequired": ManagerApprovalRequired},
        "manager.services": {"create_decision": recorder("create_decision")},
        "core.claude_auth": {"mark_claude_disconnected": mark_claude_disconnected},
        "agent.persona": {
            "build_prompt": build_prompt,
            "build_assistant_prompt": build_assistant_prompt,
        },
        "agent.tools": {
            "whatsapp_tools": lambda conversation, batch: [],
            "assistant_tools": lambda conversation, batch: [],
        },
    }
    for name, attrs in modules.items():
        module = types.ModuleType(name)
        for attr, value in attrs.items():
            setattr(module, attr, overrides.get(attr, value))
        monkeypatch.setitem(sys.modules, name, module)
    return calls
