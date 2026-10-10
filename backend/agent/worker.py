"""One agent turn: build the prompt, run the isolated SDK, return the result (ADR 0010).

Django queries (prompt and tools) run here, outside the event loop; only the SDK
run is async. One CLI process per turn, resumed by session id: the spike measured
p50 7.7 s against 10.4 s with a long-lived client.
"""

import asyncio
import logging

from claude_agent_sdk import create_sdk_mcp_server

from agent import sdk

log = logging.getLogger(__name__)

SERVER = "corpotex"  # tools reach the model as mcp__corpotex__<name>
TURN_EFFORT = "medium"


def run_batch(batch) -> sdk.TurnResult:
    conversation = batch.turn.conversation
    try:
        return _run(batch, conversation, resume=conversation.agent_session or None)
    except sdk.SessionNotFound:
        log.warning(
            "conversation %s: session %s is gone, reopening with history",
            conversation.pk,
            conversation.agent_session,
        )
        return _run(batch, conversation, resume=None, with_history=True)


def _run(batch, conversation, *, resume: str | None, with_history: bool = False) -> sdk.TurnResult:
    if conversation.channel == "dashboard":
        from agent.persona import build_assistant_prompt as build_prompt
        from agent.tools import assistant_tools as tools_for
    else:
        from agent.persona import build_prompt
        from agent.tools import whatsapp_tools as tools_for

    system, blocks = build_prompt(conversation, batch, with_history=with_history)
    tools = tools_for(conversation, batch)
    options = sdk.isolated_options(
        subdir="turns",
        system_prompt=system,
        mcp_servers={SERVER: create_sdk_mcp_server(SERVER, tools=tools)} if tools else None,
        allowed_tools=[f"mcp__{SERVER}__{t.name}" for t in tools],
        resume=resume,
        effort=TURN_EFFORT,
    )
    result = asyncio.run(sdk.run(blocks, options))
    log.info(
        "turn %s conversation %s session %s error=%s note=%r",
        batch.turn.pk,
        conversation.pk,
        result.session_id,
        result.error,
        result.text[:300],
    )
    return result
