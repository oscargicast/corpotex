"""In-memory stand-ins for the modules the agent imports lazily (messaging, core, persona,
tools), so the agent's tests run without a database or the real SDK."""

import sys
import types
from types import SimpleNamespace


class NumberNotAllowed(Exception):
    pass


def install(monkeypatch, **overrides):
    """Put fake modules in sys.modules. `overrides` replaces any function by name."""
    calls = SimpleNamespace(
        sent=[], finished=[], disconnected=[], prompts=[], NumberNotAllowed=NumberNotAllowed
    )

    def send_text(conversation, text, turn):
        calls.sent.append((conversation, text, turn))

    def finish_turn(batch, session_id, error=None):
        calls.finished.append((batch, session_id, error))

    def mark_claude_disconnected(error_text, batch=None):
        calls.disconnected.append((error_text, batch))

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
        },
        "messaging.exceptions": {"NumberNotAllowed": NumberNotAllowed},
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
