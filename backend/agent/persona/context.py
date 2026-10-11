"""Small helpers to render turn state as the Spanish XML the models read."""

import base64
import mimetypes
from datetime import date, datetime
from decimal import Decimal
from html import escape
from zoneinfo import ZoneInfo

# Times in the prompt are always Lima time: the services hand us UTC-aware datetimes.
LIMA = ZoneInfo("America/Lima")
WEEKDAYS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
AUDIO_EXTENSIONS = {".ogg", ".oga", ".opus", ".mp3", ".m4a", ".aac", ".wav"}
MAX_IMAGES_PER_TURN = 4


def text(value) -> str:
    """Escape free text (supplier messages, notes) so it cannot close our tags."""
    return escape("" if value is None else str(value), quote=False)


def attrs(**values) -> str:
    """Render XML attributes, skipping empty values."""
    parts = []
    for key, value in values.items():
        if value is None or value == "":
            continue
        parts.append(f'{key}="{escape(str(value), quote=True)}"')
    return (" " + " ".join(parts)) if parts else ""


def as_datetime(value) -> datetime | None:
    """Aware datetimes (and ISO strings with offset) converted to Lima; naive ones kept."""
    if value in (None, ""):
        return None
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return moment.astimezone(LIMA) if moment.tzinfo else moment


def as_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime) or (isinstance(value, str) and len(value) > 10):
        return as_datetime(value).date()  # the Lima day, not the UTC one
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def fmt_date(value) -> str:
    """`sáb 17/10`: short and unambiguous for the model."""
    day = as_date(value)
    return f"{WEEKDAYS[day.weekday()]} {day:%d/%m}" if day else ""


def fmt_datetime(value) -> str:
    moment = as_datetime(value)
    return f"{WEEKDAYS[moment.weekday()]} {moment:%d/%m %H:%M}" if moment else ""


def fmt_time(value) -> str:
    moment = as_datetime(value)
    return f"{moment:%H:%M}" if moment else ""


def fmt_money(amount, currency: str = "PEN") -> str:
    if amount in (None, ""):
        return ""
    value = Decimal(str(amount)).quantize(Decimal("0.01"))
    return f"USD {value}" if currency == "USD" else f"S/ {value}"


def media_kind(media_url: str | None) -> str:
    """`imagen`, `audio` or `archivo`, from the file extension."""
    if not media_url:
        return ""
    path = media_url.split("?", 1)[0].lower()
    extension = path[path.rfind(".") :] if "." in path else ""
    if extension in IMAGE_EXTENSIONS:
        return "imagen"
    if extension in AUDIO_EXTENSIONS:
        return "audio"
    return "archivo"


def image_block(data: bytes, media_type: str) -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.b64encode(data).decode("ascii"),
        },
    }


def load_message_images(new_messages: list[dict]) -> list[tuple[str, dict]]:
    """Image blocks for the most recent image messages, as `(label, block)` pairs.

    Reads `Message.media` by id (read-only). Only the last MAX_IMAGES_PER_TURN go as images;
    older ones stay as `media="imagen"` in the XML.
    """
    from messaging.models import Message  # Django import kept local: pure helpers stay testable

    with_images = [m for m in new_messages if media_kind(m.get("media_url")) == "imagen"]
    images = []
    for item in with_images[-MAX_IMAGES_PER_TURN:]:
        message = Message.objects.filter(id=item["id"]).first()
        if not message or not message.media:
            continue
        media_type = mimetypes.guess_type(message.media.name)[0] or "image/jpeg"
        with message.media.open("rb") as handle:
            data = handle.read()
        label = f"foto del mensaje de las {fmt_time(item.get('sent_at'))}"
        images.append((label, image_block(data, media_type)))
    return images
