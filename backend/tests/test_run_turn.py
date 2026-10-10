from types import SimpleNamespace

import pytest
from agent_fakes import install
from claude_agent_sdk import tool

from agent import sdk, tasks, worker


@pytest.fixture(autouse=True)
def config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "config"))


def make_batch(session="s0", channel="whatsapp"):
    conversation = SimpleNamespace(pk=7, channel=channel, agent_session=session)
    return SimpleNamespace(turn=SimpleNamespace(pk=3, conversation=conversation), message_ids=[1])


def fake_run(results, seen):
    """sdk.run stand-in: records the options, returns or raises the next result."""

    async def run(blocks, options):
        seen.append(options)
        outcome = results.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    return run


def test_run_turn_without_pending_turn_is_noop(monkeypatch):
    calls = install(monkeypatch)
    monkeypatch.setattr(worker, "run_batch", lambda batch: pytest.fail("ran the model"))
    tasks.run_turn(7)
    assert calls.finished == []


def test_run_turn_passes_session_id_to_finish_turn(monkeypatch):
    batch = make_batch()
    calls = install(monkeypatch, claim_next_turn=lambda conversation_id: batch)
    monkeypatch.setattr(worker, "run_batch", lambda b: sdk.TurnResult("s1", "nota"))
    tasks.run_turn(7)
    assert calls.finished == [(batch, "s1", None)]


def test_model_error_finishes_with_error_and_session(monkeypatch):
    batch = make_batch()
    calls = install(monkeypatch, claim_next_turn=lambda conversation_id: batch)
    failed = sdk.TurnResult("s1", "", error="error_max_turns")
    monkeypatch.setattr(worker, "run_batch", lambda b: failed)
    tasks.run_turn(7)
    assert calls.finished == [(batch, "s1", "error_max_turns")]


def test_auth_failure_does_not_count_attempt(monkeypatch):
    batch = make_batch()
    calls = install(monkeypatch, claim_next_turn=lambda conversation_id: batch)

    def not_connected(b):
        raise sdk.ClaudeNotConnected("Not logged in · Please run /login")

    monkeypatch.setattr(worker, "run_batch", not_connected)
    tasks.run_turn(7)
    assert calls.disconnected == [("Not logged in · Please run /login", batch)]
    assert calls.finished == []


def test_unexpected_exception_is_recorded_on_the_turn(monkeypatch):
    batch = make_batch()
    calls = install(monkeypatch, claim_next_turn=lambda conversation_id: batch)

    def boom(b):
        raise RuntimeError("boom")

    monkeypatch.setattr(worker, "run_batch", boom)
    tasks.run_turn(7)
    assert calls.finished == [(batch, None, "RuntimeError: boom")]


def test_lost_session_reopens_with_history(monkeypatch):
    calls = install(monkeypatch)
    seen = []
    results = [sdk.SessionNotFound("No conversation found"), sdk.TurnResult("s2", "")]
    monkeypatch.setattr(sdk, "run", fake_run(results, seen))
    out = worker.run_batch(make_batch(session="s0"))
    assert [o.resume for o in seen] == ["s0", None]
    assert calls.prompts == [("whatsapp", False), ("whatsapp", True)]
    assert out.session_id == "s2"


def test_tools_reach_the_model_namespaced_and_isolated(monkeypatch):
    @tool("send_message", "Envía un mensaje.", {"text": str})
    async def send_message(args):
        return {"content": [{"type": "text", "text": "ok"}]}

    install(monkeypatch, whatsapp_tools=lambda conversation, batch: [send_message])
    seen = []
    monkeypatch.setattr(sdk, "run", fake_run([sdk.TurnResult("s1", "")], seen))
    worker.run_batch(make_batch())
    (opts,) = seen
    assert opts.allowed_tools == ["mcp__corpotex__send_message"]
    assert list(opts.mcp_servers) == ["corpotex"]
    assert opts.tools == [] and opts.setting_sources == []
    assert opts.resume == "s0"


def test_dashboard_uses_the_assistant_prompt(monkeypatch):
    calls = install(monkeypatch)
    monkeypatch.setattr(sdk, "run", fake_run([sdk.TurnResult("s1", "")], []))
    worker.run_batch(make_batch(session="", channel="dashboard"))
    assert calls.prompts == [("dashboard", False)]
