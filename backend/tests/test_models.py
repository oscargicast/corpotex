import pytest

from core.models import Config, OnboardingStyle


@pytest.mark.django_db
def test_config_is_singleton():
    first = Config.load()
    second = Config.load()
    other = Config(clock_real_start=first.clock_real_start, clock_sim_start=first.clock_sim_start)
    other.save()
    assert first.pk == second.pk == other.pk == 1
    assert Config.objects.count() == 1


@pytest.mark.django_db
def test_onboarding_style_is_singleton():
    OnboardingStyle.load()
    OnboardingStyle.load()
    assert OnboardingStyle.objects.count() == 1


@pytest.mark.django_db
def test_user_role_comes_from_group(manager, sales, production):
    assert manager.role == "manager"
    assert sales.role == "sales"
    assert production.role == "production"
