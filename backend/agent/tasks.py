"""Celery entry point of agent turns (ADR 0018). The Turn table is the queue."""

import logging

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

from agent import sdk, worker

log = logging.getLogger(__name__)


@shared_task(
    name="agent.tasks.run_turn",
    queue="turns",
    acks_late=True,
    soft_time_limit=90,  # backstop: sdk.run already gives up at 80 s and kills the CLI
    time_limit=120,  # hard kill; the turn then stays `running` until the tick sweeps it
)
def run_turn(conversation_id: int) -> None:
    """Claim this conversation's turn and run it. A duplicate or early task is a no-op."""
    from core.claude_account import mark_claude_disconnected
    from messaging.services import claim_next_turn, finish_turn

    batch = claim_next_turn(conversation_id)
    if batch is None:
        return
    try:
        result = worker.run_batch(batch)
    except sdk.ClaudeNotConnected as e:
        # Not the turn's fault: back to pending without an attempt, queue paused (ADR 0022).
        mark_claude_disconnected(str(e), batch=batch)
        return
    except (sdk.TurnTimeout, SoftTimeLimitExceeded):
        finish_turn(batch, None, error="timeout")
        return
    except Exception as e:
        log.exception("turn %s failed", batch.turn.pk)
        finish_turn(batch, None, error=f"{type(e).__name__}: {e}"[:500])
        return
    finish_turn(batch, result.session_id, error=result.error)
