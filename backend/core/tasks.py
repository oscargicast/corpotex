"""Celery tasks of `core`. The style tasks live in `tasks_style.py` (owned by `personalidad`)
and are re-exported here so autodiscovery finds them under `core.tasks.*`."""

from .tasks_style import *  # noqa: F401,F403
