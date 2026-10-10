import sys
import types
from datetime import date, timedelta
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from agent.persona.style import load_template
from core import onboarding
from core.models import Config, OnboardingStyle, StyleVersion
from messaging.models import AllowedNumber, Conversation, Message
from suppliers.models import Supplier
from tests.test_style_extraction import ANALYSIS, FakeSdk

FIXTURES = Path(__file__).resolve().parent.parent / "agent" / "persona" / "fixtures"


@pytest.fixture
def fake_sdk(monkeypatch):
    """Patch the real `agent.sdk`: `from agent import sdk` reads the package attribute."""
    import agent.sdk as real_sdk

    def install(**kwargs):
        fake = FakeSdk(**kwargs)
        monkeypatch.setattr(real_sdk, "complete", fake.complete)
        monkeypatch.setattr(real_sdk, "is_connected", fake.is_connected)
        return fake

    return install


URL = "/api/onboarding/style/"


@pytest.fixture
def suppliers(db):
    norte = Supplier.objects.create(name="Confecciones del Norte", kind="workshop", city="Piura")
    AllowedNumber.objects.create(phone="51900000001", name="", supplier=norte, active=True)
    lima = Supplier.objects.create(name="Textiles Lima Norte S.A.C.", kind="material", city="Lima")
    AllowedNumber.objects.create(phone="51900000002", name="Sr. Ramírez", supplier=lima)
    mexico = Supplier.objects.create(name="Hilados del Bajío", kind="material", city="México")
    return {"norte": norte, "lima": lima, "mexico": mexico}


@pytest.fixture
def agent_user(config, manager):
    config.agent_user = manager
    config.save()
    return manager


@pytest.fixture
def evolution(monkeypatch):
    """Fake `messaging.evolution` with one chat per JID."""
    module = types.ModuleType("messaging.evolution")
    module.chats = {}

    class EvolutionError(Exception):
        pass

    def find_messages(jid, since, *, limit=300):
        return module.chats.get(jid, [])

    module.EvolutionError = EvolutionError
    module.find_messages = find_messages
    monkeypatch.setitem(sys.modules, "messaging.evolution", module)
    return module


def raw(message_id, from_me, text, minutes, push_name=""):
    stamp = int((timezone.now() - timedelta(minutes=minutes)).timestamp())
    return {
        "key": {"id": message_id, "fromMe": from_me, "remoteJid": "51900000001@s.whatsapp.net"},
        "message": {"conversation": text},
        "messageTimestamp": stamp,
        "pushName": push_name,
    }


def test_state_lists_suppliers_with_what_to_fix(manager_client, suppliers):
    response = manager_client.get(URL)
    assert response.status_code == 200
    statuses = {s["name"]: s["status"] for s in response.json()["suppliers"]}
    assert statuses == {
        "Confecciones del Norte": "pending",
        "Textiles Lima Norte S.A.C.": "not_allowed",
        "Hilados del Bajío": "no_phone",
    }
    assert response.json()["status"] == "not_started"


def test_only_the_manager_can_use_it(sales_client, suppliers):
    assert sales_client.get(URL).status_code == 403


def test_extract_requires_since(manager_client, suppliers):
    response = manager_client.post(URL + "extract/", {}, format="json")
    assert response.status_code == 400


def test_extract_returns_409_while_extracting(manager_client, suppliers):
    body = {"since": "2026-10-10"}
    assert manager_client.post(URL + "extract/", body, format="json").status_code == 202
    assert manager_client.post(URL + "extract/", body, format="json").status_code == 409
    assert manager_client.put(URL, {"style_md": "x", "notes": []}, format="json").status_code == 409


def test_extract_without_active_numbers_is_rejected(manager_client, suppliers):
    body = {"since": "2026-10-10", "supplier_ids": [suppliers["lima"].id]}
    response = manager_client.post(URL + "extract/", body, format="json")
    assert response.status_code == 400


def test_stale_heartbeat_reports_error(manager_client, suppliers):
    row = OnboardingStyle.load()
    row.status = OnboardingStyle.Status.EXTRACTING
    row.heartbeat_at = timezone.now() - timedelta(minutes=6)
    row.save()
    body = manager_client.get(URL).json()
    assert body["status"] == "error"
    assert "interrumpió" in body["error"]
    # And it can be started again.
    response = manager_client.post(URL + "extract/", {"since": "2026-10-10"}, format="json")
    assert response.status_code == 202


def test_run_extraction_from_whatsapp_builds_the_draft(
    manager, agent_user, suppliers, fake_sdk, evolution
):
    norte = suppliers["norte"]
    conversation = Conversation.objects.create(
        channel="whatsapp", allowed_number=norte.numbers.first()
    )
    Message.objects.create(
        conversation=conversation,
        author=Message.Author.AGENT,
        text="mensaje del bot",
        external_id="BOT1",
        status=Message.Status.SENT,
        sent_at=timezone.now(),
    )
    evolution.chats["51900000001@s.whatsapp.net"] = [
        raw("A1", True, "buenos días, ¿cómo va el pedido?", 60, push_name="Martín G"),
        raw("A2", False, "ya van 400, Sr. Martín", 50, push_name="Vale"),
        raw("BOT1", True, "mensaje del bot", 40),
    ]
    sdk = fake_sdk(
        replies={"Analizas": ANALYSIS, "Escribes el estilo": {"style_md": load_template()}}
    )

    onboarding.start_extraction(since=date.today() - timedelta(days=1), actor=manager)
    onboarding.run_extraction("extract")

    row = OnboardingStyle.load()
    assert row.status == OnboardingStyle.Status.DRAFT
    assert row.draft_style_md.startswith("# Estilo del Gerente")
    assert row.draft_notes[str(norte.id)].startswith("Trato:")
    assert row.progress[str(norte.id)]["status"] == "done"
    # Messages used for the style: the agent's own message is not counted.
    assert row.progress[str(norte.id)]["messages_read"] == 2
    analysis_prompt = sdk.calls[0]["prompt"]
    assert "mensaje del bot" not in analysis_prompt  # the agent never teaches style
    assert "Martín" not in analysis_prompt and "Vale" not in analysis_prompt


def test_disconnected_account_ends_in_a_clear_error(manager, suppliers, fake_sdk, evolution):
    fake_sdk(connected=False)
    onboarding.start_extraction(since=date(2026, 10, 10), actor=manager)
    onboarding.run_extraction("extract")
    row = OnboardingStyle.load()
    assert row.status == OnboardingStyle.Status.ERROR
    assert row.error == "Conecta tu cuenta de Claude en Configuración."


def test_import_txt_adds_the_chat_to_the_draft(manager_client, agent_user, suppliers, fake_sdk):
    lima = suppliers["lima"]
    update = {
        "style_md": load_template(),
        "notes": [
            {
                "supplier": "Proveedor 1",
                "notes": {"trato": "usted", "tono": "formal", "insistencia": "baja"},
            }
        ],
        "changelog": ["con Proveedor 1 trata de usted"],
    }
    sdk = fake_sdk(replies={"Actualizas": update})
    upload = SimpleUploadedFile(
        "lima.txt", (FIXTURES / "textiles-lima-norte.txt").read_bytes(), content_type="text/plain"
    )
    response = manager_client.post(
        URL + "import-txt/",
        {
            "file": upload,
            "manager_author": "Gerente",
            "since": "2026-01-01",
            "supplier_id": lima.id,
        },
        format="multipart",
    )
    assert response.status_code == 202
    assert OnboardingStyle.load().temp_transcript is not None

    onboarding.run_extraction("import")

    row = OnboardingStyle.load()
    assert row.status == OnboardingStyle.Status.DRAFT
    assert row.temp_transcript is None
    assert row.draft_notes[str(lima.id)].startswith("Trato: usted")
    assert "Ramírez" not in sdk.calls[0]["prompt"]


def test_import_txt_with_an_unknown_author_is_rejected(manager_client, suppliers):
    upload = SimpleUploadedFile("lima.txt", (FIXTURES / "textiles-lima-norte.txt").read_bytes())
    response = manager_client.post(
        URL + "import-txt/",
        {"file": upload, "manager_author": "Nadie", "since": "2026-01-01"},
        format="multipart",
    )
    assert response.status_code == 400


def test_template_then_approve_sets_the_style(manager_client, agent_user, suppliers):
    assert manager_client.post(URL + "template/").json()["style_md"] == load_template()
    response = manager_client.post(URL + "approve/")
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    agent_user.refresh_from_db()
    assert agent_user.style_md == load_template()
    assert StyleVersion.objects.get().source == StyleVersion.Source.TEMPLATE
    # Idempotent: approving again does not create another version.
    assert manager_client.post(URL + "approve/").status_code == 200
    assert StyleVersion.objects.count() == 1


def test_approve_creates_style_version_and_copies_notes(manager_client, agent_user, suppliers):
    norte = suppliers["norte"]
    draft = {
        "style_md": load_template(),
        "notes": [{"supplier_id": norte.id, "notes": "Trato: usted\nTono: cordial"}],
    }
    assert manager_client.put(URL, draft, format="json").status_code == 200
    assert manager_client.post(URL + "approve/").status_code == 200
    norte.refresh_from_db()
    assert norte.notes == "Trato: usted\nTono: cordial"
    version = StyleVersion.objects.get()
    assert version.notes_snapshot[str(norte.id)] == "Trato: usted\nTono: cordial"


def test_approve_rejects_an_invalid_draft(manager_client, agent_user, suppliers):
    draft = {"style_md": load_template() + "\ncon Confecciones del Norte a S/ 12.50\n", "notes": []}
    manager_client.put(URL, draft, format="json")
    response = manager_client.post(URL + "approve/")
    assert response.status_code == 400
    assert any("Confecciones del Norte" in e for e in response.json()["errors"])
    assert Config.load().agent_user.style_md == ""
