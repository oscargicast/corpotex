"""Unit tests for step 1 of the onboarding (WhatsApp). No Django, no network."""

import json

import pytest
import requests

from messaging.evolution import DEFAULT_SETTINGS, EvolutionClient
from messaging.whatsapp_onboarding import (
    configure,
    mask_webhook_url,
    onboarding_status,
    qr,
    webhook_url_from_env,
)

SECRET = "s3cr3t-webhook"
WEBHOOK_URL = f"https://corpotex.oscargicast.com/webhooks/evolution/{SECRET}/"


def evolution_webhook(**overrides):
    """What GET /webhook/find/{instance} returns once configured by us."""
    webhook = {
        "id": "wh1",
        "url": WEBHOOK_URL,
        "enabled": True,
        "events": ["MESSAGES_UPSERT"],
        "webhookByEvents": False,
        "webhookBase64": True,
    }
    webhook.update(overrides)
    return webhook


def evolution_settings():
    return {"id": "st1", "instanceId": "i1", **DEFAULT_SETTINGS}


class FakeClient:
    """Duck-typed EvolutionClient that records calls in order."""

    def __init__(self, state="open", webhook=None, settings=None, qr=None):
        self.state = state
        self.webhook = webhook
        self.settings = settings if settings is not None else evolution_settings()
        self.qr_value = qr
        self.calls = []

    def connection_state(self):
        self.calls.append(("connection_state",))
        return self.state

    def find_webhook(self):
        self.calls.append(("find_webhook",))
        return self.webhook

    def find_settings(self):
        self.calls.append(("find_settings",))
        return self.settings

    def connect_qr(self):
        self.calls.append(("connect_qr",))
        return self.qr_value

    def set_webhook(self, url, events=("MESSAGES_UPSERT",), base64=True):
        self.calls.append(("set_webhook", url, tuple(events), base64))
        self.webhook = evolution_webhook(url=url, events=list(events), webhookBase64=base64)
        return {"webhook": self.webhook}

    def set_settings(self, **overrides):
        self.calls.append(("set_settings", overrides))
        self.settings = {**evolution_settings(), **overrides}
        return self.settings


# -- status ------------------------------------------------------------------


def test_offline_without_access_token_makes_no_http_calls(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Evolution must not be called without the Access token")

    monkeypatch.setattr(requests, "request", forbidden)
    monkeypatch.setattr(requests.Session, "request", forbidden)
    client = EvolutionClient("https://evo.test", "corpotex", "token")

    status = onboarding_status(client, webhook_url=WEBHOOK_URL, has_access_token=False)

    assert status == {
        "state": "unknown",
        "webhook": None,
        "settings": None,
        "offline": True,
        "done": True,
    }


def test_done_when_open_and_webhook_configured_for_us():
    client = FakeClient(state="open", webhook=evolution_webhook())

    status = onboarding_status(client, webhook_url=WEBHOOK_URL, has_access_token=True)

    assert status["state"] == "open"
    assert status["offline"] is False
    assert status["done"] is True
    assert status["webhook"]["events"] == ["MESSAGES_UPSERT"]
    assert status["webhook"]["base64"] is True
    assert status["settings"] == DEFAULT_SETTINGS
    assert client.calls == [("connection_state",), ("find_webhook",), ("find_settings",)]


def test_secret_is_masked_in_webhook_url():
    client = FakeClient(state="open", webhook=evolution_webhook())

    status = onboarding_status(client, webhook_url=WEBHOOK_URL, has_access_token=True)

    assert status["webhook"]["url"] == "https://corpotex.oscargicast.com/webhooks/evolution/****/"
    assert SECRET not in json.dumps(status)


@pytest.mark.parametrize(
    "state, webhook",
    [
        ("close", evolution_webhook()),
        ("connecting", evolution_webhook()),
        ("open", None),
        ("open", evolution_webhook(url="https://other.example/webhooks/evolution/x/")),
        ("open", evolution_webhook(events=["CONNECTION_UPDATE"])),
        ("open", evolution_webhook(webhookBase64=False)),
        ("open", evolution_webhook(enabled=False)),
    ],
)
def test_not_done_unless_open_and_webhook_matches(state, webhook):
    client = FakeClient(state=state, webhook=webhook)

    status = onboarding_status(client, webhook_url=WEBHOOK_URL, has_access_token=True)

    assert status["done"] is False
    assert status["offline"] is False


def test_webhook_none_when_instance_has_no_webhook():
    status = onboarding_status(
        FakeClient(webhook=None), webhook_url=WEBHOOK_URL, has_access_token=True
    )

    assert status["webhook"] is None


def test_settings_keep_only_the_known_keys():
    status = onboarding_status(
        FakeClient(webhook=None), webhook_url=WEBHOOK_URL, has_access_token=True
    )

    assert set(status["settings"]) == set(DEFAULT_SETTINGS)
    assert "instanceId" not in status["settings"]


# -- qr ----------------------------------------------------------------------


def test_qr_returns_data_url_or_none():
    assert qr(FakeClient(qr="data:image/png;base64,AAA=")) == "data:image/png;base64,AAA="
    assert qr(FakeClient(qr=None)) is None


# -- configure ---------------------------------------------------------------


def test_configure_sets_webhook_then_settings_and_reports_done():
    client = FakeClient(state="open", webhook=None)

    status = configure(client, webhook_url=WEBHOOK_URL)

    assert client.calls[:2] == [
        ("set_webhook", WEBHOOK_URL, ("MESSAGES_UPSERT",), True),
        ("set_settings", {}),
    ]
    assert status["done"] is True
    assert status["offline"] is False
    assert status["webhook"]["url"].endswith("/webhooks/evolution/****/")
    assert SECRET not in json.dumps(status)


def test_configure_is_not_done_while_instance_is_not_linked():
    status = configure(FakeClient(state="close", webhook=None), webhook_url=WEBHOOK_URL)

    assert status["done"] is False
    assert status["webhook"]["events"] == ["MESSAGES_UPSERT"]


# -- helpers -----------------------------------------------------------------


def test_webhook_url_from_env_uses_public_default():
    url = webhook_url_from_env({"EVOLUTION_WEBHOOK_SECRET": SECRET})

    assert url == WEBHOOK_URL


def test_webhook_url_from_env_honours_public_base_url():
    url = webhook_url_from_env(
        {"EVOLUTION_WEBHOOK_SECRET": SECRET, "PUBLIC_BASE_URL": "http://localhost:8000/"}
    )

    assert url == f"http://localhost:8000/webhooks/evolution/{SECRET}/"


def test_webhook_url_from_env_requires_secret():
    with pytest.raises(ValueError):
        webhook_url_from_env({})


@pytest.mark.parametrize(
    "url, masked",
    [
        (WEBHOOK_URL, "https://corpotex.oscargicast.com/webhooks/evolution/****/"),
        ("https://h.test/webhooks/evolution/abc", "https://h.test/webhooks/evolution/****"),
        ("https://h.test/abc/", "https://h.test/****/"),
        ("https://h.test/", "https://h.test/"),
    ],
)
def test_mask_webhook_url(url, masked):
    assert mask_webhook_url(url) == masked
