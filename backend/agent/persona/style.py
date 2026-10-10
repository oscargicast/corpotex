"""Manager style: base template and validation.

The style itself lives in `User.style_md` and `StyleVersion` (ADR 0019); this module only
knows its shape. Extraction and incremental updates are added in P2.2.
"""

import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

LIMA = ZoneInfo("America/Lima")
TEMPLATE_PATH = Path(__file__).parent / "templates" / "style.base.md"

TITLE = "# Estilo del Gerente"
REQUIRED_SECTIONS = (
    "## Resumen",
    "## Registro",
    "## Forma",
    "## Saludos y despedidas",
    "## Muletillas",
    "## Situaciones",
    "## Nunca dice",
    "## Ejemplos",
)
MIN_CHARS = 500
MAX_CHARS = 12_000

# Peruvian mobile (9 digits starting with 9, optionally grouped), with country code, and RUC.
PHONE_RE = re.compile(r"\b9\d{2}[\s-]?\d{3}[\s-]?\d{3}\b|\b51\d{9}\b")
RUC_RE = re.compile(r"\b(?:10|20)\d{9}\b")
# Amounts must be anonymized as <MONTO>, otherwise the agent may copy them as prices.
AMOUNT_RE = re.compile(r"(?:S/|USD|US\$|\$)\s?\d")


def load_template() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def validate_style(md: str, supplier_names: tuple[str, ...] = ()) -> list[str]:
    """Return a list of problems (in Spanish, shown to the manager); empty means valid.

    `supplier_names` are rejected because the style goes into every conversation's prompt:
    a supplier name there could leak to another supplier.
    """
    errors = []
    lines = {line.strip() for line in md.splitlines()}
    if TITLE not in lines:
        errors.append(f'Falta el título "{TITLE}".')
    for section in REQUIRED_SECTIONS:
        if section not in lines:
            errors.append(f'Falta la sección "{section}".')
    if len(md) < MIN_CHARS:
        errors.append(f"Es muy corto: {len(md)} caracteres (mínimo {MIN_CHARS}).")
    if len(md) > MAX_CHARS:
        errors.append(f"Es muy largo: {len(md)} caracteres (máximo {MAX_CHARS}).")
    if PHONE_RE.search(md):
        errors.append("Tiene un número de teléfono.")
    if RUC_RE.search(md):
        errors.append("Tiene un RUC.")
    if AMOUNT_RE.search(md):
        errors.append("Tiene un monto; usa <MONTO>.")
    lowered = md.lower()
    for name in supplier_names:
        if name and name.lower() in lowered:
            errors.append(f'Nombra a un proveedor ("{name}"); usa <PROVEEDOR>.')
    return errors


# --- Anonymization ---------------------------------------------------------------------------

HONORIFICS = {"sr", "sra", "srta", "ing", "dr", "dra", "lic", "don", "doña"}
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
URL_RE = re.compile(r"\bhttps?://\S+|\bwww\.\S+", re.IGNORECASE)
DNI_RE = re.compile(r"\bDNI\s*:?\s*\d{8}\b", re.IGNORECASE)
AMOUNT_VALUE_RE = re.compile(r"(?:S/|USD|US\$|\$)\s?\d[\d.,]*")


def _name_patterns(names, *, by_word: bool) -> list[re.Pattern]:
    """Full names first; with `by_word`, also each meaningful word (skipping "Sr.", "Ing."...).

    People go by word ("Ramírez" alone is still the contact); company names do not, or every
    "Lima" or "Norte" in the chat would be replaced.
    """
    full, words = set(), set()
    for name in names:
        name = (name or "").strip()
        if not name:
            continue
        full.add(name)
        if not by_word:
            continue
        for word in re.split(r"[\s.,]+", name):
            if len(word) >= 3 and word.lower() not in HONORIFICS:
                words.add(word)
    ordered = sorted(full, key=len, reverse=True) + sorted(words, key=len, reverse=True)
    return [re.compile(rf"(?<!\w){re.escape(item)}(?!\w)", re.IGNORECASE) for item in ordered]


def anonymize(
    text: str,
    *,
    contact_names=(),
    supplier_names=(),
    manager_names=(),
) -> str:
    """Replace personal data with the placeholders the style uses.

    Idempotent: running it twice gives the same text, so an already anonymized transcript
    can go through the pipeline again.
    """
    text = URL_RE.sub("<URL>", text)
    text = EMAIL_RE.sub("<CORREO>", text)
    text = DNI_RE.sub("DNI <DNI>", text)
    text = RUC_RE.sub("<RUC>", text)
    text = PHONE_RE.sub("<TELEFONO>", text)
    text = AMOUNT_VALUE_RE.sub("<MONTO>", text)
    for placeholder, names, by_word in (
        ("<PROVEEDOR>", supplier_names, False),
        ("<CONTACTO>", contact_names, True),
        ("<GERENTE>", manager_names, True),
    ):
        for pattern in _name_patterns(names, by_word=by_word):
            text = pattern.sub(placeholder, text)
    return text


# --- WhatsApp export parser ------------------------------------------------------------------

ANDROID_LINE = re.compile(
    r"^(\d{1,2})/(\d{1,2})/(\d{2,4}),?\s(\d{1,2}):(\d{2})(?:\s?([ap])\.?\s?m\.?)?\s-\s([^:]+):\s?(.*)$",
    re.IGNORECASE,
)
IOS_LINE = re.compile(
    r"^\[(\d{1,2})/(\d{1,2})/(\d{2,4}),?\s(\d{1,2}):(\d{2})(?::\d{2})?(?:\s?([ap])\.?\s?m\.?)?\]\s([^:]+):\s?(.*)$",
    re.IGNORECASE,
)
# LRM/RLM marks, bidi embeddings, narrow no-break space and BOM that exports insert.
INVISIBLE = dict.fromkeys([0x200E, 0x200F, 0x202A, 0x202C, 0x202F, 0xFEFF], None)
MEDIA_PLACEHOLDERS = {
    "<multimedia omitido>": "[archivo]",
    "<media omitted>": "[archivo]",
    "imagen omitida": "[imagen]",
    "image omitted": "[imagen]",
    "audio omitido": "[audio]",
    "audio omitted": "[audio]",
    "sticker omitido": "[sticker]",
    "sticker omitted": "[sticker]",
}
DELETED = {"se eliminó este mensaje", "eliminaste este mensaje", "this message was deleted"}


def _parse_header(line: str):
    match = ANDROID_LINE.match(line) or IOS_LINE.match(line)
    if not match:
        return None
    day, month, year, hour, minute, meridiem, author, body = match.groups()
    year = int(year) + 2000 if len(year) == 2 else int(year)
    hour = int(hour)
    if meridiem:
        hour = hour % 12 + (12 if meridiem.lower() == "p" else 0)
    sent_at = datetime(year, int(month), int(day), hour, int(minute), tzinfo=LIMA)
    return sent_at, author.strip(), body


def parse_whatsapp_export(
    content: str,
    manager_author: str,
    since: date,
    supplier_id=None,
    supplier_name: str | None = None,
) -> dict:
    """Parse an Android or iOS "export chat" (dd/mm dates) into an anonymized chat.

    Returns the same shape backend passes to `extract_style`:
    `{supplier_id, supplier_name, contact_names, messages: [{sender, text, sent_at}]}`.
    """
    messages = []
    for raw in content.translate(INVISIBLE).splitlines():
        header = _parse_header(raw)
        if header:
            sent_at, author, body = header
            messages.append({"author": author, "sent_at": sent_at, "lines": [body]})
        elif messages and raw.strip():
            messages[-1]["lines"].append(raw)  # continuation of a multiline message

    contact_names = sorted({m["author"] for m in messages if m["author"] != manager_author})
    chat_messages = []
    for message in messages:
        if message["sent_at"].date() < since:
            continue
        body = "\n".join(message["lines"]).strip()
        lowered = body.lower()
        if not body or lowered in DELETED:
            continue
        body = MEDIA_PLACEHOLDERS.get(lowered, body)
        chat_messages.append(
            {
                "sender": "manager" if message["author"] == manager_author else "supplier",
                "text": anonymize(
                    body,
                    contact_names=contact_names,
                    supplier_names=[supplier_name] if supplier_name else [],
                    manager_names=[manager_author],
                ),
                "sent_at": message["sent_at"].isoformat(),
            }
        )
    return {
        "supplier_id": supplier_id,
        "supplier_name": supplier_name,
        "contact_names": contact_names,
        "messages": chat_messages,
    }
