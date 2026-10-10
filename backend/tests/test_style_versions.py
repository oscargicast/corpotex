from agent.persona.style import load_template
from core.models import StyleVersion
from suppliers.models import Supplier


def test_restore_never_rewrites_history(manager_client, manager, config):
    config.agent_user = manager
    config.save()
    supplier = Supplier.objects.create(
        name="Confecciones del Norte", kind="workshop", notes="nuevas"
    )
    first = StyleVersion.objects.create(
        user=manager,
        style_md=load_template(),
        notes_snapshot={str(supplier.id): "Trato: usted"},
        source=StyleVersion.Source.TEMPLATE,
    )
    StyleVersion.objects.create(user=manager, style_md="otro", source=StyleVersion.Source.DAILY)

    listed = manager_client.get("/api/style/versions/").json()
    assert [v["source"] for v in listed] == ["daily", "template"]

    response = manager_client.post(f"/api/style/versions/{first.id}/restore/")
    assert response.status_code == 201
    assert response.json()["source"] == "rollback"
    assert StyleVersion.objects.count() == 3
    manager.refresh_from_db()
    supplier.refresh_from_db()
    assert manager.style_md == load_template()
    assert supplier.notes == "Trato: usted"


def test_version_detail_has_the_style(manager_client, manager):
    version = StyleVersion.objects.create(
        user=manager, style_md="estilo", source=StyleVersion.Source.MANUAL
    )
    body = manager_client.get(f"/api/style/versions/{version.id}/").json()
    assert body["style_md"] == "estilo"
    assert body["notes_snapshot"] == {}


def test_sales_cannot_see_versions(sales_client):
    assert sales_client.get("/api/style/versions/").status_code == 403
