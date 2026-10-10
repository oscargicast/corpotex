"""Unit tests for the Evolution client. No Django, no network: requests.request is faked."""

import json

import pytest
import requests

from messaging.evolution import DEFAULT_SETTINGS, EvolutionClient, EvolutionUnavailable

BASE_URL = "https://evo.test"
TOKEN = "instance-token-SECRET"
CF_ID = "cf-id.access"
CF_SECRET = "cf-secret-SECRET"


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None and self.text:
            raise ValueError("not json")
        return self._payload


class Recorder:
    """Stand-in for requests.request that records every call."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    @property
    def last(self):
        return self.calls[-1]


def client(**kwargs) -> EvolutionClient:
    params = dict(base_url=BASE_URL, instance="corpotex", token=TOKEN)
    params.update(kwargs)
    return EvolutionClient(**params)


@pytest.fixture
def record(monkeypatch):
    def install(*responses):
        recorder = Recorder(*responses)
        monkeypatch.setattr(requests, "request", recorder)
        return recorder

    return install


# -- headers and transport ---------------------------------------------------


def test_connection_state_path_and_headers_with_access_token(record):
    rec = record(FakeResponse(200, {"instance": {"instanceName": "corpotex", "state": "open"}}))

    state = client(cf_client_id=CF_ID, cf_client_secret=CF_SECRET).connection_state()

    assert state == "open"
    assert rec.last["method"] == "GET"
    assert rec.last["url"] == f"{BASE_URL}/instance/connectionState/corpotex"
    assert rec.last["headers"] == {
        "apikey": TOKEN,
        "CF-Access-Client-Id": CF_ID,
        "CF-Access-Client-Secret": CF_SECRET,
    }
    assert rec.last["allow_redirects"] is False
    assert rec.last["timeout"] == 20


def test_headers_without_access_token_have_only_apikey(record):
    rec = record(FakeResponse(200, {"instance": {"state": "close"}}))

    assert client().connection_state() == "close"
    assert rec.last["headers"] == {"apikey": TOKEN}
    assert "CF-Access-Client-Id" not in rec.last["headers"]
    assert "CF-Access-Client-Secret" not in rec.last["headers"]


def test_base_url_trailing_slash_is_normalised(record):
    rec = record(FakeResponse(200, {"instance": {"state": "open"}}))

    client(base_url=BASE_URL + "/").connection_state()

    assert rec.last["url"] == f"{BASE_URL}/instance/connectionState/corpotex"


def test_connection_state_unknown_when_payload_lacks_state(record):
    record(FakeResponse(200, {}))

    assert client().connection_state() == "unknown"


def test_302_maps_to_access_denied(record):
    record(FakeResponse(302, text="<html>login</html>"))

    with pytest.raises(EvolutionUnavailable) as info:
        client().connection_state()

    assert info.value.reason == "access_denied"
    assert info.value.status == 302


def test_non_2xx_maps_to_http_error(record):
    record(FakeResponse(401, {"status": 401, "error": "Unauthorized"}))

    with pytest.raises(EvolutionUnavailable) as info:
        client().find_settings()

    assert info.value.reason == "http_error"
    assert info.value.status == 401


def test_network_error_maps_to_network(record):
    record(requests.ConnectionError("boom"))

    with pytest.raises(EvolutionUnavailable) as info:
        client().connection_state()

    assert info.value.reason == "network"
    assert info.value.status is None


def test_invalid_json_maps_to_bad_json(record):
    record(FakeResponse(200, None, text="<html>not json</html>"))

    with pytest.raises(EvolutionUnavailable) as info:
        client().connection_state()

    assert info.value.reason == "bad_json"


def test_exceptions_never_contain_secrets(record):
    record(FakeResponse(302, text="login"))
    evolution = client(cf_client_id=CF_ID, cf_client_secret=CF_SECRET)

    with pytest.raises(EvolutionUnavailable) as info:
        evolution.set_webhook("https://corpotex.test/webhooks/evolution/hook-SECRET/")

    rendered = str(info.value) + repr(info.value) + repr(evolution)
    for secret in (TOKEN, CF_SECRET, "hook-SECRET"):
        assert secret not in rendered


# -- instance ----------------------------------------------------------------


def test_connect_qr_returns_data_url(record):
    rec = record(
        FakeResponse(200, {"base64": "data:image/png;base64,AAA=", "code": "x", "count": 1})
    )

    assert client().connect_qr() == "data:image/png;base64,AAA="
    assert rec.last["method"] == "GET"
    assert rec.last["url"] == f"{BASE_URL}/instance/connect/corpotex"


def test_connect_qr_returns_none_when_base64_missing(record):
    record(FakeResponse(200, {"instance": {"instanceName": "corpotex", "state": "open"}}))

    assert client().connect_qr() is None


# -- webhook -----------------------------------------------------------------


def test_find_webhook_none_when_unset(record):
    rec = record(FakeResponse(200, None))

    assert client().find_webhook() is None
    assert rec.last["url"] == f"{BASE_URL}/webhook/find/corpotex"


def test_find_webhook_returns_config(record):
    config = {"id": "1", "url": "https://x/h/s/", "enabled": True, "events": ["MESSAGES_UPSERT"]}
    record(FakeResponse(200, config))

    assert client().find_webhook() == config


def test_set_webhook_posts_flat_keys(record):
    rec = record(FakeResponse(201, {"webhook": {"url": "https://x/h/s/"}}))

    client().set_webhook("https://x/h/s/")

    assert rec.last["method"] == "POST"
    assert rec.last["url"] == f"{BASE_URL}/webhook/set/corpotex"
    assert rec.last["json"] == {
        "webhook": {
            "enabled": True,
            "url": "https://x/h/s/",
            "byEvents": False,
            "base64": True,
            "events": ["MESSAGES_UPSERT"],
        }
    }
    assert "webhookByEvents" not in json.dumps(rec.last["json"])


def test_set_webhook_accepts_events_and_base64(record):
    rec = record(FakeResponse(201, {}))

    client().set_webhook(
        "https://x/h/s/", events=["MESSAGES_UPSERT", "CONNECTION_UPDATE"], base64=False
    )

    assert rec.last["json"]["webhook"]["events"] == ["MESSAGES_UPSERT", "CONNECTION_UPDATE"]
    assert rec.last["json"]["webhook"]["base64"] is False


# -- settings ----------------------------------------------------------------


def test_find_settings_path(record):
    rec = record(FakeResponse(200, {"groupsIgnore": True}))

    assert client().find_settings() == {"groupsIgnore": True}
    assert rec.last["method"] == "GET"
    assert rec.last["url"] == f"{BASE_URL}/settings/find/corpotex"


def test_set_settings_posts_adr_defaults(record):
    rec = record(FakeResponse(201, {}))

    client().set_settings()

    assert rec.last["method"] == "POST"
    assert rec.last["url"] == f"{BASE_URL}/settings/set/corpotex"
    assert rec.last["json"] == {
        "rejectCall": False,
        "msgCall": "",
        "groupsIgnore": True,
        "alwaysOnline": False,
        "readMessages": False,
        "readStatus": False,
        "syncFullHistory": False,
    }
    assert rec.last["json"] == DEFAULT_SETTINGS


def test_set_settings_overrides_single_keys(record):
    rec = record(FakeResponse(201, {}))

    client().set_settings(alwaysOnline=True)

    assert rec.last["json"]["alwaysOnline"] is True
    assert rec.last["json"]["groupsIgnore"] is True


# -- messages ----------------------------------------------------------------


def test_send_text_posts_number_and_text(record):
    rec = record(FakeResponse(201, {"key": {"id": "ABC"}}))

    assert client().send_text("51906746241", "hola") == {"key": {"id": "ABC"}}
    assert rec.last["method"] == "POST"
    assert rec.last["url"] == f"{BASE_URL}/message/sendText/corpotex"
    assert rec.last["json"] == {"number": "51906746241", "text": "hola"}


# -- construction ------------------------------------------------------------


def test_from_env_reads_documented_variables(record):
    rec = record(FakeResponse(200, {"instance": {"state": "open"}}))
    env = {
        "EVOLUTION_API_URL": "https://evolution.example/",
        "EVOLUTION_INSTANCE": "corpotex",
        "EVOLUTION_INSTANCE_TOKEN": TOKEN,
        "EVOLUTION_WEBHOOK_SECRET": "hook",
        "CF_ACCESS_CLIENT_ID": CF_ID,
        "CF_ACCESS_CLIENT_SECRET": CF_SECRET,
    }

    evolution = EvolutionClient.from_env(env)
    evolution.connection_state()

    assert evolution.has_access_token is True
    assert rec.last["url"] == "https://evolution.example/instance/connectionState/corpotex"
    assert rec.last["headers"]["CF-Access-Client-Id"] == CF_ID


def test_from_env_without_access_token():
    evolution = EvolutionClient.from_env(
        {"EVOLUTION_INSTANCE_TOKEN": TOKEN, "CF_ACCESS_CLIENT_ID": ""}
    )

    assert evolution.has_access_token is False
    assert evolution.instance == "corpotex"


def test_refuses_personal_whatsapp_instance():
    with pytest.raises(ValueError):
        client(instance="personal-whatsapp")


def test_client_has_no_destructive_methods():
    names = {name.lower() for name in dir(EvolutionClient)}
    for word in ("logout", "delete", "create", "restart"):
        assert not any(word in name for name in names), f"found a method containing {word!r}"
