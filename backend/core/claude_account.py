"""The installation's Claude account, Django side (ADR 0022, planning B4.3).

`core.claude_auth` holds the framework-free OAuth and API key logic over a config
directory. This module binds it to `settings.CLAUDE_CONFIG_DIR`, records the
connection state in `Config` and pauses or resumes the turn queue: while
`Config.claude_last_error` has a value, `claim_next_turn` hands out nothing
(planning B3.5), so every agent stops until the Gerente reconnects.
"""

from __future__ import annotations

import logging
from pathlib import Path

from celery import current_app
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from . import claude_auth, clock
from .models import Config

logger = logging.getLogger(__name__)

DISCONNECTED_BY_MANAGER = "Cuenta de Claude desconectada desde el dashboard."
ALERT_TEXT = "Claude desconectado: el agente está en pausa hasta reconectar la cuenta."
DEFAULT_ERROR = "Claude rechazó la autenticación."


def config_dir() -> Path:
    return Path(settings.CLAUDE_CONFIG_DIR)


def status() -> dict:
    """What `/settings/claude` shows: the credential state plus the queue state."""
    config = Config.load()
    data = claude_auth.status(config_dir())
    data.update(
        connected_at=config.claude_connected_at,
        last_error=config.claude_last_error or None,
        last_error_at=config.claude_last_error_at,
    )
    return data


def start() -> dict:
    return claude_auth.start()


def connect_with_code(code_input: str) -> dict:
    claude_auth.exchange(code_input, config_dir())
    mark_claude_connected()
    return status()


def connect_with_api_key(api_key: str) -> dict:
    claude_auth.set_api_key(config_dir(), api_key)
    mark_claude_connected()
    return status()


def disconnect() -> dict:
    """Remove the credential and pause the queue. Raises `not_connected` when there was none."""
    claude_auth.disconnect(config_dir())
    config = Config.load()
    config.claude_connected_at = None
    config.save(update_fields=["claude_connected_at", "updated_at"])
    mark_claude_disconnected(DISCONNECTED_BY_MANAGER)
    return status()


# -- Queue pause / resume (called by the worker, A3.3) ------------------------


def mark_claude_disconnected(error_text: str, *, batch=None) -> None:
    """Record the auth failure, open the `claude_disconnected` alert and pause the queue.

    With `batch` (the `TurnBatch` the worker was running) its turn goes back to the
    queue without counting an attempt: the failure was not the turn's fault.
    """
    from manager.models import Alert

    error_text = (error_text or "").strip()[:500] or DEFAULT_ERROR
    with transaction.atomic():
        config = Config.load()
        config.claude_last_error = error_text
        config.claude_last_error_at = timezone.now()
        config.save(update_fields=["claude_last_error", "claude_last_error_at", "updated_at"])
        _open_alert(Alert, detected_at=clock.now(config))
        if batch is not None:
            _requeue(batch.turn, error_text)
    logger.warning("Claude disconnected, queue paused: %s", error_text)


def mark_claude_connected() -> None:
    """Clear the error, resolve the alert and re-dispatch every conversation with a pending turn."""
    from manager.models import Alert
    from messaging.models import Turn

    now = timezone.now()
    with transaction.atomic():
        config = Config.load()
        config.claude_connected_at = now
        config.claude_last_error = ""
        config.claude_last_error_at = None
        config.save(
            update_fields=[
                "claude_connected_at",
                "claude_last_error",
                "claude_last_error_at",
                "updated_at",
            ]
        )
        Alert.objects.filter(
            kind=Alert.Kind.CLAUDE_DISCONNECTED,
            status__in=[Alert.Status.OPEN, Alert.Status.ACKNOWLEDGED],
        ).update(status=Alert.Status.RESOLVED, resolved_at=now)
        conversation_ids = list(
            Turn.objects.filter(status=Turn.Status.PENDING)
            .order_by()
            .values_list("conversation_id", flat=True)
            .distinct()
        )
        transaction.on_commit(lambda: _dispatch_pending(conversation_ids))


def _open_alert(Alert, *, detected_at) -> None:
    """One open `claude_disconnected` alert at a time (`uniq_open_alert_per_target`)."""
    try:
        with transaction.atomic():
            Alert.objects.get_or_create(
                kind=Alert.Kind.CLAUDE_DISCONNECTED,
                status=Alert.Status.OPEN,
                order=None,
                purchase_order=None,
                decision=None,
                defaults={
                    "severity": Alert.Severity.CRITICAL,
                    "text": ALERT_TEXT,
                    "detected_at": detected_at,
                },
            )
    except IntegrityError:
        pass  # another worker opened it in between: same outcome


def _requeue(turn, error_text: str) -> None:
    """Back to `pending` without an attempt. If a newer `pending` already exists for the
    conversation (a message arrived while this turn ran), this one ends as `error` and the
    pending one picks the whole batch up: batches are built from fresh state (ADR 0010)."""
    from messaging.models import Turn

    turn = Turn.objects.select_for_update().get(pk=turn.pk)
    has_other_pending = (
        Turn.objects.filter(conversation_id=turn.conversation_id, status=Turn.Status.PENDING)
        .exclude(pk=turn.pk)
        .exists()
    )
    turn.error = error_text
    if has_other_pending:
        turn.status = Turn.Status.ERROR
        turn.save(update_fields=["status", "error", "updated_at"])
        return
    turn.status = Turn.Status.PENDING
    turn.available_at = timezone.now()
    turn.save(update_fields=["status", "error", "available_at", "updated_at"])


def _dispatch_pending(conversation_ids: list[int]) -> None:
    for conversation_id in conversation_ids:
        try:
            current_app.send_task("agent.tasks.run_turn", args=[conversation_id], queue="turns")
        except Exception:  # the tick re-dispatches pending turns anyway (B5.2)
            logger.exception("could not re-dispatch turn for conversation %s", conversation_id)
