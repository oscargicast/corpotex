"""M4 (ADR 0028, photos): a garment photo becomes the line's text in the magic order form.
One structured Claude call with the image, its own system prompt, no tools."""

import asyncio
import base64
import binascii
import io
import logging
import time
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

SYSTEM_PROMPT = (
    "Eres el jefe de producción de Corpotex. Describe la prenda de la foto para una orden de confección: "
    "tipo de prenda, color, cuello, mangas, cierres y detalles visibles (bordado, sublimado, bolsillos). "
    "Una sola frase en español, máximo 25 palabras, sin cantidad ni tallas."
)
SCHEMA = {"type": "object", "properties": {"description": {"type": "string"}}, "required": ["description"], "additionalProperties": False}
MEDIA_TYPES = {"jpeg": "image/jpeg", "jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
MAX_BASE64 = 5 * 1024 * 1024  # the base64 text, as the contract says
TIMEOUT_SECONDS = 30
logger = logging.getLogger(__name__)


class BadImage(ValueError):
    """The request's image cannot be used; the message is for the person (Spanish)."""


def decode(media_type: str, data: str) -> tuple[bytes, str]:
    """Validates the media type (jpeg, png or webp, with or without `image/`) and the base64."""
    normalized = MEDIA_TYPES.get((media_type or "").strip().lower().removeprefix("image/"))
    if normalized is None:
        raise BadImage("La foto tiene que ser JPEG, PNG o WebP.")
    data = (data or "").strip()
    if data.startswith("data:") and "," in data:  # tolerate a data URL from the browser
        data = data.split(",", 1)[1]
    if not data:
        raise BadImage("Falta la foto.")
    if len(data) > MAX_BASE64:
        raise BadImage("La foto pesa más de 5 MB. Prueba con una más liviana.")
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise BadImage("La foto no llegó bien (base64 inválido).")
    return raw, normalized


ITEM_PHOTOS = "items/"  # OrderItem.photo's upload_to


def photo_file(photo: dict) -> ContentFile:
    """N1 (ADR 0029): an order item's `{media_type, data}` as a file to store, after the same
    checks as describe-image plus Pillow: what is saved has to open as an image."""
    from PIL import Image

    raw, media_type = decode(photo.get("media_type"), photo.get("data"))
    try:
        Image.open(io.BytesIO(raw)).verify()
    except Exception:
        raise BadImage("La foto no se pudo abrir como imagen.")
    extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[media_type]
    return ContentFile(raw, name=f"{uuid.uuid4().hex}.{extension}")


def kept_photo(photo_url: str) -> str:
    """The storage name behind a `photo_url` the detail gave out, so a PATCH that re-sends the
    items keeps their photos. Only item photos that exist."""
    prefix = settings.MEDIA_URL + ITEM_PHOTOS
    name = (photo_url or "").strip()
    if not name.startswith(prefix) or ".." in name:
        raise BadImage("La foto del ítem no es una de esta orden.")
    name = name.removeprefix(settings.MEDIA_URL)
    if not default_storage.exists(name):
        raise BadImage("La foto del ítem ya no existe. Súbela de nuevo.")
    return name


def describe_model() -> str:
    """AGENT_MODEL (Opus): as fast as Sonnet on a photo and the sentence reads better on screen
    (orquestador, 11/10, with the measurements of #147). CLASSIFY_MODEL is only for recipes."""
    return getattr(settings, "AGENT_MODEL", "sonnet")


def describe(raw: bytes, media_type: str, *, brand: str | None = None, customer: str | None = None) -> str:
    """The garment in one sentence. Raises on model failure or timeout (the view answers 502)."""
    from agent.persona.context import image_block
    from agent.sdk import complete

    context = []
    if brand:
        context.append(f"marca {brand}")
    if customer:
        context.append(f"cliente {customer}")
    text = "Describe la prenda de esta foto." + (f" Contexto: {', '.join(context)}." if context else "")
    blocks = [image_block(raw, media_type), {"type": "text", "text": text}]
    from .classify import COMPLETE_MAX_TURNS

    coro = asyncio.wait_for(
        complete(blocks, system_prompt=SYSTEM_PROMPT, model=describe_model(), schema=SCHEMA, effort="low", max_turns=COMPLETE_MAX_TURNS), TIMEOUT_SECONDS
    )
    started = time.monotonic()
    try:
        result = _run(coro)
    finally:
        logger.info("describe_image: claude=%.2fs (%d bytes, model %s)", time.monotonic() - started, len(raw), describe_model())
    description = (result.get("description") if isinstance(result, dict) else "") or ""
    if not description.strip():
        raise RuntimeError("empty description")
    return description.strip()


def _run(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()
