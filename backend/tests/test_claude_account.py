"""Claude account from the dashboard (B4.3): views, Config state and the queue pause."""

import json
import stat
from types import SimpleNamespace

import pytest
from django.utils import timezone

from core import claude_account, claude_auth
from core.models import Config, User
from manager.models import Alert
from messaging.models import Conversation, Turn

pytestmark = pytest.mark.django_db

TOKEN_RESPONSE = {
    "access_token": "sk-ant-oat01-test",
    "refresh_token": "sk-ant-ort01-test",
    "expires_in": 3600,
    "refresh_token_expires_in": 86400,
    "scope": "user:inference user:profile",
}


@pytest.fixture
def claude_dir(settings, tmp_path):
    settings.CLAUDE_CONFIG_DIR = str(tmp_path)
    return tmp_path


@pytest.fixture
def oauth_ok(monkeypatch):
    monkeypatch.setattr(claude_auth, "_request_token", lambda code, state: dict(TOKEN_RESPONSE))
    monkeypatch.setattr(claude_auth, "_fetch_subscription_type", lambda token: "max")


@pytest.fixture
def dispatched(monkeypatch):
    calls: list[list[int]] = []
    monkeypatch.setattr(claude_account, "_dispatch_pending", calls.append)
    return calls


def _conversation() -> Conversation:
    # A dashboard conversation needs a user (`conversation_owner_matches_channel`).
    user = User.objects.create_user(username=f"user-{Conversation.objects.count() + 1}")
    return Conversation.objects.create(channel=Conversation.Channel.DASHBOARD, user=user)


def _turn(status: str, attempts: int = 0, conversation: Conversation | None = None) -> Turn:
    conversation = conversation or _conversation()
    return Turn.objects.create(
        conversation=conversation,
        reason=Turn.Reason.MESSAGE,
        status=status,
        attempts=attempts,
        available_at=timezone.now(),
    )


# -- Views -------------------------------------------------------------------


def test_status_is_manager_only(claude_dir, sales_client, anonymous_client):
    assert sales_client.get("/api/settings/claude/").status_code == 403
    assert anonymous_client.get("/api/settings/claude/").status_code == 401


def test_status_without_credential(claude_dir, manager_client):
    response = manager_client.get("/api/settings/claude/")
    assert response.status_code == 200
    assert response.json() == {
        "connected": False,
        "method": "none",
        "subscription_type": None,
        "expires_at": None,
        "refresh_token_expires_at": None,
        "expired": False,
        "connected_at": None,
        "last_error": None,
        "last_error_at": None,
    }


def test_start_returns_authorize_url_with_pkce(claude_dir, manager_client):
    data = manager_client.post("/api/settings/claude/start/").json()
    assert data["url"].startswith(claude_auth.AUTHORIZE_URL + "?")
    assert "code_challenge_method=S256" in data["url"]
    assert data["state"] and f"state={data['state']}" in data["url"]


def test_exchange_without_hash_returns_missing_state(claude_dir, manager_client):
    response = manager_client.post("/api/settings/claude/exchange/", {"code": "abc"})
    assert response.status_code == 400
    assert response.json()["error_code"] == "missing_state"


def test_exchange_writes_credentials_0600_and_marks_connected(
    claude_dir, manager_client, oauth_ok, dispatched, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = manager_client.post("/api/settings/claude/exchange/", {"code": "abc#verifier"})
    assert response.status_code == 200, response.content
    data = response.json()
    assert data["connected"] is True
    assert data["method"] == "oauth"
    assert data["subscription_type"] == "max"
    assert data["connected_at"] is not None
    assert data["last_error"] is None

    creds = claude_dir / claude_auth.CREDENTIALS_FILE
    assert stat.S_IMODE(creds.stat().st_mode) == 0o600
    blob = json.loads(creds.read_text())["claudeAiOauth"]
    assert blob["accessToken"] == TOKEN_RESPONSE["access_token"]
    assert blob["clientId"] == claude_auth.CLIENT_ID
    assert Config.load().claude_connected_at is not None
    assert dispatched == [[]]  # nothing pending, still re-dispatched once


def test_set_key_rejected_by_anthropic(claude_dir, manager_client, monkeypatch):
    def reject(api_key):
        raise claude_auth.ClaudeAuthError("key_rejected", "Anthropic rechazó la API key.")

    monkeypatch.setattr(claude_auth, "_verify_api_key", reject)
    response = manager_client.post(
        "/api/settings/claude/set-key/", {"api_key": "sk-ant-api03-" + "x" * 30}
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "key_rejected"
    assert claude_auth.credential_shape(claude_dir) == "none"


def test_disconnect_pauses_queue_and_opens_alert(
    claude_dir, manager_client, oauth_ok, dispatched, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        manager_client.post("/api/settings/claude/exchange/", {"code": "abc#verifier"})
    response = manager_client.post("/api/settings/claude/disconnect/")
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is False
    assert data["connected_at"] is None
    assert data["last_error"] == claude_account.DISCONNECTED_BY_MANAGER
    assert not (claude_dir / claude_auth.CREDENTIALS_FILE).exists()
    assert (
        Alert.objects.filter(kind=Alert.Kind.CLAUDE_DISCONNECTED, status=Alert.Status.OPEN).count()
        == 1
    )

    again = manager_client.post("/api/settings/claude/disconnect/")
    assert again.status_code == 400
    assert again.json()["error_code"] == "not_connected"


# -- Queue pause / resume ----------------------------------------------------


def test_mark_disconnected_requeues_turn_without_attempt(claude_dir):
    turn = _turn(Turn.Status.RUNNING, attempts=2)
    claude_account.mark_claude_disconnected(
        "OAuth session expired", batch=SimpleNamespace(turn=turn)
    )
    turn.refresh_from_db()
    assert turn.status == Turn.Status.PENDING
    assert turn.attempts == 2
    assert turn.available_at <= timezone.now()
    config = Config.load()
    assert config.claude_last_error == "OAuth session expired"
    assert config.claude_last_error_at is not None


def test_mark_disconnected_twice_keeps_one_open_alert(claude_dir):
    claude_account.mark_claude_disconnected("first")
    claude_account.mark_claude_disconnected("second")
    assert Alert.objects.filter(kind=Alert.Kind.CLAUDE_DISCONNECTED).count() == 1
    assert Config.load().claude_last_error == "second"


def test_mark_disconnected_with_newer_pending_ends_running_turn_as_error(claude_dir):
    running = _turn(Turn.Status.RUNNING, attempts=1)
    pending = _turn(Turn.Status.PENDING, conversation=running.conversation)
    claude_account.mark_claude_disconnected("expired", batch=SimpleNamespace(turn=running))
    running.refresh_from_db()
    pending.refresh_from_db()
    assert running.status == Turn.Status.ERROR
    assert running.attempts == 1
    assert pending.status == Turn.Status.PENDING


def test_mark_connected_resolves_alert_and_redispatches_pending(
    claude_dir, dispatched, django_capture_on_commit_callbacks
):
    claude_account.mark_claude_disconnected("expired")
    first = _turn(Turn.Status.PENDING)
    _turn(Turn.Status.PENDING)
    _turn(Turn.Status.DONE, conversation=first.conversation)

    with django_capture_on_commit_callbacks(execute=True):
        claude_account.mark_claude_connected()

    config = Config.load()
    assert config.claude_last_error == ""
    assert config.claude_last_error_at is None
    assert config.claude_connected_at is not None
    alert = Alert.objects.get(kind=Alert.Kind.CLAUDE_DISCONNECTED)
    assert alert.status == Alert.Status.RESOLVED
    assert alert.resolved_at is not None
    assert len(dispatched) == 1
    assert sorted(dispatched[0]) == sorted(
        Turn.objects.filter(status=Turn.Status.PENDING).values_list("conversation_id", flat=True)
    )
    assert len(dispatched[0]) == 2
