import sys
import types
from datetime import date
from pathlib import Path

import pytest

from agent.persona import style

FIXTURES = Path(__file__).resolve().parent.parent / "agent" / "persona" / "fixtures"

ANALYSIS = {
    "treatment": "usted",
    "summary": "corto y amable",
    "form": ["mensajes cortos"],
    "greetings": ["buenos días, ¿cómo está?"],
    "phrases": ["ya", "nomás"],
    "never_says": ["urgente"],
    "situations": [
        {"situation": "Pedir fecha", "how": "pregunta por un día", "quotes": ["¿para el <FECHA>?"]}
    ],
    "examples": [{"supplier": "ya salió", "manager": ["gracias 🙏"]}],
    "notes": {
        "trato": "usted, le dice <CONTACTO>",
        "tono": "cordial",
        "insistencia": "un mensaje cada 3 días",
        "horario": "",
        "ojo": "cobra en USD",
    },
}


class FakeSdk(types.ModuleType):
    class ClaudeNotConnected(Exception):
        pass

    class ClaudeSDKError(Exception):
        pass

    def __init__(self, replies=None, connected=True):
        super().__init__("agent.sdk")
        self.replies = replies or {}
        self.connected = connected
        self.calls = []

    def is_connected(self):
        return self.connected

    async def complete(self, prompt, *, system_prompt, model, schema=None, effort=None):
        self.calls.append({"prompt": prompt, "system": system_prompt, "model": model})
        for key, reply in self.replies.items():
            if system_prompt.startswith(key):
                return reply(prompt) if callable(reply) else reply
        raise AssertionError(f"unexpected system prompt: {system_prompt[:40]}")


@pytest.fixture
def fake_sdk(monkeypatch):
    def install(**kwargs):
        sdk = FakeSdk(**kwargs)
        monkeypatch.setitem(sys.modules, "agent.sdk", sdk)
        return sdk

    return install


def lima_chat():
    content = (FIXTURES / "textiles-lima-norte.txt").read_text(encoding="utf-8")
    chat = style.parse_whatsapp_export(
        content, "Oscar", since=date(2026, 1, 1), supplier_id=5, supplier_name="Textiles Lima Norte"
    )
    return chat


def raw_chat(supplier_id, messages, contact_names=("Encargada",)):
    return {
        "supplier_id": supplier_id,
        "supplier_name": "Confecciones del Norte",
        "contact_names": list(contact_names),
        "messages": messages,
    }


def test_extract_style_runs_one_analysis_per_supplier_and_one_draft(fake_sdk):
    sdk = fake_sdk(
        replies={
            "Analizas": ANALYSIS,
            "Escribes el estilo": {"style_md": style.load_template()},
        }
    )
    progress = []
    result = style.extract_style(
        [lima_chat()],
        date(2026, 1, 1),
        on_progress=lambda *args, **kwargs: progress.append((args, kwargs)),
        manager_names=("Oscar",),
    )

    assert result["style_md"].startswith("# Estilo del Gerente")
    assert result["notes"][5].startswith("Trato: usted, le dice <CONTACTO>")
    assert "Horario" not in result["notes"][5]  # empty fields are left out
    assert [c["model"] for c in sdk.calls] == ["sonnet", "opus"]
    assert [args[1] for args, _ in progress] == ["analyzing", "done", "merging"]
    # The draft never sees supplier names, only labels.
    assert "Textiles Lima Norte" not in sdk.calls[1]["prompt"]
    assert "Proveedor 1" in sdk.calls[1]["prompt"]


def test_extract_style_without_manager_messages_reports_no_chat(fake_sdk):
    fake_sdk(replies={})
    chat = raw_chat(
        3, [{"sender": "supplier", "text": "hola", "sent_at": "2026-10-10T10:00:00-05:00"}]
    )
    progress = []
    with pytest.raises(style.StyleError, match="No hay mensajes del Gerente"):
        style.extract_style(
            [chat], date(2026, 10, 10), on_progress=lambda *a, **k: progress.append(a)
        )
    assert progress == [(3, "no_chat")]


def test_extract_style_fails_clearly_when_claude_is_not_connected(fake_sdk):
    fake_sdk(connected=False)
    with pytest.raises(style.StyleError, match="Conecta tu cuenta de Claude"):
        style.extract_style([lima_chat()], date(2026, 1, 1))


def test_invalid_draft_is_retried_once_with_the_validation_errors(fake_sdk):
    drafts = iter(
        [{"style_md": "# Estilo del Gerente\ncorto"}, {"style_md": style.load_template()}]
    )
    sdk = fake_sdk(
        replies={"Analizas": ANALYSIS, "Escribes el estilo": lambda prompt: next(drafts)}
    )
    style.extract_style([lima_chat()], date(2026, 1, 1))
    retry = sdk.calls[-1]["prompt"]
    assert "<error_anterior>" in retry
    assert "Falta la sección" in retry


def test_draft_that_names_a_supplier_is_rejected(fake_sdk):
    leaky = {"style_md": style.load_template() + "\ncon Textiles Lima Norte usa usted\n"}
    fake_sdk(replies={"Analizas": ANALYSIS, "Escribes el estilo": leaky})
    with pytest.raises(style.StyleError, match="Textiles Lima Norte"):
        style.extract_style([lima_chat()], date(2026, 1, 1))


def test_update_style_returns_changelog(fake_sdk):
    update = {
        "style_md": style.load_template(),
        "notes": [
            {
                "supplier": "Proveedor 1",
                "notes": {"trato": "tú", "tono": "cercano", "insistencia": "uno al día"},
            }
        ],
        "changelog": ["con Proveedor 1 ahora escribe de tú", "  "],
    }
    sdk = fake_sdk(replies={"Actualizas": update})
    chat = raw_chat(
        3,
        [
            {"sender": "manager", "text": "buenas causa", "sent_at": "2026-10-11T09:00:00-05:00"},
            {"sender": "agent", "text": "del bot", "sent_at": "2026-10-11T09:05:00-05:00"},
        ],
    )
    result = style.update_style(style.load_template(), {3: "Trato: usted"}, [chat])

    assert result["changelog"] == ["con Proveedor 1 ahora escribe de tú"]
    assert result["notes"][3].startswith("Trato: tú")
    assert "del bot" not in sdk.calls[0]["prompt"]  # the agent's own messages never teach style
    assert "Trato: usted" in sdk.calls[0]["prompt"]


def test_update_style_without_new_manager_messages_skips_the_model(fake_sdk):
    sdk = fake_sdk(connected=False)  # would fail if it tried to call the model
    chat = raw_chat(
        3, [{"sender": "agent", "text": "hola", "sent_at": "2026-10-11T09:00:00-05:00"}]
    )
    result = style.update_style("estilo", {3: "notas"}, [chat])
    assert result == {"style_md": "estilo", "notes": {3: "notas"}, "changelog": []}
    assert sdk.calls == []


def test_build_transcript_marks_gaps_and_skips_the_agent():
    transcript, managers = style.build_transcript(
        [
            {"sender": "manager", "text": "¿cómo va?", "sent_at": "2026-10-01T09:00:00-05:00"},
            {"sender": "agent", "text": "del bot", "sent_at": "2026-10-01T09:01:00-05:00"},
            {"sender": "supplier", "text": "bien", "sent_at": "2026-10-03T10:00:00-05:00"},
        ]
    )
    assert transcript == "[G] ¿cómo va?\n[P] (+2d) bien"
    assert managers == 1


def test_inline_refs_removes_defs():
    schema = style._inline_refs(style.SupplierAnalysis.model_json_schema())
    assert "$defs" not in str(schema) and "$ref" not in str(schema)
