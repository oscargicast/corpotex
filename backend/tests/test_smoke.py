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


@pytest.mark.django_db
def test_schema_types_the_computed_responses(manager_client):
    """The frontend generates its types from the schema (`docs/api/README.md`): the routes of
    ADR 0025 and the computed lists must not come out as plain objects."""
    import json

    schema = json.loads(manager_client.get("/api/schema/", HTTP_ACCEPT="application/json").content)
    components = schema["components"]["schemas"]
    for name in ("ClassificationResult", "ClassificationProductRequest", "BreakDownResult", "GenerateResult", "PendingPurchase", "ProductBrand", "StatusChange", "OrderRef", "RedistributedInto", "RequirementPurchaseOrder"):
        assert name in components, name
    assert schema["paths"]["/api/orders/{id}/classify/"]["post"]["responses"]["200"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/ClassificationResult"}
    assert schema["paths"]["/api/requirements/pending/"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["items"] == {"$ref": "#/components/schemas/PendingPurchase"}
    assert components["OrderDetail"]["properties"]["status_history"]["items"] == {"$ref": "#/components/schemas/StatusChange"}
    assert components["OrderDetail"]["properties"]["alerts"]["items"] == {"$ref": "#/components/schemas/Alert"}
    assert components["PurchaseOrderDetail"]["properties"]["orders"]["items"] == {"$ref": "#/components/schemas/OrderRef"}
