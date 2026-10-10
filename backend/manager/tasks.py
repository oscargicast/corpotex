"""Beat task. The real tick (follow-ups, sweep, monitor) lands in B5.2."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="manager.tasks.tick")
def tick() -> None:
    logger.debug("tick: pending implementation (B5.2)")
