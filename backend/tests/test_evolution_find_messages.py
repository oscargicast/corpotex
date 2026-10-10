"""`find_messages` pagination over a faked `POST /chat/findMessages` (newest first)."""

from datetime import UTC, datetime

import pytest
import requests

from messaging import evolution
from messaging.evolution import EvolutionClient

JID = "51906746241@s.whatsapp.net"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def _record(ts: int, from_me: bool = False) -> dict:
    return {
        "key": {"remoteJid": JID, "fromMe": from_me, "id": f"id-{ts}"},
        "pushName": "Gerente" if from_me else "Proveedor",
        "message": {"conversation": f"msg {ts}"},
        "messageTimestamp": ts,
    }


@pytest.fixture
def paged(monkeypatch):
    """Serve `timestamps` (any order) newest first, `page_size` per page; records the bodies."""
    bodies: list[dict] = []

    def install(timestamps: list[int], page_size: int = 50):
        ordered = sorted(timestamps, reverse=True)
        pages = max(1, -(-len(ordered) // page_size))

        def fake_request(method, url, headers=None, json=None, timeout=None, allow_redirects=True):
            assert method == "POST" and url.endswith("/chat/findMessages/corpotex")
            assert headers["User-Agent"] == evolution.USER_AGENT
            bodies.append(json)
            assert json["offset"] == evolution.FIND_MESSAGES_PAGE_SIZE
            page = json["page"]
            # The fake pages by its own `page_size` so the tests stay small.
            chunk = ordered[(page - 1) * page_size : page * page_size]
            return FakeResponse(
                {
                    "messages": {
                        "total": len(ordered),
                        "pages": pages,
                        "currentPage": page,
                        "records": [_record(ts, from_me=ts % 2 == 0) for ts in chunk],
                    }
                }
            )

        monkeypatch.setattr(requests, "request", fake_request)
        return bodies

    return install


@pytest.fixture
def client():
    return EvolutionClient("https://evolution.test", "corpotex", "token")


def test_returns_ascending_and_stops_at_since(client, paged):
    bodies = paged([100, 200, 300, 400, 500, 600], page_size=2)
    records = client.find_messages(JID, since=300)
    assert [r["messageTimestamp"] for r in records] == [300, 400, 500, 600]
    # Pages 1 (600, 500) and 2 (400, 300) are fresh; page 3 holds 200, so it is read and stops.
    assert [b["page"] for b in bodies] == [1, 2, 3]
    assert all(b["where"] == {"key": {"remoteJid": JID}} for b in bodies)


def test_limit_keeps_the_most_recent(client, paged):
    bodies = paged([100, 200, 300, 400, 500, 600], page_size=2)
    records = client.find_messages(JID, since=0, limit=3)
    assert [r["messageTimestamp"] for r in records] == [400, 500, 600]
    assert [b["page"] for b in bodies] == [1, 2]  # stops once `limit` fresh records are in hand


def test_stops_at_last_page(client, paged):
    bodies = paged([100, 200, 300], page_size=2)
    records = client.find_messages(JID, since=0)
    assert [r["messageTimestamp"] for r in records] == [100, 200, 300]
    assert [b["page"] for b in bodies] == [1, 2]


def test_since_accepts_datetime_and_keeps_push_name_on_from_me(client, paged):
    paged([1_700_000_000, 1_700_000_100], page_size=50)
    since = datetime.fromtimestamp(1_700_000_050, tz=UTC)
    records = client.find_messages(JID, since=since)
    assert len(records) == 1
    assert records[0]["key"]["fromMe"] is True
    assert records[0]["pushName"] == "Gerente"


def test_module_entry_point_completes_bare_number(monkeypatch, paged, settings):
    paged([10, 20], page_size=50)
    seen = {}

    def fake_find(self, jid, since, *, limit=300):
        seen.update(jid=jid, since=since, limit=limit)
        return []

    monkeypatch.setattr(EvolutionClient, "find_messages", fake_find)
    assert evolution.find_messages("51906746241", 5, limit=7) == []
    assert seen == {"jid": JID, "since": 5, "limit": 7}
