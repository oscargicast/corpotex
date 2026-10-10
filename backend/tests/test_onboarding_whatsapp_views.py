"""WhatsApp onboarding endpoints (B4.4) over a fake Evolution client."""

import pytest

from core.models import Config
from messaging import views_onboarding
from messaging.evolution import EvolutionUnavailable

pytestmark = pytest.mark.django_db

SECRET = "s3cret-webhook"
WEBHOOK_URL = f"https://corpotex.oscargicast.com/webhooks/evolution/{SECRET}/"


class FakeClient:
    def __init__(self, *, state="open", webhook=None, has_access_token=True, qr=None, error=None):
        self.state = state
        self.webhook = webhook
        self.has_access_token = has_access_token
        self.qr = qr
        self.error = error
        self.calls: list[tuple] = []

    def _maybe_fail(self):
        if self.error:
            raise self.error

    def connection_state(self):
        self._maybe_fail()
        return self.state

    def find_webhook(self):
        return self.webhook

    def find_settings(self):
        return {"groupsIgnore": True, "readMessages": False, "unknown": 1}

    def connect_qr(self):
        self._maybe_fail()
        return self.qr

    def set_webhook(self, url, events=("MESSAGES_UPSERT",), base64=True):
        self.calls.append(("set_webhook", url, tuple(events), base64))
        self.webhook = {
            "enabled": True,
            "url": url,
            "events": list(events),
            "webhookBase64": base64,
        }
        return {}

    def set_settings(self, **overrides):
        self.calls.append(("set_settings", overrides))
        return {}


@pytest.fixture
def fake(settings, monkeypatch):
    settings.EVOLUTION_WEBHOOK_SECRET = SECRET
    holder = {"client": FakeClient()}
    monkeypatch.setattr(views_onboarding, "_client", lambda: holder["client"])

    def use(client: FakeClient) -> FakeClient:
        holder["client"] = client
        return client

    return use


def test_status_is_manager_only(fake, sales_client, anonymous_client):
    assert sales_client.get("/api/onboarding/whatsapp/").status_code == 403
    assert anonymous_client.get("/api/onboarding/whatsapp/").status_code == 401


def test_status_masks_secret_and_records_done_at(fake, manager_client):
    fake(
        FakeClient(
            webhook={
                "enabled": True,
                "url": WEBHOOK_URL,
                "events": ["MESSAGES_UPSERT"],
                "webhookBase64": True,
            }
        )
    )
    response = manager_client.get("/api/onboarding/whatsapp/")
    assert response.status_code == 200, response.content
    data = response.json()
    assert data["state"] == "open"
    assert data["offline"] is False
    assert data["webhook"] == {
        "url": "https://corpotex.oscargicast.com/webhooks/evolution/****/",
        "events": ["MESSAGES_UPSERT"],
        "base64": True,
    }
    assert SECRET not in response.content.decode()
    assert data["settings"] == {"groupsIgnore": True, "readMessages": False}
    assert data["done_at"]
    assert Config.load().onboarding["whatsapp"]["done_at"] == data["done_at"]

    # The first done_at is kept on later reads.
    assert manager_client.get("/api/onboarding/whatsapp/").json()["done_at"] == data["done_at"]


def test_status_not_done_while_webhook_points_elsewhere(fake, manager_client):
    fake(
        FakeClient(
            webhook={"enabled": True, "url": "https://other/x/", "events": ["MESSAGES_UPSERT"]}
        )
    )
    data = manager_client.get("/api/onboarding/whatsapp/").json()
    assert data["done_at"] is None
    assert "whatsapp" not in Config.load().onboarding


def test_status_offline_without_access_token(fake, manager_client):
    fake(FakeClient(has_access_token=False, error=EvolutionUnavailable("network")))
    data = manager_client.get("/api/onboarding/whatsapp/").json()
    assert data == {
        "state": "unknown",
        "webhook": None,
        "settings": None,
        "offline": True,
        "done_at": data["done_at"],
    }
    assert data["done_at"]


def test_status_502_when_evolution_is_down(fake, manager_client):
    fake(FakeClient(error=EvolutionUnavailable("access_denied", status=302)))
    response = manager_client.get("/api/onboarding/whatsapp/")
    assert response.status_code == 502
    assert response.json()["error_code"] == "evolution_unavailable"


def test_status_400_without_webhook_secret(fake, manager_client, settings):
    settings.EVOLUTION_WEBHOOK_SECRET = ""
    response = manager_client.get("/api/onboarding/whatsapp/")
    assert response.status_code == 400
    assert response.json()["error_code"] == "webhook_secret_missing"


def test_qr_returns_data_url_or_null(fake, manager_client):
    assert manager_client.post("/api/onboarding/whatsapp/qr/").json() == {"qr_base64": None}
    fake(FakeClient(state="connecting", qr="data:image/png;base64,AAAA"))
    assert manager_client.post("/api/onboarding/whatsapp/qr/").json() == {
        "qr_base64": "data:image/png;base64,AAAA"
    }


def test_webhook_configures_instance_and_marks_done(fake, manager_client):
    client = fake(FakeClient())
    response = manager_client.post("/api/onboarding/whatsapp/webhook/")
    assert response.status_code == 200, response.content
    assert client.calls == [
        ("set_webhook", WEBHOOK_URL, ("MESSAGES_UPSERT",), True),
        ("set_settings", {}),
    ]
    data = response.json()
    assert data["webhook"]["url"].endswith("/webhooks/evolution/****/")
    assert data["done_at"]
    assert Config.load().onboarding["whatsapp"]["done_at"] == data["done_at"]
