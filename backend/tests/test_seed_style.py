import pytest
from django.core.management import call_command

from core.models import Config, OnboardingStyle, StyleVersion


@pytest.mark.django_db
def test_seed_demo_leaves_the_style_step_approved():
    call_command("seed_demo", verbosity=0)
    row = OnboardingStyle.load()
    manager = Config.load().agent_user
    assert row.status == OnboardingStyle.Status.APPROVED
    assert row.approved_at is not None
    assert row.draft_style_md == manager.style_md
    assert row.draft_source == StyleVersion.Source.MANUAL
    assert row.error == "" and row.step == ""


@pytest.mark.django_db
def test_seed_demo_never_overwrites_a_draft_in_progress():
    call_command("seed_demo", verbosity=0)
    row = OnboardingStyle.load()
    row.status, row.draft_style_md = OnboardingStyle.Status.DRAFT, "mi borrador"
    row.save()
    call_command("seed_demo", "--reset-style", verbosity=0)
    row = OnboardingStyle.load()
    assert row.status == OnboardingStyle.Status.DRAFT
    assert row.draft_style_md == "mi borrador"


@pytest.mark.django_db
def test_reseed_without_reset_style_still_marks_the_step_approved():
    call_command("seed_demo", verbosity=0)
    row = OnboardingStyle.load()
    row.status, row.approved_at, row.draft_style_md = OnboardingStyle.Status.NOT_STARTED, None, ""
    row.save()
    call_command("seed_demo", verbosity=0)  # keeps the style: the versions already exist
    row = OnboardingStyle.load()
    assert StyleVersion.objects.count() == 3
    assert row.status == OnboardingStyle.Status.APPROVED
    assert row.approved_at is not None
    assert row.draft_style_md == Config.load().agent_user.style_md


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["extracting", "error"])
def test_reseed_respects_a_running_or_failed_extraction(status):
    call_command("seed_demo", verbosity=0)
    row = OnboardingStyle.load()
    row.status, row.error = status, "algo"
    row.save()
    call_command("seed_demo", verbosity=0)
    assert OnboardingStyle.load().status == status
