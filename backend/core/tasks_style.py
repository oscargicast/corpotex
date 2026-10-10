"""Style extraction and the daily refresh (ADR 0011, 0019), on the `style` queue.

`style_lock()` keeps one style task at a time; a task that finds it taken retries in 30 s.
"""

from celery import shared_task

from .locks import style_lock


@shared_task(bind=True, name="core.tasks.run_style_extraction", max_retries=40)
def run_style_extraction(self, mode: str = "extract") -> None:
    from .onboarding import run_extraction

    with style_lock() as acquired:
        if not acquired:
            raise self.retry(countdown=30)
        run_extraction(mode)


@shared_task(bind=True, name="core.tasks.refresh_style", max_retries=40)
def refresh_style(self, user_id: int | None = None) -> None:
    from .style import refresh_style as refresh

    with style_lock() as acquired:
        if not acquired:
            raise self.retry(countdown=30)
        refresh(user_id)
