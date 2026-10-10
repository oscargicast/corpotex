import pytest
from django.apps import apps
from django.conf import settings


def test_all_seven_apps_are_installed():
    labels = {app.label for app in apps.get_app_configs()}
    assert {"core", "suppliers", "operations", "messaging", "manager", "agent", "seed"} <= labels


def test_twenty_nine_models_are_registered():
    own = [
        model
        for model in apps.get_models()
        if model._meta.app_label in {"core", "suppliers", "operations", "messaging", "manager"}
    ]
    assert len(own) == 29, sorted(m.__name__ for m in own)


def test_celery_routes_and_schedule():
    assert settings.CELERY_TASK_ROUTES["agent.tasks.run_turn"]["queue"] == "turns"
    assert settings.CELERY_TASK_ROUTES["manager.tasks.tick"]["queue"] == "periodic"
    assert settings.CELERY_TASK_ROUTES["core.tasks.refresh_style"]["queue"] == "style"
    assert settings.CELERY_BEAT_SCHEDULE["tick"]["schedule"] == 10.0


@pytest.mark.django_db
def test_schema_requires_auth_and_renders_with_token(anonymous_client, manager_client):
    assert anonymous_client.get("/api/schema/").status_code == 401
    response = manager_client.get("/api/schema/")
    assert response.status_code == 200
    assert b"/api/clock/" in response.content
