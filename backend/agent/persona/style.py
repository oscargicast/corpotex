"""Manager style: template, validation, anonymization, parser and extraction (ADR 0011, 0019).

The style itself lives in `User.style_md` and `StyleVersion`; this module only builds and
checks it. Model calls go through `agent.sdk.complete` with the shared Claude account.
"""

import asyncio
import copy
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, ValidationError

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
# The agent writes from the manager's own number: his phrases never name him.
MANAGER_RE = re.compile(r"\bgerente\b", re.IGNORECASE)


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
    for line in md.splitlines():
        phrase = line.strip()
        if phrase.startswith(('- "', "[G]")) and MANAGER_RE.search(phrase):
            errors.append(
                f"Una frase del Gerente lo nombra en tercera persona ({phrase[:80]}): "
                "el asistente escribe desde su número."
            )
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


# --- Extraction with the model (P2.2) --------------------------------------------------------

NOT_CONNECTED = "Conecta tu cuenta de Claude en Configuración."
MAX_TRANSCRIPT_MESSAGES = 300
MAX_TRANSCRIPT_CHARS = 30_000
CONCURRENCY = 2  # the bot shares the subscription limits (ADR 0013)
SITUATIONS = (
    "Proponer el pedido",
    "Pedir fecha",
    "Insistir",
    "Decir que no o regatear",
    "Dejar en pausa",
    "Cerrar el pedido",
    "Recibir avance o foto",
    "Problema o cancelación",
)


class StyleError(Exception):
    """The extraction failed; the message is in Spanish and goes to the manager as is."""


class SupplierNotes(BaseModel):
    trato: str = Field(description="tú o usted, y cómo le dice (usa <CONTACTO> para su nombre)")
    tono: str
    insistencia: str = Field(description="cuánto tolera que le insistan y cada cuánto escribirle")
    horario: str = Field(default="", description="cuándo responde, si se ve; si no, vacío")
    ojo: str = Field(default="", description="lo particular de este proveedor, si hay")


class SituationQuotes(BaseModel):
    situation: str = Field(description="una de: " + ", ".join(SITUATIONS))
    how: str = Field(description="qué hace el Gerente en esa situación, en una línea")
    quotes: list[str] = Field(description="1 o 2 mensajes del Gerente, textuales")


class Exchange(BaseModel):
    supplier: str = Field(description="mensaje del proveedor, textual")
    manager: list[str] = Field(description="respuesta del Gerente, uno o más mensajes textuales")


class SupplierAnalysis(BaseModel):
    treatment: str = Field(description="tú, usted o mixto")
    summary: str = Field(description="cómo escribe el Gerente con este proveedor, en 2 líneas")
    form: list[str] = Field(description="largo, cortes, mayúsculas, puntuación, emojis")
    greetings: list[str] = Field(description="saludos y despedidas textuales")
    phrases: list[str] = Field(description="muletillas y expresiones que repite")
    never_says: list[str] = Field(description="lo que evita, si se nota")
    situations: list[SituationQuotes]
    examples: list[Exchange] = Field(description="2 o 3 intercambios representativos")
    notes: SupplierNotes


class StyleDraft(BaseModel):
    style_md: str


class SupplierNotesUpdate(BaseModel):
    supplier: str = Field(description='la etiqueta del proveedor, por ejemplo "Proveedor 1"')
    notes: SupplierNotes


class StyleUpdate(BaseModel):
    style_md: str
    notes: list[SupplierNotesUpdate]
    changelog: list[str] = Field(description="cambios del estilo y sugerencias, máximo 5")


ANALYSIS_SYSTEM = """\
Analizas cómo le escribe por WhatsApp el Gerente de una empresa de uniformes de Piura a un \
proveedor. Te paso el chat anonimizado: [G] son mensajes del Gerente y [P] del proveedor; \
"(+2d)" es el tiempo desde el mensaje anterior.

- Describe solo cómo escribe el Gerente. Los [P] son contexto.
- No inventes: cita textual y deja los marcadores (<CONTACTO>, <MONTO>, <FECHA>...) tal cual. \
Si queda el nombre de otra persona, cámbialo por <PERSONA>.
- Ignora lo personal o familiar que no sea del trabajo: no lo cites ni lo resumas.
- No uses como ejemplo mensajes donde el Gerente promete pagos o fechas de pago.
- Las notas son para el asistente que le escribirá a este proveedor: cortas y concretas."""

DRAFT_SYSTEM = """\
Escribes el estilo del Gerente de Corpotex en markdown, para que un asistente le escriba a los \
proveedores por WhatsApp como él. Te paso el análisis de sus chats con varios proveedores.

Usa exactamente esta estructura, con estos títulos:
{skeleton}

- Es el estilo general: nada de nombres de proveedores ni de personas (usa <CONTACTO> o \
<PERSONA>), ni montos (<MONTO>), fechas (<FECHA>) o teléfonos.
- Registro: el trato por defecto; el de cada proveedor está en sus notas, no lo pongas acá.
- Situaciones: cada una con qué hace el Gerente y 1 o 2 citas textuales "[G] …" de los análisis.
- Ejemplos: de 4 a 6 intercambios, cada línea empieza con "[P] " o "[G] ".
- Nada que prometa pagos o fechas de pago.
- Menos de 8000 caracteres."""

UPDATE_SYSTEM = """\
Actualizas el estilo del Gerente de Corpotex con mensajes nuevos de sus chats con proveedores. \
Te paso el estilo actual, las notas actuales de cada proveedor y los chats nuevos, anonimizados \
([G] Gerente, [P] proveedor).

- Cambia solo lo que los mensajes nuevos muestran con claridad. Si no hay nada nuevo, devuelve \
el estilo igual.
- Mantén la misma estructura y los mismos títulos.
- El estilo es general: nada de nombres de proveedores ni de personas, montos, fechas o \
teléfonos. Lo propio de un proveedor va en sus notas.
- Devuelve las notas de cada proveedor de los chats nuevos, actualizadas.
- changelog: lo que cambió, en frases cortas en español (máximo 5). Lo que sea de un proveedor \
va como sugerencia, por ejemplo "con Proveedor 2 ahora escribe de usted"."""


def _skeleton() -> str:
    lines = [TITLE]
    for section in REQUIRED_SECTIONS:
        lines.append(section)
        if section == "## Situaciones":
            lines.extend(f"### {situation}" for situation in SITUATIONS)
    return "\n".join(lines)


def _as_aware(value) -> datetime:
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return moment if moment.tzinfo else moment.replace(tzinfo=LIMA)


def _since_datetime(since) -> datetime:
    if isinstance(since, datetime):
        return _as_aware(since)
    return datetime(since.year, since.month, since.day, tzinfo=LIMA)


def _gap(delta) -> str:
    hours = delta.total_seconds() / 3600
    if hours < 6:
        return ""
    return f" (+{round(hours / 24)}d)" if hours >= 36 else f" (+{round(hours)}h)"


def build_transcript(messages: list[dict]) -> tuple[str, int]:
    """`([G]/[P] transcript, manager messages)`, newest last, without the agent's messages."""
    ordered = sorted(
        (m for m in messages if m.get("sender") in ("manager", "supplier") and m.get("text")),
        key=lambda m: _as_aware(m["sent_at"]),
    )[-MAX_TRANSCRIPT_MESSAGES:]
    lines, previous = [], None
    for message in ordered:
        moment = _as_aware(message["sent_at"])
        gap = _gap(moment - previous) if previous else ""
        prefix = "[G]" if message["sender"] == "manager" else "[P]"
        lines.append(f"{prefix}{gap} {message['text']}")
        previous = moment
    while lines and sum(len(line) + 1 for line in lines) > MAX_TRANSCRIPT_CHARS:
        lines.pop(0)
    managers = sum(1 for line in lines if line.startswith("[G]"))
    return "\n".join(lines), managers


def format_notes(notes: SupplierNotes) -> str:
    lines = [f"Trato: {notes.trato}", f"Tono: {notes.tono}", f"Insistencia: {notes.insistencia}"]
    if notes.horario:
        lines.append(f"Horario: {notes.horario}")
    if notes.ojo:
        lines.append(f"Ojo: {notes.ojo}")
    return "\n".join(line.strip() for line in lines)


def _group_chats(chats: list[dict], since, manager_names) -> list[dict]:
    """One anonymized group per supplier: several numbers of the same supplier are merged."""
    since_at = _since_datetime(since)
    groups: dict = {}
    for chat in chats:
        group = groups.setdefault(
            chat.get("supplier_id"),
            {
                "supplier_id": chat.get("supplier_id"),
                "supplier_name": chat.get("supplier_name") or "",
                "contact_names": set(),
                "messages": [],
            },
        )
        group["contact_names"].update(n for n in chat.get("contact_names") or [] if n)
        group["messages"].extend(chat.get("messages") or [])
    for group in groups.values():
        kept = []
        for message in group["messages"]:
            if message.get("sender") == "agent" or _as_aware(message["sent_at"]) < since_at:
                continue
            text = anonymize(
                str(message.get("text") or ""),
                contact_names=group["contact_names"],
                supplier_names=[group["supplier_name"]],
                manager_names=manager_names,
            )
            kept.append({**message, "text": text})
        group["messages"] = kept
    return list(groups.values())


def _model(name: str, default: str) -> str:
    try:
        from django.conf import settings
        from django.core.exceptions import ImproperlyConfigured

        try:
            return getattr(settings, name, None) or os.environ.get(name, default)
        except ImproperlyConfigured:  # scripts and tests without Django settings
            return os.environ.get(name, default)
    except ImportError:
        return os.environ.get(name, default)


def _inline_refs(schema: dict) -> dict:
    """Pydantic puts nested models under $defs; structured output gets them inlined."""
    defs = schema.pop("$defs", {})

    def resolve(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return resolve(copy.deepcopy(defs[node["$ref"].rsplit("/", 1)[-1]]))
            return {key: resolve(value) for key, value in node.items()}
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    return resolve(schema)


def _ask(prompt: str, system: str, model: str, result_model: type[BaseModel], check=None):
    """One structured call, validated with pydantic (and `check`), retried once with the error."""
    from agent import sdk

    schema = _inline_refs(result_model.model_json_schema())
    error = None
    for _ in range(2):
        full = prompt
        if error:
            full += f"\n\n<error_anterior>Tu respuesta anterior no sirvió: {error}</error_anterior>"
        try:
            raw = asyncio.run(sdk.complete(full, system_prompt=system, model=model, schema=schema))
            result = result_model.model_validate(raw)
        except sdk.ClaudeNotConnected as exc:
            raise StyleError(NOT_CONNECTED) from exc
        except ValidationError as exc:
            error = str(exc)[:500]
            continue
        except sdk.ClaudeSDKError as exc:  # the CLI failed (limits, network): retry once
            error = str(exc)[:300]
            continue
        problems = check(result) if check else []
        if not problems:
            return result
        error = " ".join(problems)
    raise StyleError(f"El modelo no devolvió un estilo válido: {error}")


def _require_connection():
    from agent import sdk

    if not sdk.is_connected():
        raise StyleError(NOT_CONNECTED)


def _forbidden_names(groups) -> tuple[str, ...]:
    names = {g["supplier_name"] for g in groups if g["supplier_name"]}
    for group in groups:
        names.update(group["contact_names"])
    return tuple(sorted(names))


def extract_style(chats: list[dict], since, on_progress=None, manager_names=()) -> dict:
    """Style and per-supplier notes from past chats: `{"style_md", "notes": {supplier_id: str}}`.

    One analysis per supplier (STYLE_ANALYSIS_MODEL, 2 at a time) and one final draft
    (STYLE_BOSS_MODEL). Raises StyleError with a message for the manager.
    """
    progress = on_progress or (lambda *args, **kwargs: None)
    _require_connection()
    groups = _group_chats(chats, since, manager_names)
    analysis_model = _model("STYLE_ANALYSIS_MODEL", "sonnet")

    pending = {}
    for group in groups:
        transcript, managers = build_transcript(group["messages"])
        if managers == 0:
            progress(group["supplier_id"], "no_chat", messages_read=len(group["messages"]))
            continue
        progress(group["supplier_id"], "analyzing", messages_read=len(group["messages"]))
        pending[group["supplier_id"]] = transcript

    analyses = {}
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = {
            pool.submit(
                _ask,
                f"<chat>\n{transcript}\n</chat>",
                ANALYSIS_SYSTEM,
                analysis_model,
                SupplierAnalysis,
            ): supplier_id
            for supplier_id, transcript in pending.items()
        }
        for future in as_completed(futures):
            supplier_id = futures[future]
            try:
                analyses[supplier_id] = future.result()
            except StyleError as exc:
                if str(exc) == NOT_CONNECTED:
                    raise
                progress(supplier_id, "error", error=str(exc))
                continue
            progress(supplier_id, "done")
    if not analyses:
        raise StyleError("No hay mensajes del Gerente en los chats elegidos desde esa fecha.")

    progress(None, "merging")
    labeled = [
        {"proveedor": f"Proveedor {index}", **analysis.model_dump(exclude={"notes"})}
        for index, analysis in enumerate(analyses.values(), start=1)
    ]
    forbidden = _forbidden_names(groups)
    draft = _ask(
        "<analisis>\n" + json.dumps(labeled, ensure_ascii=False, indent=1) + "\n</analisis>",
        DRAFT_SYSTEM.format(skeleton=_skeleton()),
        _model("STYLE_BOSS_MODEL", "opus"),
        StyleDraft,
        check=lambda result: validate_style(result.style_md, forbidden),
    )
    notes = {}
    by_id = {g["supplier_id"]: g for g in groups}
    for supplier_id, analysis in analyses.items():
        group = by_id[supplier_id]
        notes[supplier_id] = anonymize(
            format_notes(analysis.notes),
            contact_names=group["contact_names"],
            manager_names=manager_names,
        )
    return {"style_md": draft.style_md.strip() + "\n", "notes": notes}


def update_style(
    current_md: str,
    current_notes: dict,
    chats: list[dict],
    on_progress=None,
    manager_names=(),
    since=None,
) -> dict:
    """Incremental update with new chats: `{"style_md", "notes", "changelog"}`.

    Used by the daily refresh (which ignores `notes`, ADR 0019) and by import-txt (which merges
    one chat into the draft). Without new manager messages it returns the input unchanged and
    does not call the model.
    """
    progress = on_progress or (lambda *args, **kwargs: None)
    groups = _group_chats(chats, since or date(2000, 1, 1), manager_names)
    labels, blocks = {}, []
    for index, group in enumerate(groups, start=1):
        transcript, managers = build_transcript(group["messages"])
        if managers == 0:
            progress(group["supplier_id"], "no_chat", messages_read=len(group["messages"]))
            continue
        label = f"Proveedor {index}"
        labels[label] = group
        current = current_notes.get(group["supplier_id"]) or "Sin notas."
        blocks.append(
            f'<chat proveedor="{label}">\n<notas_actuales>\n{current}\n</notas_actuales>\n'
            f"{transcript}\n</chat>"
        )
    if not blocks:
        return {"style_md": current_md, "notes": dict(current_notes), "changelog": []}

    _require_connection()
    progress(None, "merging")
    forbidden = _forbidden_names(groups)
    result = _ask(
        f"<estilo_actual>\n{current_md}\n</estilo_actual>\n\n" + "\n\n".join(blocks),
        UPDATE_SYSTEM,
        _model("STYLE_BOSS_MODEL", "opus"),
        StyleUpdate,
        check=lambda update: validate_style(update.style_md, forbidden),
    )
    notes = dict(current_notes)
    for item in result.notes:
        group = labels.get(item.supplier)
        if group is None:
            continue
        notes[group["supplier_id"]] = anonymize(
            format_notes(item.notes),
            contact_names=group["contact_names"],
            manager_names=manager_names,
        )
        progress(group["supplier_id"], "done")
    return {
        "style_md": result.style_md.strip() + "\n",
        "notes": notes,
        "changelog": [line.strip() for line in result.changelog if line.strip()][:5],
    }
