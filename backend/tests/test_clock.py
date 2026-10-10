from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied

from core import clock
from core.models import Config


@pytest.mark.django_db
def test_now_runs_at_factor(config):
    config.clock_factor = Decimal("60")
    config.save()
    before = clock.now()
    import time

    time.sleep(0.2)
    after = clock.now()
    assert timedelta(seconds=10) < after - before < timedelta(seconds=60)


@pytest.mark.django_db
def test_advance_hours_moves_now_without_jump(manager, config):
    before = clock.now()
    clock.set_clock(advance_hours=24, actor=manager)
    after = clock.now()
    assert timedelta(hours=23, minutes=59) < after - before < timedelta(hours=24, minutes=1)


@pytest.mark.django_db
def test_pause_freezes_and_resume_rebases(manager, config):
    clock.set_clock(paused=True, actor=manager)
    frozen = clock.now()
    assert clock.now() == frozen
    clock.set_clock(paused=False, factor=1, actor=manager)
    assert clock.now() - frozen < timedelta(seconds=5)
    assert Config.load().clock_paused is False


@pytest.mark.django_db
def test_set_clock_requires_manager(sales, config):
    with pytest.raises(PermissionDenied):
        clock.set_clock(paused=True, actor=sales)


@pytest.mark.django_db
def test_clock_api(manager_client, sales_client):
    assert sales_client.get("/api/clock/").status_code == 200
    assert sales_client.patch("/api/clock/", {"advance_hours": 24}).status_code == 403
    response = manager_client.patch("/api/clock/", {"advance_hours": 24})
    assert response.status_code == 200
    assert set(response.json()) == {"now", "factor", "paused"}
