"""M4 (ADR 0028, photos): a garment photo becomes the line's text in the magic order form.
One structured Claude call with the image, its own system prompt, no tools."""

import asyncio
import base64
import binascii
import logging
import time

from django.conf import settings

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
    from .classify import classify_model

    from .classify import COMPLETE_MAX_TURNS

    coro = asyncio.wait_for(
        complete(blocks, system_prompt=SYSTEM_PROMPT, model=classify_model(), schema=SCHEMA, effort="low", max_turns=COMPLETE_MAX_TURNS), TIMEOUT_SECONDS
    )
    started = time.monotonic()
    try:
        result = _run(coro)
    finally:
        logger.info("describe_image: claude=%.2fs (%d bytes, model %s)", time.monotonic() - started, len(raw), classify_model())
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
