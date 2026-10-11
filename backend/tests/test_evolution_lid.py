"""`find_messages` reads a contact's phone chat and LID chat together (10/10 finding: the
role-play chat with Valeria lives under `<id>@lid`, the older history under the phone jid)."""

from unittest import mock

import pytest

from messaging.evolution import EvolutionClient
from messaging.models import AllowedNumber
from tests.scenario import build

PHONE = "51906746241@s.whatsapp.net"
LID = "162509248041191@lid"


def record(mid, remote, ts, *, alt=None, from_me=False):
    key = {"id": mid, "fromMe": from_me, "remoteJid": remote}
    if alt:
        key["remoteJidAlt"] = alt
    return {"key": key, "message": {"conversation": mid}, "messageTimestamp": ts}


PHONE_CHAT = [record("A1", PHONE, 1_000, from_me=True), record("A2", PHONE, 1_100)]
LID_CHAT = [record("B1", LID, 1_200, alt=PHONE), record("B2", LID, 1_300, alt=PHONE, from_me=True), record("A2", LID, 1_100)]  # A2 echoed in both


def fake_request(method, path, json=None):
    where = (json or {}).get("where") or {}
    key = where.get("key") or {}
    if key.get("remoteJid") == PHONE:
        records = PHONE_CHAT
    elif key.get("remoteJid") == LID:
        records = LID_CHAT
    elif key.get("remoteJidAlt") == PHONE:
        records = [r for r in LID_CHAT if r["key"].get("remoteJidAlt")]
    else:
        records = []
    return {"messages": {"records": list(reversed(records)), "pages": 1}}


@pytest.fixture
def client(settings):
    settings.EVOLUTION_API_URL = "http://evolution.test"
    settings.EVOLUTION_INSTANCE = "corpotex"
    settings.EVOLUTION_INSTANCE_TOKEN = "token"
    with mock.patch.object(EvolutionClient, "_request", side_effect=fake_request):
        yield EvolutionClient.from_settings()


@pytest.mark.django_db
def test_phone_jid_merges_the_lid_chat_and_caches_the_lid(client, sales):
    build(owner=sales)
    records = client.find_messages("51906746241", since=0)
    assert [r["key"]["id"] for r in records] == ["A1", "A2", "B1", "B2"]  # merged, deduplicated, oldest first
    assert AllowedNumber.objects.get(phone="51906746241").lid == LID


@pytest.mark.django_db
def test_lid_jid_merges_the_phone_chat(client, sales):
    build(owner=sales)
    records = client.find_messages(LID, since=1_050)
    assert [r["key"]["id"] for r in records] == ["A2", "B1", "B2"]
    assert client.chat_jids(LID) == [PHONE, LID]


@pytest.mark.django_db
def test_limit_keeps_the_most_recent_across_both_chats(client, sales):
    build(owner=sales)
    assert [r["key"]["id"] for r in client.find_messages("51906746241", since=0, limit=2)] == ["B1", "B2"]


@pytest.mark.django_db
def test_without_a_mapping_only_the_given_chat_is_read(client, db):
    with mock.patch.object(EvolutionClient, "resolve_lid", return_value=None):
        assert client.chat_jids("51900000000") == ["51900000000@s.whatsapp.net"]
