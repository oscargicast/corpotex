"""Beat task: every ~10 real seconds (ADR 0018)."""

import logging
from datetime import timedelta

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="manager.tasks.tick")
def tick() -> dict:
    """Queues follow-ups, sweeps the turn queue, runs the monitor and repeats stale alerts."""
    from core import clock
    from messaging.models import Turn
    from messaging.services import conversation_for_supplier, enqueue_turn, sweep_turns
    from operations.models import PurchaseOrder

    from . import services

    follow_ups = 0
    now = clock.now()
    due = PurchaseOrder.objects.filter(status__in=PurchaseOrder.OPEN_STATUSES, next_follow_up_at__lte=now).select_related(
        "supplier", "conversation__allowed_number"
    )
    for po in due:
        conversation = po.conversation
        if conversation is None or conversation.allowed_number is None or not conversation.allowed_number.active:
            conversation = conversation_for_supplier(po.supplier)
            if conversation is None:
                continue
            po.conversation = conversation
            po.save(update_fields=["conversation", "updated_at"])
        if conversation.turns.filter(status__in=(Turn.Status.PENDING, Turn.Status.RUNNING)).exists():
            continue  # That turn will carry the follow-up in its batch.
        enqueue_turn(conversation, "follow_up")
        follow_ups += 1

    swept = sweep_turns()
    monitor = services.run_monitor()
    repeated = services.repeat_open_alerts_to_manager()
    _check_claude_credentials()
    return {"follow_ups": follow_ups, "swept": swept, "repeated": repeated, **monitor}


def _check_claude_credentials() -> None:
    """If the credential file is newer than the last error, Claude is back (ADR 0022)."""
    import os

    from django.conf import settings
    from django.utils import timezone

    from core.models import Config

    config = Config.load()
    if not config.claude_last_error or not config.claude_last_error_at:
        return
    path = os.path.join(settings.CLAUDE_CONFIG_DIR, ".credentials.json")
    try:
        mtime = timezone.datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.get_current_timezone())
    except OSError:
        return
    if mtime > config.claude_last_error_at:
        try:
            from core.claude_account import mark_claude_connected
        except ImportError:  # The orquestador's module is not merged yet.
            config.claude_last_error = ""
            config.claude_last_error_at = None
            config.save(update_fields=["claude_last_error", "claude_last_error_at", "updated_at"])
            return
        mark_claude_connected()
