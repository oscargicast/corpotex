"""A2.3: one full turn through the real queue, prompt, tools and services. Only the model
is faked: it calls the real tools the worker built, like Claude would."""

import pytest
from django.utils import timezone

from agent import sdk, tasks, worker
from messaging.models import AllowedNumber, Conversation, Message, Turn
from messaging.services import enqueue_turn
from tests.scenario import build


@pytest.fixture
def simulator_turn(transactional_db, tmp_path, monkeypatch):
    """The scenario's workshop writes through the simulator; its turn is due now.

    Tools reach the ORM from sync_to_async's thread, so the data must be committed:
    hence transactional_db."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "config"))
    scenario = build()
    number = AllowedNumber.objects.get(phone="sim-confecciones-norte")
    conversation = Conversation.objects.create(channel="simulator", allowed_number=number)
    incoming = Message.objects.create(
        conversation=conversation,
        author="supplier",
        text="Buenas, ¿cómo va lo del PT-0001? Ya vamos 600.",
        status="received",
        sent_at=timezone.now(),
    )
    enqueue_turn(conversation, "message")
    Turn.objects.filter(conversation=conversation).update(available_at=timezone.now())
    return scenario, conversation, incoming


def fake_model(monkeypatch, script):
    """sdk.run stand-in: records the prompt and runs `script(tools)` against the real tools."""
    seen = {}

    def capture(name, tools):
        seen["tools"] = {t.name: t for t in tools}
        return {"type": "sdk", "name": name}

    async def run(blocks, options):
        seen["system"], seen["blocks"], seen["options"] = options.system_prompt, blocks, options
        await script(seen["tools"])
        return sdk.TurnResult("sess-1", "Nota: el taller reporta 600.")

    monkeypatch.setattr(worker, "create_sdk_mcp_server", capture)
    monkeypatch.setattr(sdk, "run", run)
    return seen


def test_simulator_message_runs_a_full_turn(simulator_turn, monkeypatch):
    scenario, conversation, incoming = simulator_turn

    async def script(tools):
        await tools["record_progress"].handler({"code": "PT-0001", "units_done": 600})
        await tools["send_message"].handler({"text": "Ya, anotado: 600 de 1000. Gracias."})

    seen = fake_model(monkeypatch, script)
    tasks.run_turn(conversation.id)

    # The prompt is persona's, built from the fresh turn state.
    assert seen["system"].startswith("<reglas>") and "<estilo>" in seen["system"]
    assert "PT-0001" in seen["blocks"][0]["text"] and "Ya vamos 600" in seen["blocks"][0]["text"]
    assert seen["options"].tools == [] and seen["options"].setting_sources == []

    # The tools hit the real services.
    reply = conversation.messages.get(author="agent")
    assert reply.text == "Ya, anotado: 600 de 1000. Gracias." and reply.turn_id is not None
    assert scenario["purchase_order"].progress_reports.order_by("-id").first().units_done == 600

    # finish_turn closed the batch and kept the session.
    turn = Turn.objects.get(pk=reply.turn_id)
    conversation.refresh_from_db()
    incoming.refresh_from_db()
    assert turn.status == "done" and conversation.agent_session == "sess-1"
    assert incoming.status == "processed"


def test_boss_rule_refusal_reaches_the_model_and_the_turn_still_closes(simulator_turn, monkeypatch):
    _, conversation, _ = simulator_turn
    answers = []

    async def script(tools):
        out = await tools["confirm_purchase_order"].handler(
            {"code": "PT-0001", "unit_price": 9.0, "committed_on": "2026-10-14", "terms": "50/50"}
        )
        answers.append(out)

    fake_model(monkeypatch, script)
    tasks.run_turn(conversation.id)
    assert answers[0]["is_error"] and "escalate_to_manager" in answers[0]["content"][0]["text"]
    assert Turn.objects.get(conversation=conversation).status == "done"


def test_dashboard_question_gets_a_reply_built_from_role_reads(
    transactional_db, manager, tmp_path, monkeypatch
):
    from messaging.services import dashboard_conversation

    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "config"))
    build()
    conversation = dashboard_conversation(manager)
    Message.objects.create(
        conversation=conversation,
        author="user",
        text="¿Qué tengo pendiente?",
        status="received",
        sent_at=timezone.now(),
    )
    enqueue_turn(conversation, "message")
    reads = []

    async def script(tools):
        reads.append(await tools["list_pending"].handler({}))

    seen = fake_model(monkeypatch, script)
    tasks.run_turn(conversation.id)

    assert "¿Qué tengo pendiente?" in seen["blocks"][0]["text"]
    assert (
        "Pide subir el precio a 7.00" in reads[0]["content"][0]["text"]
    )  # the manager sees decisions
    reply = conversation.messages.get(author="agent")
    assert reply.text == "Nota: el taller reporta 600." and reply.action is None


def test_list_alerts_only_brings_the_users_alerts(transactional_db, sales):
    from agent.assistant_tools import api_get

    build()  # one open order_in_danger alert: sales gets it (ADR 0020)
    status, alerts = api_get(sales, "/api/alerts/", {"mine": "1"})
    assert status == 200 and [a["kind"] for a in alerts] == ["order_in_danger"]


def test_list_materials_reads_the_real_inventory(transactional_db, production, sales):
    from agent.assistant_tools import api_get

    build()
    status, rows = api_get(production, "/api/materials/", {"q": "algod"})
    assert status == 200 and [r["sku"] for r in rows] == ["TEL-ALG-20-1"]
    assert api_get(sales, "/api/materials/")[0] == 403
