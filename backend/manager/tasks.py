"""Beat task: every ~10 real seconds (ADR 0018)."""

import logging
from datetime import timedelta

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="manager.tasks.tick")
def tick() -> dict:
    """Queues the day's follow-ups (ADR 0027), sweeps the turn queue, runs the monitor and
    repeats stale alerts."""
    from messaging.services import sweep_turns

    from . import follow_up, services

    try:
        follow_ups = follow_up.enqueue_due_follow_ups()
        follow_up.refresh_next_follow_up()
    except Exception:  # The tick must keep sweeping and monitoring whatever the plan hits.
        logger.exception("tick: follow-up planning failed")
        follow_ups = 0
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
