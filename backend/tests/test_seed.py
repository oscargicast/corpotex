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
    assert Conversation.objects.filter(channel="whatsapp").count() == 0  # proactive turns start on the simulator

    config = Config.load()
    assert config.agent_phone == MANAGER_PHONE and config.agent_user.username == "gerente" and config.plant_name

    versions = StyleVersion.objects.filter(user__username="gerente").order_by("created_at")
    assert versions.first().source == "template"
    assert versions.first().style_md.startswith("# Estilo del Gerente")
    assert versions.count() >= 2
    assert config.agent_user.style_md == versions.last().style_md
    for supplier in Supplier.objects.filter(source="external"):
        assert supplier.source_detail and supplier.notes == ""
