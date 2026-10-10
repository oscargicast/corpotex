import os

from celery import Celery
from celery.signals import worker_ready

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("corpotex")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@worker_ready.connect
def requeue_turns_left_running(**_kwargs) -> None:
    """Turns that were `running` when the worker died go back to the queue (ADR 0010)."""
    from messaging.services import recover_stuck_turns

    recover_stuck_turns()
