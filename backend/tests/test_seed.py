"""`seed_demo` against the real fixtures in `backend/seed/data` (skipped until they land)."""

import pytest
from django.core.management import call_command

from seed.loader import DATA_DIR, MANAGER_PHONE, REAL_SUPPLIER_PHONE

pytestmark = pytest.mark.skipif(not (DATA_DIR / "suppliers.json").exists(), reason="seed data not present")


@pytest.mark.django_db
def test_seed_demo_loads_and_is_idempotent(monkeypatch):
    from core.models import Config, StyleVersion, User
    from messaging.models import AllowedNumber, Conversation
    from operations.models import Order, PurchaseOrder, Requirement
    from suppliers.models import Supplier

    monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "admin")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "admin")
    call_command("seed_demo", verbosity=0)
    call_command("seed_demo", verbosity=0)

    assert User.objects.filter(username="admin", is_superuser=True).count() == 1
    assert set(User.objects.exclude(is_superuser=True).values_list("username", flat=True)) == {"gerente", "comercial", "produccion"}
    assert Supplier.objects.count() >= 8 and Order.objects.count() >= 6 and PurchaseOrder.objects.count() >= 10
    assert Requirement.objects.count() > 0 and Order.objects.exclude(estimated_on=None).count() == Order.objects.count()

    real = AllowedNumber.objects.get(phone=REAL_SUPPLIER_PHONE)
    assert real.supplier.name == "Confecciones del Norte" and real.name == "" and real.active and not real.simulated
    assert AllowedNumber.objects.filter(simulated=True).count() >= 5
    assert all(p.isascii() for p in AllowedNumber.objects.values_list("phone", flat=True))
    assert PurchaseOrder.objects.filter(status__in=PurchaseOrder.OPEN_STATUSES, conversation__isnull=True, supplier__is_in_house=False).count() == 0
    scene = PurchaseOrder.objects.get(code="PT-0038")  # Valeria's workshop: proactive turns go to WhatsApp, not the simulator.
    assert scene.conversation.channel == "whatsapp" and scene.conversation.allowed_number.phone == REAL_SUPPLIER_PHONE

    config = Config.load()
    assert config.agent_phone == MANAGER_PHONE and config.agent_user.username == "gerente" and config.plant_name

    versions = StyleVersion.objects.filter(user__username="gerente").order_by("created_at")
    assert versions.first().source == "template"
    assert versions.first().style_md.startswith("# Estilo del Gerente")
    assert versions.count() >= 2
    assert config.agent_user.style_md == versions.last().style_md
    for supplier in Supplier.objects.filter(source="external"):
        assert supplier.source_detail and supplier.notes == ""


@pytest.mark.django_db
def test_seed_demo_fills_the_status_timeline_and_runs_on_real_time():
    from django.utils import timezone

    from core.models import Config
    from operations.models import Order, PurchaseOrder, StatusChange

    call_command("seed_demo", verbosity=0)
    config = Config.load()
    assert config.clock_factor == 1 and not config.clock_paused and config.clock_sim_start == config.clock_real_start
    assert abs((timezone.now() - config.clock_real_start).total_seconds()) < 120
    for order in Order.objects.all():
        statuses = [c.status for c in order.status_changes.all()]
        assert statuses[0] == "registered" and statuses[-1] == order.status
        assert all(c.at <= timezone.now() for c in order.status_changes.all())
    for po in PurchaseOrder.objects.all():
        statuses = [c.status for c in po.status_changes.all()]
        assert statuses[0] == "suggested" and statuses[-1] == po.status
    assert StatusChange.objects.count() >= Order.objects.count() + PurchaseOrder.objects.count()
    assert set(Order.objects.values_list("code", flat=True)) == {c for c in Order.objects.values_list("code", flat=True) if c.startswith("CP-2026-")}
    assert all(c[:3] in ("PT-", "PI-", "PF-") for c in PurchaseOrder.objects.values_list("code", flat=True))


@pytest.mark.django_db
def test_loader_rejects_codes_outside_the_documented_format(tmp_path):
    import json

    from seed.loader import Loader, SeedError

    (tmp_path / "orders.json").write_text(json.dumps([{"code": "OC-2026-0001", "customer": "x", "brand": "y", "promised_on": "T+5", "items": []}]))
    with pytest.raises(SeedError, match="CP-AAAA-NNNN"):
        Loader(data_dir=tmp_path).load_orders()


@pytest.mark.django_db
def test_scene_purchase_order_has_the_fixed_report_token():
    from operations.models import PurchaseOrder
    from seed.loader import SCENE_PURCHASE_ORDER, SCENE_REPORT_TOKEN

    call_command("seed_demo", verbosity=0)
    assert str(PurchaseOrder.objects.get(code=SCENE_PURCHASE_ORDER).report_token) == SCENE_REPORT_TOKEN


@pytest.mark.django_db
def test_seed_exits_carry_their_reason():
    from operations.models import Order, PurchaseOrder

    call_command("seed_demo", verbosity=0)
    po = PurchaseOrder.objects.get(code="PT-0027")
    assert po.status == "cancelled_by_supplier"
    last = po.status_changes.last()
    assert last.status == "cancelled_by_supplier" and last.actor == "agent" and last.note == "se le malograron dos máquinas"
    assert [c.status for c in po.status_changes.all()][:2] == ["suggested", "approved"]
    order = Order.objects.get(code="CP-2026-0109")
    assert order.status_changes.last().note.startswith("Cliente canceló")
    for change in __import__("operations.models", fromlist=["StatusChange"]).StatusChange.objects.filter(status__in=("cancelled", "cancelled_by_supplier", "declined_by_supplier")):
        assert change.note, change


@pytest.mark.django_db
def test_scene_cancellation_leaves_current_and_replaced_routes(manager_client, manager):
    """Step 8 of the script: PT-0038 cancels, the decision is approved and the map gets
    {current: new, replaced: old} for the same day."""
    from manager.services import resolve_decision
    from operations import services
    from operations.models import PurchaseOrder, Route

    call_command("seed_demo", verbosity=0)
    po = PurchaseOrder.objects.get(code="PT-0038")
    order = po.items.first().requirement.order
    old_day = order.estimated_on or order.promised_on
    old = Route.objects.get(date=old_day, status="planned")
    assert old.stops.filter(order=order).exists()
    po, created, decision = services.cancel_by_supplier(po, reason="se me enfermó la gente")
    assert len(created) >= 1 and all(p.redistributed_from == po for p in created)
    before, after = decision.detail["before"]["route_id"], decision.detail["after"]["route_id"]
    proposed = Route.objects.get(pk=after)
    order.refresh_from_db()
    assert before == old.id and proposed.status == "proposed" and proposed.date == order.estimated_on != old_day
    resolve_decision(decision, action="approve", actor=manager)
    body = manager_client.get("/api/routes/?current=1").json()
    assert body["current"]["id"] == after and body["replaced"]["id"] == before
    assert {s["order"]["code"] for s in body["current"]["stops"] if s["order"]} >= {order.code}
    assert {s["order"]["code"] for s in body["replaced"]["stops"] if s["order"]} >= {order.code}
    assert all(s["kind"] in ("plant", "delivery") for s in body["current"]["stops"])
    assert manager_client.get(f"/api/routes/{before}/").json()["status"] == "replaced"


@pytest.mark.django_db
def test_seed_keeps_the_dashboard_chats(manager):
    from django.utils import timezone

    from messaging.models import Message, Turn
    from messaging.services import dashboard_conversation, enqueue_turn

    conversation = dashboard_conversation(manager)
    Message.objects.create(conversation=conversation, author="user", text="hola", status="received", sent_at=timezone.now())
    turn = enqueue_turn(conversation, "message")
    call_command("seed_demo", verbosity=0)
    assert Message.objects.filter(conversation=conversation, text="hola").exists()
    assert Turn.objects.filter(pk=turn.pk, status="pending").exists()


@pytest.mark.django_db
def test_seed_users_carry_the_demo_names(manager_client):
    from core.models import User

    call_command("seed_demo", verbosity=0)
    assert [(u.username, u.first_name, u.last_name) for u in User.objects.filter(username__in=["gerente", "comercial", "produccion"]).order_by("username")] == [
        ("comercial", "Nesky", ""), ("gerente", "Oscar", "Giraldo"), ("produccion", "Freddy", ""),
    ]
    me = manager_client.get("/api/auth/me/").json()
    assert me["first_name"] == "Oscar" and me["last_name"] == "Giraldo"
    # A name the manager changed by hand is kept on the next seed.
    User.objects.filter(username="gerente").update(first_name="Óscar", last_name="G.")
    call_command("seed_demo", verbosity=0)
    assert User.objects.get(username="gerente").first_name == "Óscar"
