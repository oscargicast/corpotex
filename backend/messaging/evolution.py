"""Minimal client for the Evolution API v2 instance that runs the bot.

Evolution sits behind Cloudflare Access (ADR 0006), so every request carries the
instance token (``apikey``) plus the Access service token headers when they are
configured. Without them Cloudflare answers with a 302 to its login page.

By design this class has no method to create, log out or delete an instance
(ADR 0011): re-linking would require a QR from Oscar's phone. It also refuses
to be pointed at ``personal-whatsapp``.
"""

from __future__ import annotations

import logging

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import requests

SinceType = datetime | int | float

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

USER_AGENT = "corpotex-backend/0.1"
DEFAULT_BASE_URL = "https://evolution.oscargicast.com"
WHATSAPP_JID_SUFFIX = "@s.whatsapp.net"

# `POST /chat/findMessages` pages newest first; `offset` is the page size.
FIND_MESSAGES_PAGE_SIZE = 50
FIND_MESSAGES_MAX_PAGES = 40


logger = logging.getLogger(__name__)


class EvolutionError(Exception):
    """Base of every failure talking to Evolution; callers that only need "it did not
    work" (the style extraction, B4.6) catch this one."""


class EvolutionUnavailable(EvolutionError):
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
            base_url=env.get("EVOLUTION_API_URL") or DEFAULT_BASE_URL,
            instance=env.get("EVOLUTION_INSTANCE") or "corpotex",
            token=env.get("EVOLUTION_INSTANCE_TOKEN") or "",
            cf_client_id=env.get("CF_ACCESS_CLIENT_ID"),
            cf_client_secret=env.get("CF_ACCESS_CLIENT_SECRET"),
        )

    @classmethod
    def from_settings(cls) -> EvolutionClient:
        """Build a client from Django settings (same names as the env)."""
        from django.conf import settings

        return cls.from_env(
            {
                "EVOLUTION_API_URL": settings.EVOLUTION_API_URL,
                "EVOLUTION_INSTANCE": settings.EVOLUTION_INSTANCE,
                "EVOLUTION_INSTANCE_TOKEN": settings.EVOLUTION_INSTANCE_TOKEN,
                "CF_ACCESS_CLIENT_ID": settings.CF_ACCESS_CLIENT_ID,
                "CF_ACCESS_CLIENT_SECRET": settings.CF_ACCESS_CLIENT_SECRET,
            }
        )

    @property
    def has_access_token(self) -> bool:
        """True when both Cloudflare Access service token parts are configured."""
        return bool(self._cf_client_id and self._cf_client_secret)

    def __repr__(self) -> str:  # never show the secrets
        return f"EvolutionClient(base_url={self.base_url!r}, instance={self.instance!r})"

    # -- transport -------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        # Cloudflare's browser integrity check answers 403 (error 1010) to generic
        # Python user agents, so the client identifies itself.
        headers = {"apikey": self._token, "User-Agent": USER_AGENT}
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

    def find_messages(self, jid: str, since: SinceType, *, limit: int = 300) -> list[dict]:
        """Raw message records of a contact since ``since``, oldest first, across BOTH of
        their chats: the phone one (``<phone>@s.whatsapp.net``) and the LID one (``<id>@lid``,
        what WhatsApp uses since 2025; Valeria's chat on 10/10 was one). Either jid works; the
        other is taken from ``AllowedNumber.lid`` or resolved through Evolution and cached.
        Records are merged, deduplicated by ``key.id`` and the MOST RECENT ``limit`` kept."""
        jids = self.chat_jids(jid)
        collected: dict[str, dict] = {}
        for chat in jids:
            for record in self.find_chat_messages(chat, since, limit=limit):
                key = record.get("key") or {}
                collected.setdefault(key.get("id") or f"{chat}:{_timestamp(record)}:{len(collected)}", record)
        records = sorted(collected.values(), key=_timestamp)
        return records[-limit:] if limit > 0 else []

    def chat_jids(self, jid: str) -> list[str]:
        """The phone jid and the LID of one contact, whichever was given (cached on
        ``AllowedNumber.lid``). Never fails: without a mapping, just the jid given."""
        if "@" not in jid:
            jid = f"{jid}{WHATSAPP_JID_SUFFIX}"
        from .models import AllowedNumber

        phone_jid = lid = None
        try:
            if jid.endswith("@lid"):
                lid = jid
                number = AllowedNumber.objects.filter(lid=lid).first()
                phone = number.phone if number else self._safe(self.resolve_phone, lid)
                phone_jid = f"{phone}{WHATSAPP_JID_SUFFIX}" if phone else None
            else:
                phone_jid = jid
                phone = jid.split("@")[0]
                number = AllowedNumber.objects.filter(phone=phone).first()
                lid = (number.lid if number and number.lid else None) or self._safe(self.resolve_lid, phone_jid)
                if number is not None and lid and not number.lid:
                    number.lid = lid
                    number.save(update_fields=["lid", "updated_at"])
        except RuntimeError:  # No database in this context (unit tests of the raw client): just the jid given.
            return [jid]
        return [j for j in (phone_jid, lid) if j]

    @staticmethod
    def _safe(func, arg):
        try:
            return func(arg)
        except EvolutionError as exc:
            logger.warning("evolution: %s(%s) failed: %s", func.__name__, arg, exc)
            return None

    def resolve_lid(self, phone_jid: str) -> str | None:
        """The LID of a phone: any message addressed by LID carries the phone in
        ``key.remoteJidAlt`` (verified on the real instance, 10/10)."""
        for record in self._page({"key": {"remoteJidAlt": phone_jid}}):
            remote = (record.get("key") or {}).get("remoteJid") or ""
            if remote.endswith("@lid"):
                return remote
        return None

    def resolve_phone(self, lid: str) -> str | None:
        """The phone digits behind a LID, from ``remoteJidAlt``/``senderPn`` of its messages."""
        for record in self._page({"key": {"remoteJid": lid}}):
            key = record.get("key") or {}
            for name in ("remoteJidAlt", "senderPn", "previousRemoteJid"):
                alt = key.get(name) or record.get(name) or ""
                if alt.endswith(WHATSAPP_JID_SUFFIX):
                    return alt.split("@")[0]
        return None

    def _page(self, where: dict) -> list[dict]:
        data = self._request("POST", f"/chat/findMessages/{self.instance}", json={"where": where, "offset": 25, "page": 1})
        block = data.get("messages") if isinstance(data, dict) else None
        records = block.get("records") if isinstance(block, dict) else data
        return [record for record in (records or []) if isinstance(record, dict)]

    def find_chat_messages(self, jid: str, since: SinceType, *, limit: int = 300) -> list[dict]:
        """Raw message records of one chat since ``since``, oldest first.

        Records are what Evolution stores (``key``, ``message``, ``messageTimestamp``
        in epoch seconds, ``pushName``, also on ``fromMe``). When the chat holds more
        than ``limit`` messages since ``since`` the MOST RECENT ``limit`` are kept:
        the style of the Gerente is read from how they write today (planning B4.6).
        """
        since_ts = _epoch(since)
        body = {"where": {"key": {"remoteJid": jid}}, "offset": FIND_MESSAGES_PAGE_SIZE}
        collected: list[dict] = []
        for page in range(1, FIND_MESSAGES_MAX_PAGES + 1):
            data = self._request(
                "POST", f"/chat/findMessages/{self.instance}", json={**body, "page": page}
            )
            block = data.get("messages") if isinstance(data, dict) else None
            records = block.get("records") if isinstance(block, dict) else data
            records = [record for record in (records or []) if isinstance(record, dict)]
            if not records:
                break
            fresh = [record for record in records if _timestamp(record) >= since_ts]
            collected.extend(fresh)
            pages = block.get("pages") if isinstance(block, dict) else None
            exhausted = isinstance(pages, int) and page >= pages
            # Pages come newest first: anything older than `since` on this page means
            # the following pages are older still; and `limit` fresh records are
            # already the most recent ones.
            if len(fresh) < len(records) or len(collected) >= limit or exhausted:
                break
        collected.sort(key=_timestamp)
        return collected[-limit:] if limit > 0 else []


def find_messages(jid: str, since: SinceType, *, limit: int = 300) -> list[dict]:
    """Module-level entry point for the style extraction (B4.6): digits or full JID."""
    if "@" not in jid:
        jid = f"{jid}{WHATSAPP_JID_SUFFIX}"
    return EvolutionClient.from_settings().find_messages(jid, since, limit=limit)


def _epoch(value: SinceType) -> float:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.timestamp()
    return float(value)


def _timestamp(record: Mapping) -> float:
    """``messageTimestamp`` as epoch seconds; unparseable values sort first (oldest)."""
    raw = record.get("messageTimestamp")
    if isinstance(raw, Mapping):  # Long {low, high} from older Baileys payloads
        raw = raw.get("low")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0
