"""The simulated clock (accelerated for the demo). Every business date is written with `now()`."""

from datetime import datetime, timedelta
from decimal import Decimal

from django.utils import timezone

from .models import Config
from .permissions import require_role


def now(config: Config | None = None) -> datetime:
    config = config or Config.load()
    if config.clock_paused:
        return config.clock_sim_start
    elapsed = timezone.now() - config.clock_real_start
    return config.clock_sim_start + elapsed * float(config.clock_factor)


def today(config: Config | None = None):
    return timezone.localtime(now(config)).date()


def _rebase(config: Config) -> None:
    """Pin the simulated time to the real one so a factor or pause change does not jump."""
    config.clock_sim_start = now(config)
    config.clock_real_start = timezone.now()


def set_clock(
    *,
    factor: Decimal | float | None = None,
    paused: bool | None = None,
    advance_hours: float | None = None,
    actor,
) -> Config:
    require_role(actor, "manager")
    config = Config.load()
    _rebase(config)
    if factor is not None:
        config.clock_factor = Decimal(str(factor))
    if paused is not None:
        config.clock_paused = paused
    if advance_hours:
        config.clock_sim_start += timedelta(hours=float(advance_hours))
    config.save()
    return config
