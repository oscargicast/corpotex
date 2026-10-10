"""Style extraction and the daily refresh (ADR 0011, 0019). Owned by `personalidad`; these
stubs register the task names so routing and beat work before the real code lands."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="core.tasks.run_style_extraction")
def run_style_extraction() -> None:
    logger.info("run_style_extraction: pending implementation (personalidad, B4.6)")


@shared_task(name="core.tasks.refresh_style")
def refresh_style(user_id: int | None = None) -> None:
    logger.info("refresh_style: pending implementation (personalidad, B5.3)")
