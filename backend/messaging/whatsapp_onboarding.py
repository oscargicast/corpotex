"""Step 1 of the onboarding (ADR 0011): link WhatsApp and configure the instance.

Pure functions over an :class:`EvolutionClient`, so the Django views (B4.4) can
stay thin. They never create, disconnect or delete instances.
"""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlsplit, urlunsplit

from messaging.evolution import DEFAULT_SETTINGS, EvolutionClient

DEFAULT_PUBLIC_BASE_URL = "https://corpotex.oscargicast.com"
WEBHOOK_PATH = "/webhooks/evolution/"
WEBHOOK_EVENTS = ("MESSAGES_UPSERT",)
MASK = "****"


def webhook_url_from_env(env: Mapping[str, str]) -> str:
    """``<PUBLIC_BASE_URL>/webhooks/evolution/<EVOLUTION_WEBHOOK_SECRET>/``."""
    secret = env.get("EVOLUTION_WEBHOOK_SECRET") or ""
    if not secret:
        raise ValueError("EVOLUTION_WEBHOOK_SECRET is not set")
    base = (env.get("PUBLIC_BASE_URL") or DEFAULT_PUBLIC_BASE_URL).rstrip("/")
    return f"{base}{WEBHOOK_PATH}{secret}/"


def mask_webhook_url(url: str) -> str:
    """Replace the last path segment (the shared secret) with ``****``."""
    parts = urlsplit(url)
    segments = [segment for segment in parts.path.split("/") if segment]
    if not segments:
        return url
    segments[-1] = MASK
    path = "/" + "/".join(segments) + ("/" if parts.path.endswith("/") else "")
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _webhook_base64(webhook: Mapping) -> bool:
    # Evolution reads back ``webhookBase64``; accept the flat key too.
    return bool(webhook.get("webhookBase64", webhook.get("base64", False)))


def _webhook_summary(webhook: Mapping | None) -> dict | None:
    if not webhook:
        return None
    return {
        "url": mask_webhook_url(webhook.get("url") or ""),
        "events": list(webhook.get("events") or []),
        "base64": _webhook_base64(webhook),
    }


def _webhook_matches(webhook: Mapping | None, webhook_url: str) -> bool:
    """True when the instance posts MESSAGES_UPSERT with base64 to our URL."""
    if not webhook or webhook.get("enabled") is False:
        return False
    return (
        webhook.get("url") == webhook_url
        and "MESSAGES_UPSERT" in (webhook.get("events") or [])
        and _webhook_base64(webhook)
    )


def _settings_summary(settings: Mapping) -> dict:
    return {key: settings[key] for key in DEFAULT_SETTINGS if key in settings}


def onboarding_status(client: EvolutionClient, *, webhook_url: str, has_access_token: bool) -> dict:
    """State of the instance, its webhook (secret masked) and settings.

    Without the Cloudflare Access service token Evolution is unreachable, so the
    step is reported as done offline without calling it (ADR 0011).
    """
    if not has_access_token:
        return {
            "state": "unknown",
            "webhook": None,
            "settings": None,
            "offline": True,
            "done": True,
        }
    state = client.connection_state()
    webhook = client.find_webhook()
    settings = client.find_settings()
    return {
        "state": state,
        "webhook": _webhook_summary(webhook),
        "settings": _settings_summary(settings),
        "offline": False,
        "done": state == "open" and _webhook_matches(webhook, webhook_url),
    }


def qr(client: EvolutionClient) -> str | None:
    """The QR data URL to link the instance, or None when it is already linked."""
    return client.connect_qr()


def configure(client: EvolutionClient, *, webhook_url: str) -> dict:
    """Point the webhook at us (only MESSAGES_UPSERT, base64) and apply the ADR settings."""
    client.set_webhook(webhook_url, events=WEBHOOK_EVENTS, base64=True)
    client.set_settings()
    return onboarding_status(client, webhook_url=webhook_url, has_access_token=True)
