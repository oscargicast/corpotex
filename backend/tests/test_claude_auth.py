"""Tests for core.claude_auth. No network: requests.post/get are monkeypatched."""

import base64
import hashlib
import json
import stat
import time
import urllib.parse

import pytest
import requests

from core import claude_auth

VALID_KEY = "sk-ant-api03-" + "a" * 40
PASTED_CODE = "the-auth-code#the-state-verifier"


class FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (json.dumps(payload) if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


def token_payload(**overrides):
    payload = {
        "access_token": "access-123",
        "refresh_token": "refresh-456",
        "expires_in": 3600,
        "refresh_token_expires_in": 86400 * 30,
        "scope": "user:inference user:profile",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def config_dir(tmp_path):
    return tmp_path / ".claude"


@pytest.fixture
def calls(monkeypatch):
    """Mock claude.ai and api.anthropic.com; records every call made."""
    recorded = {"post": [], "get": []}
    responses = {
        "post": FakeResponse(200, token_payload()),
        "get": FakeResponse(200, {"organization": {"organization_type": "claude_max"}}),
    }

    def fake_post(url, **kwargs):
        recorded["post"].append((url, kwargs))
        result = responses["post"]
        if isinstance(result, Exception):
            raise result
        return result

    def fake_get(url, **kwargs):
        recorded["get"].append((url, kwargs))
        result = responses["get"]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(requests, "get", fake_get)
    recorded["responses"] = responses
    return recorded


def file_mode(path):
    return stat.S_IMODE(path.stat().st_mode)


# -- start --------------------------------------------------------------------


def test_start_returns_pkce_authorize_url():
    result = claude_auth.start()

    assert result["url"].startswith(claude_auth.AUTHORIZE_URL + "?")
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(result["url"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["client_id"] == [claude_auth.CLIENT_ID]
    assert query["redirect_uri"] == [claude_auth.REDIRECT_URI]
    assert query["scope"] == [claude_auth.SCOPES]
    assert query["state"] == [result["state"]]
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(result["state"].encode()).digest())
        .decode()
        .rstrip("=")
    )
    assert query["code_challenge"] == [expected]


def test_start_generates_a_fresh_verifier_each_time():
    assert claude_auth.start()["state"] != claude_auth.start()["state"]


# -- exchange -----------------------------------------------------------------


def test_exchange_writes_credentials_0600(config_dir, calls):
    before_ms = int(time.time() * 1000)
    result = claude_auth.exchange(PASTED_CODE, config_dir)

    creds_file = config_dir / ".credentials.json"
    assert file_mode(creds_file) == 0o600
    oauth = json.loads(creds_file.read_text())["claudeAiOauth"]
    assert oauth["accessToken"] == "access-123"
    assert oauth["refreshToken"] == "refresh-456"
    assert oauth["scopes"] == ["user:inference", "user:profile"]
    assert oauth["subscriptionType"] == "max"
    assert oauth["clientId"] == claude_auth.CLIENT_ID
    assert abs(oauth["expiresAt"] - (before_ms + 3600 * 1000)) < 5000
    assert abs(oauth["refreshTokenExpiresAt"] - (before_ms + 86400 * 30 * 1000)) < 5000

    assert result == {
        "expires_at": oauth["expiresAt"],
        "refresh_token_expires_at": oauth["refreshTokenExpiresAt"],
        "subscription_type": "max",
    }
    assert claude_auth.credential_shape(config_dir) == "oauth"


def test_exchange_posts_code_and_verifier_like_the_cli(calls, config_dir):
    claude_auth.exchange("  'the-auth-code#the-state-verifier'  ", config_dir)

    url, kwargs = calls["post"][0]
    assert url == claude_auth.TOKEN_URL
    assert kwargs["json"]["grant_type"] == "authorization_code"
    assert kwargs["json"]["code"] == "the-auth-code"
    assert kwargs["json"]["code_verifier"] == "the-state-verifier"
    assert kwargs["json"]["state"] == "the-state-verifier"
    assert kwargs["json"]["client_id"] == claude_auth.CLIENT_ID
    assert kwargs["json"]["redirect_uri"] == claude_auth.REDIRECT_URI
    assert kwargs["headers"]["User-Agent"] == "claude-cli/1.0 (external, cli)"
    assert kwargs["timeout"] == 30

    profile_url, profile_kwargs = calls["get"][0]
    assert profile_url == claude_auth.PROFILE_URL
    assert profile_kwargs["headers"]["Authorization"] == "Bearer access-123"


def test_exchange_without_hash_returns_missing_state(config_dir, calls):
    with pytest.raises(claude_auth.ClaudeAuthError) as exc:
        claude_auth.exchange("just-a-code", config_dir)

    assert exc.value.code == "missing_state"
    assert exc.value.status == 400
    assert calls["post"] == []
    assert not (config_dir / ".credentials.json").exists()


def test_exchange_non_200_is_invalid_code(config_dir, calls):
    calls["responses"]["post"] = FakeResponse(400, text='{"error":"invalid_grant"}')

    with pytest.raises(claude_auth.ClaudeAuthError) as exc:
        claude_auth.exchange(PASTED_CODE, config_dir)

    assert exc.value.code == "invalid_code"
    assert exc.value.status == 400
    assert not (config_dir / ".credentials.json").exists()


def test_exchange_connection_error_is_unreachable(config_dir, calls):
    calls["responses"]["post"] = requests.ConnectionError("dns failed")

    with pytest.raises(claude_auth.ClaudeAuthError) as exc:
        claude_auth.exchange(PASTED_CODE, config_dir)

    assert exc.value.code == "unreachable"
    assert exc.value.status == 502


def test_exchange_falls_back_to_default_scopes_and_survives_profile_failure(config_dir, calls):
    calls["responses"]["post"] = FakeResponse(200, token_payload(scope=None))
    calls["responses"]["get"] = requests.Timeout("profile slow")

    result = claude_auth.exchange(PASTED_CODE, config_dir)

    oauth = json.loads((config_dir / ".credentials.json").read_text())["claudeAiOauth"]
    assert oauth["scopes"] == claude_auth.SCOPES.split()
    assert oauth["subscriptionType"] is None
    assert result["subscription_type"] is None


# -- status -------------------------------------------------------------------


def test_status_is_none_without_file(config_dir):
    assert claude_auth.status(config_dir) == {
        "connected": False,
        "method": "none",
        "subscription_type": None,
        "expires_at": None,
        "refresh_token_expires_at": None,
        "expired": False,
    }


def test_status_oauth_is_connected_until_refresh_deadline(config_dir, calls):
    claude_auth.exchange(PASTED_CODE, config_dir)

    result = claude_auth.status(config_dir)

    assert result["connected"] is True
    assert result["method"] == "oauth"
    assert result["subscription_type"] == "max"
    assert result["expired"] is False
    assert result["refresh_token_expires_at"] > result["expires_at"] > 0


def test_status_oauth_with_expired_access_token_is_still_connected(config_dir, calls):
    # The CLI refreshes the access token on the next spawn; only the refresh
    # token's deadline counts.
    calls["responses"]["post"] = FakeResponse(200, token_payload(expires_in=-10))

    claude_auth.exchange(PASTED_CODE, config_dir)

    result = claude_auth.status(config_dir)
    assert result["connected"] is True
    assert result["expired"] is False


def test_status_oauth_past_refresh_deadline_is_expired(config_dir, calls):
    calls["responses"]["post"] = FakeResponse(
        200, token_payload(expires_in=-20, refresh_token_expires_in=-10)
    )
    claude_auth.exchange(PASTED_CODE, config_dir)

    result = claude_auth.status(config_dir)

    assert result["expired"] is True
    assert result["connected"] is False
    assert result["method"] == "none"


def test_status_api_key_method(config_dir, calls):
    claude_auth.set_api_key(config_dir, VALID_KEY)

    result = claude_auth.status(config_dir)

    assert result["connected"] is True
    assert result["method"] == "api_key"
    assert result["subscription_type"] is None
    assert result["expired"] is False


def test_status_with_corrupt_credentials_file_is_none(config_dir):
    config_dir.mkdir()
    (config_dir / ".credentials.json").write_text("{not json")

    assert claude_auth.status(config_dir)["method"] == "none"


# -- set_api_key --------------------------------------------------------------


def test_set_api_key_bad_format(config_dir, calls):
    with pytest.raises(claude_auth.ClaudeAuthError) as exc:
        claude_auth.set_api_key(config_dir, "not-a-key")

    assert exc.value.code == "key_format"
    assert calls["get"] == []
    assert not (config_dir / "anthropic_api_key").exists()


def test_set_api_key_rejected_401(config_dir, calls):
    calls["responses"]["get"] = FakeResponse(401, {"error": "unauthorized"})

    with pytest.raises(claude_auth.ClaudeAuthError) as exc:
        claude_auth.set_api_key(config_dir, VALID_KEY)

    assert exc.value.code == "key_rejected"
    assert exc.value.status == 400
    assert not (config_dir / "anthropic_api_key").exists()


def test_set_api_key_network_error_is_unverifiable(config_dir, calls):
    calls["responses"]["get"] = requests.ConnectionError("offline")

    with pytest.raises(claude_auth.ClaudeAuthError) as exc:
        claude_auth.set_api_key(config_dir, VALID_KEY)

    assert exc.value.code == "key_unverifiable"
    assert exc.value.status == 502


def test_set_api_key_installs_key_and_helper(config_dir, calls):
    # Start connected by OAuth with an unrelated setting already in place.
    claude_auth.exchange(PASTED_CODE, config_dir)
    (config_dir / "settings.json").write_text(json.dumps({"theme": "dark"}))

    result = claude_auth.set_api_key(config_dir, f'  "{VALID_KEY}"  ')

    assert result == {"method": "api_key"}
    key_file = config_dir / "anthropic_api_key"
    assert key_file.read_text() == VALID_KEY + "\n"
    assert file_mode(key_file) == 0o600

    helper = config_dir / "anthropic-key-helper"
    assert file_mode(helper) == 0o700
    assert helper.read_text().startswith("#!/bin/sh")

    settings = json.loads((config_dir / "settings.json").read_text())
    assert settings == {"theme": "dark", "apiKeyHelper": str(helper)}

    assert not (config_dir / ".credentials.json").exists()
    assert claude_auth.credential_shape(config_dir) == "api_key"
    assert claude_auth.helper_settings(config_dir) == {"apiKeyHelper": str(helper)}

    url, kwargs = calls["get"][-1]
    assert url == claude_auth.MODELS_URL
    assert kwargs["headers"] == {"x-api-key": VALID_KEY, "anthropic-version": "2023-06-01"}


def test_helper_script_prints_the_key(config_dir, calls):
    import subprocess

    claude_auth.set_api_key(config_dir, VALID_KEY)

    helper = claude_auth.helper_settings(config_dir)["apiKeyHelper"]
    output = subprocess.run([helper], capture_output=True, text=True, check=True).stdout
    assert output.strip() == VALID_KEY


def test_helper_settings_is_none_in_oauth_mode(config_dir, calls):
    claude_auth.exchange(PASTED_CODE, config_dir)

    assert claude_auth.helper_settings(config_dir) is None


def test_exchange_after_set_api_key_removes_key_file(config_dir, calls):
    claude_auth.set_api_key(config_dir, VALID_KEY)

    claude_auth.exchange(PASTED_CODE, config_dir)

    assert not (config_dir / "anthropic_api_key").exists()
    assert not (config_dir / "anthropic-key-helper").exists()
    assert "apiKeyHelper" not in json.loads((config_dir / "settings.json").read_text())
    assert claude_auth.credential_shape(config_dir) == "oauth"
    assert claude_auth.status(config_dir)["method"] == "oauth"


# -- disconnect ---------------------------------------------------------------


def test_disconnect_cleans_everything(config_dir, calls):
    claude_auth.set_api_key(config_dir, VALID_KEY)

    claude_auth.disconnect(config_dir)

    assert not (config_dir / "anthropic_api_key").exists()
    assert not (config_dir / "anthropic-key-helper").exists()
    assert not (config_dir / ".credentials.json").exists()
    assert "apiKeyHelper" not in json.loads((config_dir / "settings.json").read_text())
    assert claude_auth.helper_settings(config_dir) is None
    assert claude_auth.status(config_dir)["method"] == "none"


def test_disconnect_oauth(config_dir, calls):
    claude_auth.exchange(PASTED_CODE, config_dir)

    claude_auth.disconnect(config_dir)

    assert not (config_dir / ".credentials.json").exists()
    assert claude_auth.status(config_dir)["connected"] is False


def test_disconnect_without_credential_raises_not_connected(config_dir):
    with pytest.raises(claude_auth.ClaudeAuthError) as exc:
        claude_auth.disconnect(config_dir)

    assert exc.value.code == "not_connected"
