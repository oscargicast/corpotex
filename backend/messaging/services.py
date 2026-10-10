"""Turn queue and messaging services (ADR 0010, 0018). The full queue lands in B3.5; B1 ships
what the worker needs at startup."""

import logging

from django.db import transaction
from django.utils import timezone

from .models import Turn

logger = logging.getLogger(__name__)


def recover_stuck_turns() -> int:
    """Turns left `running` by a dead worker go back to the queue. The retry does not count as
    an attempt: it was not the turn's fault."""
    with transaction.atomic():
        stuck = list(Turn.objects.select_for_update().filter(status=Turn.Status.RUNNING))
        for turn in stuck:
            turn.status = Turn.Status.ERROR
            turn.error = "worker restarted"
            turn.save(update_fields=["status", "error", "updated_at"])
            if not Turn.objects.filter(
                conversation=turn.conversation, status=Turn.Status.PENDING
            ).exists():
                Turn.objects.create(
                    conversation=turn.conversation,
                    reason=turn.reason,
                    attempts=turn.attempts,
                    available_at=timezone.now(),
                )
    if stuck:
        logger.warning("recover_stuck_turns: requeued %d turn(s)", len(stuck))
    return len(stuck)
