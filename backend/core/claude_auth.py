"""Claude account connection for the whole installation (ADR 0022).

Port of mano's ``system/auth_providers/anthropic.py``, framework-free: every
function takes the ``CLAUDE_CONFIG_DIR`` path explicitly so Django views and
the Celery worker can share it without importing anything from here but the
functions.

Two credential types live in ``config_dir``, mutually exclusive (writing one
deletes the other, so the CLI's precedence order never arbitrates):

- Subscription OAuth -> ``.credentials.json``. The CLI refreshes the access
  token itself; we write the credential once, including ``scopes`` and
  ``clientId``, which its refresh path consumes.
- API key -> ``anthropic_api_key`` plus an ``apiKeyHelper`` entry in
  ``settings.json`` pointing at ``anthropic-key-helper`` (a shell script that
  prints the key). With ``setting_sources=[]`` the CLI ignores
  ``settings.json``, so the agent passes ``helper_settings()`` through the
  SDK's ``settings=`` option instead.

A configured ``apiKeyHelper`` pointing at an empty key file hard-fails every
request, so ``_reconcile_api_key_helper`` is the sole writer of that setting
and keeps it present if and only if the key file has content.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import logging
import os
import re
import secrets
import tempfile
import time
import urllib.parse
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# --- Public Claude Code OAuth values, copied from mano. --------------------
# They are the ones the Claude Code CLI itself uses for `claude login`; this is
# the single place to edit if Anthropic rotates them (ADR 0022).
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
AUTHORIZE_URL = "https://claude.ai/oauth/authorize"
TOKEN_URL = "https://claude.ai/v1/oauth/token"
REDIRECT_URI = "https://console.anthropic.com/oauth/code/callback"
SCOPES = "org:create_api_key user:profile user:inference"
# ---------------------------------------------------------------------------

API_BASE_URL = "https://api.anthropic.com"
PROFILE_URL = f"{API_BASE_URL}/api/oauth/profile"
MODELS_URL = f"{API_BASE_URL}/v1/models"

CREDENTIALS_FILE = ".credentials.json"
KEY_FILE = "anthropic_api_key"
SETTINGS_FILE = "settings.json"
HELPER_FILE = "anthropic-key-helper"

TOKEN_TIMEOUT = 30
PROFILE_TIMEOUT = 5
KEY_PROBE_TIMEOUT = 10
USER_AGENT = "claude-cli/1.0 (external, cli)"

API_KEY_RE = re.compile(r"^sk-ant-[A-Za-z0-9_-]{20,200}$")
# The CLI maps organization_type onto max/pro/team/enterprise by stripping the
# "claude_" prefix; only a short slug is ever surfaced to the UI.
_TIER_RE = re.compile(r"^[a-z0-9_]{1,32}$")

# Resolves the key file relative to its own location, so the same volume works
# from any mount path (web writes it, the worker runs it).
_HELPER_SCRIPT = (
    "#!/bin/sh\n"
    "# Prints the stored Anthropic API key for Claude Code's apiKeyHelper.\n"
    f'exec cat "$(dirname "$0")/{KEY_FILE}"\n'
)


class ClaudeAuthError(Exception):
    """A failure the view maps onto ``{error_code, detail}`` with ``status``.

    ``code`` is one of: missing_state, invalid_code, unreachable, key_format,
    key_rejected, key_unverifiable, not_connected, write_failed.
    """

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


# -- Paths ------------------------------------------------------------------


def _creds_file(config_dir: Path) -> Path:
    return Path(config_dir) / CREDENTIALS_FILE


def _key_file(config_dir: Path) -> Path:
    return Path(config_dir) / KEY_FILE


def _settings_file(config_dir: Path) -> Path:
    return Path(config_dir) / SETTINGS_FILE


def _helper_file(config_dir: Path) -> Path:
    return Path(config_dir) / HELPER_FILE


# -- Small helpers ----------------------------------------------------------


def _now_ms() -> int:
    return int(time.time() * 1000)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _clean_pasted(value: str | None) -> str:
    """Strip wrapping quotes and whitespace off a pasted value."""
    return value.strip().strip('"').strip("'").strip() if value else ""


def _atomic_write(path: Path, data: str, mode: int = 0o600) -> None:
    """Write a file atomically: readers see either the old bytes or the new."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.tmp.")
    try:
        os.write(fd, data.encode())
        os.fchmod(fd, mode)
        os.close(fd)
        os.replace(tmp, str(path))
    except Exception:
        with contextlib.suppress(OSError):
            os.close(fd)
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _remove(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.unlink()


def _oauth_blob(config_dir: Path) -> dict:
    """The stored OAuth grant, or {} when absent or unreadable."""
    try:
        return json.loads(_creds_file(config_dir).read_text()).get("claudeAiOauth", {})
    except (OSError, ValueError, AttributeError):
        return {}


def _key_file_value(config_dir: Path) -> str:
    """The stored API key, or "" when absent or whitespace-only."""
    try:
        return _key_file(config_dir).read_text().strip()
    except OSError:
        return ""


def _parse_subscription_type(profile: object) -> str | None:
    """Map an /api/oauth/profile body onto a tier slug, or None."""
    if not isinstance(profile, dict):
        return None
    org = profile.get("organization")
    org_type = org.get("organization_type") if isinstance(org, dict) else None
    if isinstance(org_type, str):
        tier = org_type.removeprefix("claude_").strip().lower()
        if _TIER_RE.match(tier):
            return tier
    account = profile.get("account")
    if isinstance(account, dict):
        if account.get("has_claude_max"):
            return "max"
        if account.get("has_claude_pro"):
            return "pro"
    logger.info("Unrecognized profile shape; keys=%s", sorted(profile.keys()))
    return None


# -- apiKeyHelper reconcile -------------------------------------------------


def _reconcile_api_key_helper(config_dir: Path) -> bool:
    """Keep the helper script and the settings entry iff the key file has content.

    Sole writer of ``apiKeyHelper``, idempotent, preserves unrelated settings.
    Returns True when the helper ends up configured.
    """
    key_present = bool(_key_file_value(config_dir))
    helper = _helper_file(config_dir)
    if key_present and not helper.is_file():
        _atomic_write(helper, _HELPER_SCRIPT, mode=0o700)
    elif not key_present:
        _remove(helper)

    settings_file = _settings_file(config_dir)
    settings: dict = {}
    corrupt = False
    if settings_file.is_file():
        try:
            settings = json.loads(settings_file.read_text())
        except (OSError, ValueError):
            logger.warning("settings.json was corrupt or unreadable; rebuilding it")
            settings, corrupt = {}, True

    before = settings.get("apiKeyHelper")
    if key_present:
        settings["apiKeyHelper"] = str(helper)
    else:
        settings.pop("apiKeyHelper", None)
    if corrupt or settings.get("apiKeyHelper") != before:
        _atomic_write(settings_file, json.dumps(settings, indent=2) + "\n")
    return key_present


# -- OAuth ------------------------------------------------------------------


def start() -> dict:
    """Build the claude.ai authorize URL (PKCE S256).

    The state IS the verifier: the callback page shows the user
    ``<code>#<state>``, so the server keeps nothing between the two steps.
    """
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    params = {
        "code": "true",
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": verifier,
    }
    return {"url": AUTHORIZE_URL + "?" + urllib.parse.urlencode(params), "state": verifier}


def _split_pasted_code(code_input: str) -> tuple[str, str]:
    code_input = _clean_pasted(code_input)
    code, _, state = code_input.partition("#")
    code, state = _clean_pasted(code), _clean_pasted(state)
    if not code:
        raise ClaudeAuthError("invalid_code", "Pega el código que muestra la página de Anthropic.")
    if not state:
        raise ClaudeAuthError(
            "missing_state",
            "Falta la parte después de '#'. Pega el código completo, tal como lo "
            "muestra la página de Anthropic.",
        )
    return code, state


def _request_token(code: str, state: str) -> dict:
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "code_verifier": state,
        "state": state,
    }
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    try:
        resp = requests.post(TOKEN_URL, json=body, headers=headers, timeout=TOKEN_TIMEOUT)
    except requests.RequestException as e:
        raise ClaudeAuthError(
            "unreachable", f"No se pudo contactar a claude.ai: {e}", status=502
        ) from e
    if resp.status_code != 200:
        raise ClaudeAuthError(
            "invalid_code",
            f"claude.ai rechazó el código (HTTP {resp.status_code}): {resp.text[:200]}",
        )
    try:
        data = resp.json()
    except ValueError as e:
        raise ClaudeAuthError("invalid_code", "La respuesta de claude.ai no es JSON.") from e
    if not isinstance(data, dict) or not data.get("access_token"):
        raise ClaudeAuthError("invalid_code", "La respuesta de claude.ai no trae access_token.")
    return data


def _fetch_subscription_type(access_token: str) -> str | None:
    """The Claude plan tier, or None. Best-effort: never fails a connect."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
    }
    try:
        resp = requests.get(PROFILE_URL, headers=headers, timeout=PROFILE_TIMEOUT)
        if resp.status_code != 200:
            logger.info("Profile fetch returned %s; plan will be omitted", resp.status_code)
            return None
        data = resp.json()
    except Exception as e:  # noqa: BLE001 - cosmetic, any failure just omits the plan
        logger.info("Profile fetch failed (%s); plan will be omitted", e)
        return None
    return _parse_subscription_type(data)


def _write_credentials(config_dir: Path, creds: dict) -> None:
    """Write ``.credentials.json`` atomically (0600) and verify by re-reading."""
    path = _creds_file(config_dir)
    try:
        _atomic_write(path, json.dumps(creds))
        written = json.loads(path.read_text())
        if not written["claudeAiOauth"]["accessToken"]:
            raise ValueError("accessToken is empty after write")
    except Exception as e:  # noqa: BLE001 - any failure here means "not connected"
        raise ClaudeAuthError(
            "write_failed", f"No se pudo guardar la credencial: {e}", status=500
        ) from e


def exchange(code_input: str, config_dir: Path) -> dict:
    """Trade the pasted ``<code>#<state>`` for a credential file.

    Writes ``<config_dir>/.credentials.json`` in the exact shape the CLI
    writes on ``claude login`` and removes any API key (mutual exclusion).
    """
    code, state = _split_pasted_code(code_input)
    data = _request_token(code, state)

    # Stamp the issue time BEFORE the profile fetch: expires_in is relative to
    # when the server minted the token.
    now_ms = _now_ms()
    subscription_type = _fetch_subscription_type(data["access_token"])

    expires_at = now_ms + int(data.get("expires_in", 0)) * 1000
    rt_expires_in = data.get("refresh_token_expires_in")
    refresh_expires_at = now_ms + int(rt_expires_in) * 1000 if rt_expires_in else None
    # scopes is load-bearing: the CLI rebuilds its refresh request from it.
    scopes = (data.get("scope") or SCOPES).split()
    creds = {
        "claudeAiOauth": {
            "accessToken": data["access_token"],
            "refreshToken": data.get("refresh_token"),
            "expiresAt": expires_at,
            "refreshTokenExpiresAt": refresh_expires_at,
            "scopes": scopes,
            "subscriptionType": subscription_type,
            "clientId": CLIENT_ID,
        }
    }
    _write_credentials(config_dir, creds)

    _remove(_key_file(config_dir))
    _reconcile_api_key_helper(config_dir)
    return {
        "expires_at": expires_at,
        "refresh_token_expires_at": refresh_expires_at,
        "subscription_type": subscription_type,
    }


# -- API key ----------------------------------------------------------------


def _verify_api_key(api_key: str) -> None:
    """GET /v1/models with the key: authenticated, bills no tokens."""
    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
    try:
        resp = requests.get(MODELS_URL, headers=headers, timeout=KEY_PROBE_TIMEOUT)
    except requests.RequestException as e:
        raise ClaudeAuthError(
            "key_unverifiable", f"No se pudo verificar la API key: {e}", status=502
        ) from e
    if resp.status_code in (401, 403):
        raise ClaudeAuthError("key_rejected", "Anthropic rechazó la API key.")
    if resp.status_code != 200:
        raise ClaudeAuthError(
            "key_unverifiable",
            f"No se pudo verificar la API key (HTTP {resp.status_code}).",
            status=502,
        )


def set_api_key(config_dir: Path, api_key: str) -> dict:
    """Validate and install an API key; removes any OAuth credential."""
    api_key = _clean_pasted(api_key)
    if not API_KEY_RE.match(api_key):
        raise ClaudeAuthError(
            "key_format", "La API key no tiene el formato esperado (empieza con sk-ant-)."
        )
    # Validate live BEFORE destroying anything: under mutual exclusion a typo
    # would otherwise cost a working subscription.
    _verify_api_key(api_key)
    try:
        _atomic_write(_key_file(config_dir), api_key + "\n")
        _reconcile_api_key_helper(config_dir)
    except OSError as e:
        raise ClaudeAuthError(
            "write_failed", f"No se pudo guardar la API key: {e}", status=500
        ) from e
    _remove(_creds_file(config_dir))
    return {"method": "api_key"}


# -- Disconnect / status ----------------------------------------------------


def disconnect(config_dir: Path) -> None:
    """Remove whichever credential is stored and the helper entry.

    Raises ``not_connected`` when there was nothing to remove (after still
    healing a stale helper entry).
    """
    shape = credential_shape(config_dir)
    _remove(_creds_file(config_dir))
    _remove(_key_file(config_dir))
    _reconcile_api_key_helper(config_dir)
    if shape == "none":
        raise ClaudeAuthError("not_connected", "No hay ninguna cuenta de Claude conectada.")


def credential_shape(config_dir: Path) -> str:
    """Which credential is stored: ``api_key`` (shadows OAuth), ``oauth`` or ``none``."""
    if _key_file_value(config_dir):
        return "api_key"
    if _creds_file(config_dir).is_file():
        return "oauth"
    return "none"


def status(config_dir: Path) -> dict:
    """What the dashboard shows. Timestamps are epoch milliseconds, as the CLI stores them.

    ``expired`` only once the REFRESH token lapsed: the CLI refreshes an expired
    access token itself on the next spawn.
    """
    key_active = bool(_key_file_value(config_dir))
    oauth = _oauth_blob(config_dir)
    logged_in = bool(oauth.get("accessToken"))
    expires_at = oauth.get("expiresAt")
    refresh_expires_at = oauth.get("refreshTokenExpiresAt")
    deadline = refresh_expires_at or expires_at
    expired = bool(deadline) and _now_ms() > int(deadline)

    connected = key_active or (logged_in and not expired)
    if key_active:
        method = "api_key"
    elif connected:
        method = "oauth"
    else:
        method = "none"
    return {
        "connected": connected,
        "method": method,
        # An API key is a Console credential with no claude.ai plan attached.
        "subscription_type": oauth.get("subscriptionType") if method == "oauth" else None,
        "expires_at": expires_at,
        "refresh_token_expires_at": refresh_expires_at,
        "expired": expired,
    }


def helper_settings(config_dir: Path) -> dict | None:
    """The ``settings=`` dict the Agent SDK needs in API key mode, else None.

    With ``setting_sources=[]`` the CLI ignores ``settings.json``, so the agent
    passes the helper through the SDK (ADR 0022). The path is resolved from
    the caller's ``config_dir``, so it is right for whichever container runs
    the CLI.
    """
    if credential_shape(config_dir) != "api_key":
        return None
    return {"apiKeyHelper": str(_helper_file(config_dir))}
