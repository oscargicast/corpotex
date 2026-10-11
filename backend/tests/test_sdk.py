import asyncio
import json
import os

import pytest
from claude_agent_sdk import AssistantMessage, ResultError, ResultMessage, TextBlock

from agent import sdk


@pytest.fixture(autouse=True)
def config_dir(tmp_path, monkeypatch):
    path = tmp_path / "config"
    path.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(path))
    return path


def options(**kwargs):
    return sdk.isolated_options(subdir="turns", system_prompt="sistema", **kwargs)


def result(**kwargs):
    fields = {
        "subtype": "success",
        "duration_ms": 1,
        "duration_api_ms": 1,
        "is_error": False,
        "num_turns": 1,
        "session_id": "s1",
        "result": "nota",
    }
    return ResultMessage(**{**fields, **kwargs})


def fake_query(*messages, error=None):
    async def query(*, prompt, options):
        for message in messages:
            yield message
        if error:
            raise error

    return query


def test_isolated_options_has_no_builtin_tools_and_empty_setting_sources(config_dir):
    opts = options(allowed_tools=["mcp__corpotex__send_message"])
    assert opts.tools == []
    assert opts.setting_sources == []
    assert opts.permission_mode == "dontAsk"
    assert opts.allowed_tools == ["mcp__corpotex__send_message"]
    assert opts.cwd == str(config_dir.parent / "turns")
    assert opts.env == {
        "CLAUDE_CONFIG_DIR": str(config_dir),
        "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
    }


def test_options_never_contain_oauth_token(monkeypatch):
    for var in sdk.FOREIGN_CREDENTIALS:
        monkeypatch.setenv(var, "secret")
    opts = options()
    assert "secret" not in json.dumps(opts.env)
    assert not any(var in os.environ for var in sdk.FOREIGN_CREDENTIALS)


def test_search_only_grants_websearch():
    opts = sdk.isolated_options(subdir="search", system_prompt="s", builtin_tools=("WebSearch",))
    assert opts.tools == ["WebSearch"]
    assert opts.allowed_tools == ["WebSearch"]
    assert opts.mcp_servers == {}


def test_api_key_mode_passes_helper_inline_and_oauth_wins(config_dir):
    assert not sdk.is_connected()
    (config_dir / sdk.API_KEY_FILE).write_text("sk-ant-api03-test")
    assert sdk.is_connected()
    assert json.loads(options().settings)["apiKeyHelper"].startswith("cat ")
    (config_dir / ".credentials.json").write_text("{}")
    assert options().settings is None


def test_run_returns_session_and_final_text(monkeypatch):
    monkeypatch.setattr(sdk, "query", fake_query(result()))
    assert asyncio.run(sdk.run("hola", options())) == sdk.TurnResult("s1", "nota")


def test_content_blocks_go_as_one_user_message(monkeypatch):
    seen = []

    async def query(*, prompt, options):
        seen.extend([m async for m in prompt])
        yield result()

    monkeypatch.setattr(sdk, "query", query)
    blocks = [
        {"type": "text", "text": "foto del mensaje de las 15:57"},
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AA"}},
    ]
    asyncio.run(sdk.run(blocks, options()))
    assert [m["message"]["content"] for m in seen] == [blocks]


def test_synthetic_auth_error_raises_claude_not_connected(monkeypatch):
    synthetic = AssistantMessage(
        content=[TextBlock("Not logged in · Please run /login")],
        model="<synthetic>",
        error="authentication_failed",
    )
    monkeypatch.setattr(
        sdk,
        "query",
        fake_query(synthetic, result(is_error=True), error=ResultError("exit 1")),
    )
    with pytest.raises(sdk.ClaudeNotConnected, match="Not logged in"):
        asyncio.run(sdk.run("hola", options()))


def test_auth_error_as_plain_text_also_raises(monkeypatch):
    text = "Failed to authenticate: OAuth session expired and could not be refreshed"
    monkeypatch.setattr(sdk, "query", fake_query(result(is_error=True, result=text)))
    with pytest.raises(sdk.ClaudeNotConnected):
        asyncio.run(sdk.run("hola", options()))


def test_missing_session_raises_session_not_found(monkeypatch):
    error = ResultError(
        "Claude Code returned an error result: No conversation found with session ID: x"
    )
    monkeypatch.setattr(sdk, "query", fake_query(error=error))
    with pytest.raises(sdk.SessionNotFound):
        asyncio.run(sdk.run("hola", options(resume="x")))


def test_model_error_keeps_session_id_for_the_retry(monkeypatch):
    failed = result(is_error=True, subtype="error_max_turns", result=None)
    monkeypatch.setattr(sdk, "query", fake_query(failed, error=ResultError("exit 1")))
    assert asyncio.run(sdk.run("hola", options())) == sdk.TurnResult(
        "s1", "", error="error_max_turns"
    )


def test_complete_with_schema_returns_the_dict(monkeypatch):
    monkeypatch.setattr(sdk, "query", fake_query(result(structured_output={"saludo": "Buenas"})))
    out = asyncio.run(
        sdk.complete("p", system_prompt="s", model="sonnet", schema={"type": "object"})
    )
    assert out == {"saludo": "Buenas"}


def test_complete_without_structured_output_fails_loudly(monkeypatch):
    monkeypatch.setattr(sdk, "query", fake_query(result()))
    with pytest.raises(sdk.ClaudeSDKError):
        asyncio.run(sdk.complete("p", system_prompt="s", model="sonnet", schema={"type": "object"}))


def test_hung_cli_raises_turn_timeout_quickly(monkeypatch):
    async def hung_query(*, prompt, options):
        await asyncio.sleep(30)
        yield result()

    monkeypatch.setattr(sdk, "query", hung_query)
    with pytest.raises(sdk.TurnTimeout):
        asyncio.run(sdk.run("hola", options(), timeout=0.05))


def test_model_comes_from_django_settings(settings):
    settings.AGENT_MODEL = "opus"
    assert options().model == "opus"
    settings.AGENT_MODEL = "sonnet"
    assert options().model == "sonnet"
