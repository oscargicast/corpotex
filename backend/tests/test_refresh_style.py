from datetime import timedelta

import pytest
from django.utils import timezone

from agent.persona.style import load_template
from core.models import StyleVersion
from core.style import refresh_style
from manager.models import Alert
from messaging.models import AllowedNumber, Conversation, Message
from suppliers.models import Supplier
from tests.test_style_extraction import FakeSdk


@pytest.fixture
def fake_sdk(monkeypatch):
    """Patch the real `agent.sdk`: `from agent import sdk` reads the package attribute."""
    import agent.sdk as real_sdk

    def install(**kwargs):
        fake = FakeSdk(**kwargs)
        monkeypatch.setattr(real_sdk, "complete", fake.complete)
        monkeypatch.setattr(real_sdk, "is_connected", fake.is_connected)
        return fake

    return install


@pytest.fixture
def owner(config, manager):
    manager.style_md = load_template()
    manager.style_refreshed_at = timezone.now() - timedelta(hours=1)
    manager.save()
    config.agent_user = manager
    config.save()
    return manager


@pytest.fixture
def supplier(db):
    supplier = Supplier.objects.create(
        name="Confecciones del Norte", kind="workshop", notes="Trato: usted"
    )
    number = AllowedNumber.objects.create(phone="51900000001", supplier=supplier, active=True)
    conversation = Conversation.objects.create(channel="whatsapp", allowed_number=number)
    supplier.conversation = conversation
    return supplier


def say(conversation, author, text, minutes_ago=10):
    return Message.objects.create(
        conversation=conversation,
        author=author,
        text=text,
        status=Message.Status.SENT,
        sent_at=timezone.now() - timedelta(minutes=minutes_ago),
    )


def test_no_new_messages_skips_model(owner, supplier, fake_sdk):
    sdk = fake_sdk(connected=False)
    say(supplier.conversation, Message.Author.AGENT, "del bot")
    assert refresh_style() is None
    assert sdk.calls == []
    owner.refresh_from_db()
    assert owner.style_refreshed_at > timezone.now() - timedelta(minutes=1)


def test_refresh_applies_a_valid_update(owner, supplier, fake_sdk):
    new_style = load_template().replace("## Muletillas", '## Muletillas\n- "de una nomás"')
    fake_sdk(
        replies={
            "Actualizas": {
                "style_md": new_style,
                "notes": [],
                "changelog": ['usa más "de una nomás"'],
            }
        }
    )
    say(supplier.conversation, Message.Author.MANAGER, "de una nomás, gracias")
    version = refresh_style()
    assert version.source == StyleVersion.Source.DAILY
    assert version.changelog == 'usa más "de una nomás"'
    owner.refresh_from_db()
    assert owner.style_md.startswith(new_style.strip())


def test_invalid_result_keeps_style_and_creates_alert(owner, supplier, fake_sdk):
    leaky = {
        "style_md": load_template() + "\nConfecciones del Norte\n",
        "notes": [],
        "changelog": [],
    }
    fake_sdk(replies={"Actualizas": leaky})
    say(supplier.conversation, Message.Author.MANAGER, "buenos días")
    assert refresh_style() is None
    owner.refresh_from_db()
    assert owner.style_md == load_template()
    alert = Alert.objects.get(kind=Alert.Kind.STYLE_REFRESH_FAILED)
    assert "S/" not in alert.text


def test_refresh_never_touches_supplier_notes(owner, supplier, fake_sdk):
    update = {
        "style_md": load_template(),
        "notes": [
            {"supplier": "Proveedor 1", "notes": {"trato": "tú", "tono": "x", "insistencia": "y"}}
        ],
        "changelog": ["con Proveedor 1 ahora escribe de tú"],
    }
    fake_sdk(replies={"Actualizas": update})
    say(supplier.conversation, Message.Author.MANAGER, "buenas causa")
    refresh_style()
    supplier.refresh_from_db()
    assert supplier.notes == "Trato: usted"
