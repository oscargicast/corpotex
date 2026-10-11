"""One agent turn: build the prompt, run the isolated SDK, return the result (ADR 0010).

The prompt is built here, outside the event loop; tools reach the ORM through
sync_to_async. One CLI process per turn, resumed by session id: the spike measured
p50 7.7 s against 10.4 s with a long-lived client.
"""

import asyncio
import logging

from asgiref.sync import sync_to_async
from claude_agent_sdk import create_sdk_mcp_server

from agent import sdk

log = logging.getLogger(__name__)

SERVER = "corpotex"  # tools reach the model as mcp__corpotex__<name>
TURN_EFFORT = "medium"


def run_batch(batch) -> sdk.TurnResult:
    conversation = batch.turn.conversation
    session = conversation.agent_session or None
    try:
        # A new session (first turn, or after a reset) gets the stored history so the
        # model still sees the notice the user is answering.
        return _run(batch, conversation, resume=session, with_history=session is None)
    except sdk.SessionNotFound:
        log.warning(
            "conversation %s: session %s is gone, reopening with history",
            conversation.pk,
            conversation.agent_session,
        )
        return _run(batch, conversation, resume=None, with_history=True)


def _run(batch, conversation, *, resume: str | None, with_history: bool = False) -> sdk.TurnResult:
    dashboard = conversation.channel == "dashboard"
    if dashboard:
        from agent.assistant_tools import assistant_tools as tools_for
        from agent.assistant_tools import finish_dashboard_turn, is_alert_only
        from agent.persona import build_assistant_prompt as build_prompt
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
        effort="low" if dashboard and is_alert_only(batch) else TURN_EFFORT,
    )
    result = asyncio.run(_run_and_release(blocks, options))
    if dashboard:
        finish_dashboard_turn(conversation, batch, result)
    log.info(
        "turn %s conversation %s session %s error=%s note=%r",
        batch.turn.pk,
        conversation.pk,
        result.session_id,
        result.error,
        result.text[:300],
    )
    return result


async def _run_and_release(blocks, options) -> sdk.TurnResult:
    try:
        return await sdk.run(blocks, options)
    finally:
        # Tools use sync_to_async's single worker thread, whose DB connection Celery
        # never closes: drop it so a Postgres restart can't break the next turns.
        await sync_to_async(_close_db)()


def _close_db() -> None:
    from django.db import connections

    connections.close_all()
