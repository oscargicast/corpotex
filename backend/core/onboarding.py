"""Style step of the onboarding (ADR 0011): one row with the draft and its progress.

The manager starts an extraction from WhatsApp, adds exported chats or loads the template,
edits the draft and approves it (`core.style.approve_style`). Raw messages never reach the
database: they are read, anonymized and analyzed in memory by the task.
"""

from datetime import date, datetime, timedelta

from django.db import transaction
from django.utils import timezone

from agent.persona.style import (
    LIMA,
    StyleError,
    extract_style,
    load_template,
    parse_whatsapp_export,
    update_style,
)

from .models import Config, OnboardingStyle, StyleVersion
from .permissions import require_role

STALE_AFTER = timedelta(minutes=5)
INTERRUPTED = "La extracción se interrumpió. Vuelve a intentarlo."


class StyleBusy(Exception):
    """An extraction is running; the API answers 409."""


class StyleInputError(Exception):
    """Bad input from the manager; the API answers 400 with this message."""


def is_running(row: OnboardingStyle) -> bool:
    """Extracting and with a recent heartbeat (5 min without progress means it died)."""
    if row.status != OnboardingStyle.Status.EXTRACTING:
        return False
    return bool(row.heartbeat_at and timezone.now() - row.heartbeat_at < STALE_AFTER)


def _base_status(supplier) -> str:
    numbers = [n for n in supplier.numbers.all() if not n.simulated]
    if not numbers:
        return "no_phone"
    if not any(n.active for n in numbers):
        return "not_allowed"
    return "pending"


def _active_suppliers():
    from suppliers.models import Supplier

    return Supplier.objects.filter(status=Supplier.Status.ACTIVE).prefetch_related("numbers")


def onboarding_state() -> dict:
    """What `GET /api/onboarding/style/` returns."""
    row = OnboardingStyle.load()
    status, error = row.status, row.error
    if status == OnboardingStyle.Status.EXTRACTING and not is_running(row):
        status, error = OnboardingStyle.Status.ERROR, INTERRUPTED
    suppliers = []
    for supplier in _active_suppliers().order_by("name"):
        entry = row.progress.get(str(supplier.id)) or {"status": _base_status(supplier)}
        suppliers.append(
            {
                "id": supplier.id,
                "name": supplier.name,
                "status": entry.get("status"),
                "messages_read": entry.get("messages_read"),
                "error": entry.get("error") or "",
            }
        )
    names = dict(_active_suppliers().values_list("id", "name"))
    notes = [
        {"supplier_id": int(key), "supplier_name": names.get(int(key), ""), "notes": value}
        for key, value in row.draft_notes.items()
    ]
    return {
        "status": status,
        "status_display": OnboardingStyle.Status(status).label,
        "error": error,
        "since": row.since,
        "step": row.step or None,
        "suppliers": suppliers,
        "style_md": row.draft_style_md,
        "notes": notes,
        "approved_at": row.approved_at,
    }


def _lock_row() -> OnboardingStyle:
    OnboardingStyle.load()
    row = OnboardingStyle.objects.select_for_update().get(pk=1)
    if is_running(row):
        raise StyleBusy
    return row


def _enqueue(mode: str) -> None:
    from .tasks_style import run_style_extraction

    transaction.on_commit(lambda: run_style_extraction.delay(mode))


@transaction.atomic
def start_extraction(*, since: date, supplier_ids=None, actor) -> None:
    """Read the chats of the chosen suppliers from WhatsApp and replace the draft."""
    require_role(actor, "manager")
    row = _lock_row()
    suppliers = _active_suppliers()
    if supplier_ids:
        suppliers = suppliers.filter(id__in=supplier_ids)
    progress = {str(s.id): {"status": _base_status(s)} for s in suppliers}
    if not any(entry["status"] == "pending" for entry in progress.values()):
        raise StyleInputError("Ningún proveedor elegido tiene un celular activo.")
    row.status = OnboardingStyle.Status.EXTRACTING
    row.since, row.step, row.progress = since, OnboardingStyle.Step.SUPPLIERS, progress
    row.error, row.temp_transcript, row.heartbeat_at = "", None, timezone.now()
    row.save()
    _enqueue("extract")


@transaction.atomic
def import_txt(*, content: str, manager_author: str, since: date, supplier_id=None, actor) -> None:
    """Add one exported chat to the current draft (it never replaces it)."""
    require_role(actor, "manager")
    supplier_name = None
    if supplier_id:
        supplier = _active_suppliers().filter(id=supplier_id).first()
        if supplier is None:
            raise StyleInputError("Ese proveedor no existe o no está activo.")
        supplier_name = supplier.name
    chat = parse_whatsapp_export(content, manager_author, since, supplier_id, supplier_name)
    if not any(m["sender"] == "manager" for m in chat["messages"]):
        raise StyleInputError(
            f'No hay mensajes de "{manager_author}" desde esa fecha en el archivo.'
        )
    row = _lock_row()
    row.status = OnboardingStyle.Status.EXTRACTING
    row.since, row.step, row.error = since, OnboardingStyle.Step.SUPPLIERS, ""
    if supplier_id:
        row.progress = {
            **row.progress,
            str(supplier_id): {"status": "analyzing", "messages_read": len(chat["messages"])},
        }
    row.temp_transcript, row.heartbeat_at = chat, timezone.now()
    row.save()
    _enqueue("import")


def template_style() -> str:
    """The template version the seed loaded, or the file if the database has none."""
    version = StyleVersion.objects.filter(source=StyleVersion.Source.TEMPLATE).first()
    return version.style_md if version else load_template()


@transaction.atomic
def load_template_draft(*, actor) -> None:
    require_role(actor, "manager")
    row = _lock_row()
    row.draft_style_md, row.draft_notes = template_style(), {}
    row.draft_source = StyleVersion.Source.TEMPLATE
    row.status, row.progress, row.error, row.step = OnboardingStyle.Status.DRAFT, {}, "", ""
    row.save()


@transaction.atomic
def save_draft(*, style_md: str, notes: list[dict], actor) -> None:
    require_role(actor, "manager")
    row = _lock_row()
    row.draft_style_md = style_md
    row.draft_notes = {str(item["supplier_id"]): item.get("notes") or "" for item in notes}
    row.status = OnboardingStyle.Status.DRAFT
    row.save()


# --- Task side --------------------------------------------------------------------------------


def _progress_writer():
    """`on_progress` for the persona pipeline: writes the row and the heartbeat."""

    def on_progress(supplier_id, status, messages_read=None, error=None):
        row = OnboardingStyle.load()
        if supplier_id is None:
            if status == "merging":
                row.step = OnboardingStyle.Step.MERGING
        else:
            entry = dict(row.progress.get(str(supplier_id)) or {})
            entry["status"] = status
            if messages_read is not None:
                entry["messages_read"] = messages_read
            if error:
                entry["error"] = error
            row.progress = {**row.progress, str(supplier_id): entry}
        row.heartbeat_at = timezone.now()
        row.save(update_fields=["progress", "step", "heartbeat_at", "updated_at"])

    return on_progress


def _text_of(message: dict) -> str:
    """Text or caption of a raw Evolution message; media without caption as a placeholder."""
    message = message or {}
    if message.get("conversation"):
        return message["conversation"]
    if (message.get("extendedTextMessage") or {}).get("text"):
        return message["extendedTextMessage"]["text"]
    for kind, label in (
        ("imageMessage", "[imagen]"),
        ("videoMessage", "[video]"),
        ("audioMessage", "[audio]"),
        ("documentMessage", "[archivo]"),
        ("stickerMessage", "[sticker]"),
    ):
        if kind in message:
            caption = (message.get(kind) or {}).get("caption")
            return f"{label} {caption}" if caption else label
    return ""


def chat_from_evolution(
    raw_messages: list[dict], agent_ids: set[str]
) -> tuple[list[dict], set, set]:
    """`(messages, contact_names, manager_names)` from `find_messages` output."""
    messages, contacts, managers = [], set(), set()
    for raw in raw_messages:
        key = raw.get("key") or {}
        text = _text_of(raw.get("message"))
        if not text:
            continue
        push_name = (raw.get("pushName") or "").strip()
        if key.get("fromMe"):
            sender = "agent" if key.get("id") in agent_ids else "manager"
            if push_name and sender == "manager":
                managers.add(push_name)
        else:
            sender = "supplier"
            if push_name:
                contacts.add(push_name)
        sent_at = datetime.fromtimestamp(int(raw.get("messageTimestamp") or 0), tz=LIMA)
        messages.append({"sender": sender, "text": text, "sent_at": sent_at.isoformat()})
    return messages, contacts, managers


def _manager_names() -> set[str]:
    user = Config.load().agent_user
    if user is None:
        return set()
    return {name for name in (user.first_name, user.get_full_name()) if name}


def _read_whatsapp_chats(row: OnboardingStyle, on_progress) -> tuple[list[dict], set[str]]:
    from messaging.evolution import EvolutionError, find_messages

    from messaging.models import Message

    since_at = datetime(row.since.year, row.since.month, row.since.day, tzinfo=LIMA)
    chats, manager_names = [], _manager_names()
    for supplier in _active_suppliers().filter(id__in=[int(k) for k in row.progress]):
        if row.progress[str(supplier.id)].get("status") != "pending":
            continue
        on_progress(supplier.id, "reading")
        read = 0
        try:
            for number in supplier.numbers.filter(active=True, simulated=False):
                raw = find_messages(number.jid, since_at)
                ids = {(r.get("key") or {}).get("id") for r in raw}
                agent_ids = set(
                    Message.objects.filter(
                        author=Message.Author.AGENT, external_id__in=ids
                    ).values_list("external_id", flat=True)
                )
                messages, contacts, managers = chat_from_evolution(raw, agent_ids)
                manager_names |= managers
                read += len(messages)
                chats.append(
                    {
                        "supplier_id": supplier.id,
                        "supplier_name": supplier.name,
                        "contact_names": sorted({number.name, *contacts} - {""}),
                        "messages": messages,
                    }
                )
        except EvolutionError as exc:
            on_progress(supplier.id, "error", messages_read=read, error=f"No se pudo leer: {exc}")
            continue
        on_progress(supplier.id, "reading", messages_read=read)
    return chats, manager_names


def run_extraction(mode: str) -> None:
    """Body of the `run_style_extraction` task; the caller holds `style_lock()`."""
    row = OnboardingStyle.load()
    if row.status != OnboardingStyle.Status.EXTRACTING:
        return
    on_progress = _progress_writer()
    result, error = None, ""
    try:
        if mode == "import":
            current = row.draft_style_md or template_style()
            notes = {int(k): v for k, v in row.draft_notes.items()}
            result = update_style(current, notes, [row.temp_transcript], on_progress=on_progress)
        else:
            chats, manager_names = _read_whatsapp_chats(row, on_progress)
            result = extract_style(chats, row.since, on_progress, tuple(manager_names))
    except StyleError as exc:
        error = str(exc)
    except Exception:
        error = "Falló la extracción. Vuelve a intentarlo."
        raise  # after `finally` records it, so the worker logs the traceback
    finally:
        _finish(result, error)


def _finish(result: dict | None, error: str) -> None:
    row = OnboardingStyle.load()
    if result is not None:
        row.draft_style_md = result["style_md"]
        row.draft_notes = {str(k): v for k, v in result["notes"].items()}
        row.draft_source = StyleVersion.Source.ONBOARDING
        row.status, row.error = OnboardingStyle.Status.DRAFT, ""
    else:
        row.status, row.error = OnboardingStyle.Status.ERROR, error
    row.temp_transcript, row.step = None, ""
    row.save()
