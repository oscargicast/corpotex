"""Evolution webhook: secret, allowlist, @lid, duplicates, fromMe and media."""

import base64
import json

import pytest

from messaging.models import AllowedNumber, Message, Turn
from tests.scenario import build

SECRET = "test-secret"
URL = f"/webhooks/evolution/{SECRET}/"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


@pytest.fixture(autouse=True)
def webhook_settings(settings):
    settings.EVOLUTION_WEBHOOK_SECRET = SECRET


@pytest.fixture
def scenario(db, sales):
    return build(owner=sales)


def payload(phone="51906746241", text="hola", *, message_id="MSG1", from_me=False, remote_jid=None, extra_key=None, message=None):
    key = {"remoteJid": remote_jid or f"{phone}@s.whatsapp.net", "fromMe": from_me, "id": message_id, **(extra_key or {})}
    return {
        "event": "messages.upsert",
        "instance": "corpotex",
        "data": {"key": key, "message": message or {"conversation": text}, "messageTimestamp": 1760100000},
    }


def post(client, body, url=URL):
    return client.post(url, data=json.dumps(body), content_type="application/json")


@pytest.mark.django_db
def test_wrong_secret_is_forbidden(anonymous_client, scenario):
    assert post(anonymous_client, payload(), url="/webhooks/evolution/nope/").status_code == 403
    assert Message.objects.count() == 0


@pytest.mark.django_db
def test_unknown_number_is_dropped(anonymous_client, scenario):
    assert post(anonymous_client, payload(phone="51999999999")).status_code == 200
    assert Message.objects.filter(author="supplier").count() == 0
    assert Turn.objects.count() == 0


@pytest.mark.django_db
def test_allowlisted_message_is_stored_and_queued(anonymous_client, scenario):
    assert post(anonymous_client, payload(text="ya está la mitad")).status_code == 200
    message = Message.objects.get(author="supplier")
    assert message.text == "ya está la mitad"
    assert message.status == "received"
    assert message.external_id == "MSG1"
    assert message.conversation == scenario["conversation"]
    assert Turn.objects.filter(conversation=scenario["conversation"], status="pending", reason="message").count() == 1


@pytest.mark.django_db
def test_group_and_inactive_numbers_are_ignored(anonymous_client, scenario):
    post(anonymous_client, payload(remote_jid="1203630@g.us"))
    scenario["number"].active = False
    scenario["number"].save()
    post(anonymous_client, payload(message_id="MSG2"))
    assert Message.objects.count() == 0


@pytest.mark.django_db
def test_lid_resolves_through_remote_jid_alt(anonymous_client, scenario):
    body = payload(remote_jid="12345@lid", extra_key={"remoteJidAlt": "51906746241@s.whatsapp.net"})
    assert post(anonymous_client, body).status_code == 200
    assert Message.objects.filter(author="supplier").count() == 1
    assert AllowedNumber.objects.get(phone="51906746241").lid == "12345@lid"
    # Next time the lid alone is enough.
    post(anonymous_client, payload(remote_jid="12345@lid", message_id="MSG2"))
    assert Message.objects.filter(author="supplier").count() == 2


@pytest.mark.django_db
def test_duplicate_external_id_is_ignored(anonymous_client, scenario):
    post(anonymous_client, payload())
    post(anonymous_client, payload())
    assert Message.objects.filter(author="supplier").count() == 1
    assert Turn.objects.count() == 1


@pytest.mark.django_db
def test_from_me_without_echo_is_the_manager_typing(anonymous_client, scenario):
    post(anonymous_client, payload(text="ya le deposito", from_me=True))
    message = Message.objects.get()
    assert message.author == "manager"
    assert message.status == "sent"
    assert Turn.objects.count() == 0


@pytest.mark.django_db
def test_from_me_echo_of_our_own_send_is_matched(anonymous_client, scenario):
    from django.utils import timezone

    sent = Message.objects.create(
        conversation=scenario["conversation"], author="agent", text="buenos días, ¿cómo va?", status="sent", sent_at=timezone.now()
    )
    post(anonymous_client, payload(text="buenos días, ¿cómo va?", from_me=True, message_id="ECHO1"))
    sent.refresh_from_db()
    assert sent.external_id == "ECHO1"
    assert Message.objects.count() == 1


@pytest.mark.django_db
def test_base64_image_is_saved_as_media(anonymous_client, scenario, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    message = {"imageMessage": {"caption": "avance", "base64": base64.b64encode(PNG).decode()}}
    post(anonymous_client, payload(message=message))
    stored = Message.objects.get(author="supplier")
    assert stored.text == "avance"
    assert stored.media
    assert stored.media.read() == PNG


@pytest.mark.django_db
def test_other_events_are_acknowledged_without_storing(anonymous_client, scenario):
    body = {"event": "connection.update", "data": {"state": "open"}}
    assert post(anonymous_client, body).status_code == 200
    assert Message.objects.count() == 0


@pytest.mark.django_db
def test_lid_resolves_through_sender_pn_and_previous_remote_jid(anonymous_client, scenario):
    """WhatsApp addresses Valeria's chat by LID (seen on the real instance, 10/10 17:25); the
    phone may travel in any of the alternate keys."""
    body = payload(remote_jid="162509248041191@lid", extra_key={"senderPn": "51906746241@s.whatsapp.net", "addressingMode": "lid"})
    assert post(anonymous_client, body).status_code == 200
    assert Message.objects.filter(author="supplier").count() == 1
    assert AllowedNumber.objects.get(phone="51906746241").lid == "162509248041191@lid"
    body = payload(remote_jid="162509248041191@lid", message_id="MSG2", extra_key={"previousRemoteJid": "51906746241@s.whatsapp.net"})
    post(anonymous_client, body)
    assert Message.objects.filter(author="supplier").count() == 2


@pytest.mark.django_db
def test_unknown_lid_without_phone_is_resolved_through_evolution(anonymous_client, scenario):
    from unittest import mock

    with mock.patch("messaging.evolution.EvolutionClient.resolve_phone", return_value="51906746241") as resolve:
        assert post(anonymous_client, payload(remote_jid="162509248041191@lid", message_id="MSG3")).status_code == 200
    resolve.assert_called_once_with("162509248041191@lid")
    message = Message.objects.get(author="supplier")
    assert message.conversation.allowed_number.phone == "51906746241"
    assert AllowedNumber.objects.get(phone="51906746241").lid == "162509248041191@lid"
    # A LID nobody owns is dropped, even if Evolution knows its phone.
    with mock.patch("messaging.evolution.EvolutionClient.resolve_phone", return_value="51999999999"):
        post(anonymous_client, payload(remote_jid="99999999999999@lid", message_id="MSG4"))
    assert Message.objects.filter(author="supplier").count() == 1


@pytest.mark.django_db
def test_unknown_lid_is_dropped_when_evolution_is_down(anonymous_client, scenario):
    from unittest import mock

    from messaging.evolution import EvolutionUnavailable

    with mock.patch("messaging.evolution.EvolutionClient.resolve_phone", side_effect=EvolutionUnavailable("down")):
        assert post(anonymous_client, payload(remote_jid="162509248041191@lid", message_id="MSG5")).status_code == 200
    assert Message.objects.count() == 0
