"""Minimal client for the Evolution API v2 instance that runs the bot.

Evolution sits behind Cloudflare Access (ADR 0006), so every request carries the
instance token (``apikey``) plus the Access service token headers when they are
configured. Without them Cloudflare answers with a 302 to its login page.

By design this class has no method to create, log out or delete an instance
(ADR 0011): re-linking would require a QR from Oscar's phone. It also refuses
to be pointed at ``personal-whatsapp``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import requests

# Settings applied by step 1 of the onboarding (ADR 0011): ignore groups; do not
# reject calls, do not mark messages as read and do not sync the full history.
DEFAULT_SETTINGS: dict[str, Any] = {
    "rejectCall": False,
    "msgCall": "",
    "groupsIgnore": True,
    "alwaysOnline": False,
    "readMessages": False,
    "readStatus": False,
    "syncFullHistory": False,
}

# Instances the backend must never touch (CLAUDE.md, ADR 0010).
PROTECTED_INSTANCES = frozenset({"personal-whatsapp"})

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


class EvolutionUnavailable(Exception):
    """Evolution could not be reached or did not answer 2xx.

    ``reason`` is a short tag: ``network``, ``access_denied`` (Cloudflare Access
    redirected us, i.e. the service token is missing or wrong), ``http_error``
    or ``bad_json``. ``status`` is the HTTP status, ``None`` on network errors.
    The message never includes the token, the Access secret or request bodies.
    """

    def __init__(self, reason: str, *, status: int | None = None, where: str = "") -> None:
        self.reason = reason
        self.status = status
        message = f"Evolution unavailable ({reason})"
        if status is not None:
            message += f" status={status}"
        if where:
            message += f" on {where}"
        super().__init__(message)


class EvolutionClient:
    """Thin wrapper over the handful of Evolution endpoints the backend uses."""

    def __init__(
        self,
        base_url: str,
        instance: str,
        token: str,
        cf_client_id: str | None = None,
        cf_client_secret: str | None = None,
        timeout: float = 20,
    ) -> None:
        if instance in PROTECTED_INSTANCES:
            raise ValueError(f"instance {instance!r} must not be used by the backend")
        self.base_url = base_url.rstrip("/")
        self.instance = instance
        self.timeout = timeout
        self._token = token
        self._cf_client_id = cf_client_id or None
        self._cf_client_secret = cf_client_secret or None

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> EvolutionClient:
        """Build a client from the variable names documented in ``.env.example``."""
        return cls(
            base_url=env.get("EVOLUTION_API_URL") or "https://evolution.oscargicast.com",
            instance=env.get("EVOLUTION_INSTANCE") or "corpotex",
            token=env.get("EVOLUTION_INSTANCE_TOKEN") or "",
            cf_client_id=env.get("CF_ACCESS_CLIENT_ID"),
            cf_client_secret=env.get("CF_ACCESS_CLIENT_SECRET"),
        )

    @property
    def has_access_token(self) -> bool:
        """True when both Cloudflare Access service token parts are configured."""
        return bool(self._cf_client_id and self._cf_client_secret)

    def __repr__(self) -> str:  # never show the secrets
        return f"EvolutionClient(base_url={self.base_url!r}, instance={self.instance!r})"

    # -- transport -------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {"apikey": self._token}
        if self.has_access_token:
            headers["CF-Access-Client-Id"] = self._cf_client_id  # type: ignore[assignment]
            headers["CF-Access-Client-Secret"] = self._cf_client_secret  # type: ignore[assignment]
        return headers

    def _request(self, method: str, path: str, json: Any = None) -> Any:
        where = f"{method} {path}"
        try:
            # Redirects are not followed on purpose: a 302 is how Cloudflare
            # Access tells us the service token was rejected.
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                headers=self._headers(),
                json=json,
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise EvolutionUnavailable("network", where=f"{where} ({type(exc).__name__})") from None
        if response.status_code in _REDIRECT_STATUSES:
            raise EvolutionUnavailable("access_denied", status=response.status_code, where=where)
        if not 200 <= response.status_code < 300:
            raise EvolutionUnavailable("http_error", status=response.status_code, where=where)
        try:
            return response.json()
        except ValueError:
            raise EvolutionUnavailable(
                "bad_json", status=response.status_code, where=where
            ) from None

    # -- instance --------------------------------------------------------------

    def connection_state(self) -> str:
        """``open`` (linked), ``connecting`` or ``close``; ``unknown`` if absent."""
        data = self._request("GET", f"/instance/connectionState/{self.instance}")
        instance = data.get("instance") if isinstance(data, dict) else None
        state = instance.get("state") if isinstance(instance, dict) else None
        return state or "unknown"

    def connect_qr(self) -> str | None:
        """The QR as a ``data:image/png;base64,...`` URL, or None when already linked."""
        data = self._request("GET", f"/instance/connect/{self.instance}")
        if not isinstance(data, dict):
            return None
        return data.get("base64") or None

    # -- webhook ---------------------------------------------------------------

    def find_webhook(self) -> dict | None:
        """The webhook config, or None when the instance has none (Evolution returns null)."""
        data = self._request("GET", f"/webhook/find/{self.instance}")
        return data if isinstance(data, dict) else None

    def set_webhook(
        self,
        url: str,
        events: tuple[str, ...] | list[str] = ("MESSAGES_UPSERT",),
        base64: bool = True,
    ) -> dict:
        # Evolution v2 only honours the flat ``byEvents``/``base64`` keys on write;
        # ``webhookByEvents``/``webhookBase64`` (the names it reads back) are ignored.
        body = {
            "webhook": {
                "enabled": True,
                "url": url,
                "byEvents": False,
                "base64": base64,
                "events": list(events),
            }
        }
        return self._request("POST", f"/webhook/set/{self.instance}", json=body)

    # -- settings --------------------------------------------------------------

    def find_settings(self) -> dict:
        data = self._request("GET", f"/settings/find/{self.instance}")
        return data if isinstance(data, dict) else {}

    def set_settings(self, **overrides: Any) -> dict:
        """Apply the ADR 0011 settings; keyword arguments override single keys."""
        body = {**DEFAULT_SETTINGS, **overrides}
        return self._request("POST", f"/settings/set/{self.instance}", json=body)

    # -- messages (B3.6; kept minimal so the backend session can extend it) ----

    def send_text(self, phone: str, text: str) -> dict:
        body = {"number": phone, "text": text}
        return self._request("POST", f"/message/sendText/{self.instance}", json=body)
