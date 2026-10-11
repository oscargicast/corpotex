"""Evolution API webhook (`MESSAGES_UPSERT`). The secret travels in the URL; the allowlist is
the safety net: anything from a number that is not active is dropped without being stored
(ADR 0001, 0016)."""

import base64
import hmac
import json
import logging
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import AllowedNumber, Conversation, Message
from .services import conversation_for_number, enqueue_turn

logger = logging.getLogger(__name__)
ECHO_WINDOW_SECONDS = 30


@csrf_exempt
@require_POST
def evolution_webhook(request, secret: str):
    if not settings.EVOLUTION_WEBHOOK_SECRET or not hmac.compare_digest(secret, settings.EVOLUTION_WEBHOOK_SECRET):
        return HttpResponseForbidden()
    try:
        payload = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"detail": "invalid json"}, status=400)
    event = str(payload.get("event", "")).upper().replace(".", "_")
    if event != "MESSAGES_UPSERT":
        return HttpResponse(status=200)
    data = payload.get("data") or {}
    if isinstance(data, list):
        for item in data:
            handle_upsert(item)
    else:
        handle_upsert(data)
    return HttpResponse(status=200)


def handle_upsert(data: dict) -> Message | None:
    key = data.get("key") or {}
    remote_jid = key.get("remoteJid", "")
    if remote_jid.endswith("@g.us") or remote_jid.startswith("status@"):
        return None
    phone, lid = _identify(data, remote_jid)
    number = _allowed_number(phone, lid)
    if number is None:
        logger.info("webhook: dropped message from %s (not allowlisted)", remote_jid)
        return None
    if lid and not number.lid:
        number.lid = lid
        number.save(update_fields=["lid", "updated_at"])
    conversation = conversation_for_number(number, Conversation.Channel.WHATSAPP)
    external_id = key.get("id")
    text, media, media_name = _content(data)
    sent_at = _timestamp(data)
    from_me = bool(key.get("fromMe"))

    if from_me:
        return _handle_from_me(conversation, external_id, text, sent_at)
    try:
        with transaction.atomic():
            message = Message.objects.create(
                conversation=conversation,
                author=Message.Author.SUPPLIER,
                text=text,
                external_id=external_id,
                status=Message.Status.RECEIVED,
                sent_at=sent_at,
            )
            if media:
                message.media.save(media_name, ContentFile(media), save=True)
            enqueue_turn(conversation, "message")
    except IntegrityError:
        logger.info("webhook: duplicate external_id %s ignored", external_id)
        return None
    logger.debug("webhook payload: %s", json.dumps(data, ensure_ascii=False)[:2000])
    return message


def _handle_from_me(conversation, external_id, text, sent_at):
    """Our own sends come back as `fromMe`: match by id, or by text within 30 s. Anything else
    was typed by the manager on the phone: stored as `manager`, no turn."""
    if external_id and Message.objects.filter(external_id=external_id).exists():
        return None
    window = timezone.now() - timezone.timedelta(seconds=ECHO_WINDOW_SECONDS)
    echo = (
        conversation.messages.filter(author=Message.Author.AGENT, text=text, sent_at__gte=window, external_id__isnull=True)
        .order_by("-sent_at")
        .first()
    )
    if echo is not None:
        echo.external_id = external_id
        echo.save(update_fields=["external_id", "updated_at"])
        return None
    try:
        return Message.objects.create(
            conversation=conversation,
            author=Message.Author.MANAGER,
            text=text,
            external_id=external_id,
            status=Message.Status.SENT,
            sent_at=sent_at,
        )
    except IntegrityError:
        return None


LID_PHONE_KEYS = ("remoteJidAlt", "senderPn", "previousRemoteJid", "participantAlt")


def _identify(data: dict, remote_jid: str) -> tuple[str | None, str | None]:
    """WhatsApp may address a chat by `<id>@lid` instead of the phone (verified on the real
    instance on 10/10: Valeria's chat is a LID). The phone then travels in `key.remoteJidAlt`,
    `senderPn` or `previousRemoteJid`, on the key or on the payload."""
    key = data.get("key") or {}
    if remote_jid.endswith("@lid"):
        for name in LID_PHONE_KEYS:
            alt = key.get(name) or data.get(name) or ""
            if alt.endswith("@s.whatsapp.net"):
                return alt.split("@")[0], remote_jid
        return None, remote_jid
    return remote_jid.split("@")[0] or None, None


def _allowed_number(phone, lid) -> AllowedNumber | None:
    qs = AllowedNumber.objects.filter(active=True, simulated=False)
    if phone:
        number = qs.filter(phone=phone).first()
        if number:
            return number
    if lid:
        number = qs.filter(lid=lid).first()
        if number:
            return number
        # Unknown LID without the phone on the payload: ask Evolution once and cache it.
        from .evolution import EvolutionClient, EvolutionError

        try:
            resolved = EvolutionClient.from_settings().resolve_phone(lid)
        except EvolutionError as exc:
            logger.warning("webhook: could not resolve %s: %s", lid, exc)
            return None
        if resolved:
            return qs.filter(phone=resolved).first()
    return None


def _content(data: dict) -> tuple[str, bytes | None, str]:
    message = data.get("message") or {}
    text = message.get("conversation") or (message.get("extendedTextMessage") or {}).get("text") or ""
    media = None
    media_name = ""
    for kind, ext in (("imageMessage", "jpg"), ("audioMessage", "ogg"), ("documentMessage", "bin")):
        inner = message.get(kind)
        if inner:
            text = text or inner.get("caption") or ""
            b64 = inner.get("base64") or message.get("base64") or data.get("base64")
            if b64:
                try:
                    media = base64.b64decode(b64)
                    media_name = f"{(data.get('key') or {}).get('id', 'media')}.{ext}"
                except Exception:
                    logger.warning("webhook: could not decode base64 media")
            break
    return text, media, media_name


def _timestamp(data: dict):
    ts = data.get("messageTimestamp")
    try:
        ts = int(ts.get("low") if isinstance(ts, dict) else ts)
        return datetime.fromtimestamp(ts, tz=dt_timezone.utc)
    except (TypeError, ValueError, AttributeError):
        return timezone.now()
