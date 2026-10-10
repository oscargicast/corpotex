"""The manager's style in the database (ADR 0019): approve, roll back and refresh daily.

The approved style lives in `User.style_md` of `Config.agent_user`, with every change kept as
a `StyleVersion`. The daily refresh applies itself when it passes validation and never touches
`Supplier.notes`: per-supplier observations only go to the changelog as suggestions.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from agent.persona.style import StyleError, update_style, validate_style

from . import clock
from .models import Config, OnboardingStyle, StyleVersion, User
from .onboarding import StyleBusy, StyleInputError, is_running
from .permissions import require_role


class StyleInvalid(Exception):
    """The draft does not pass `validate_style`; carries the list of problems."""

    def __init__(self, errors: list[str]):
        super().__init__(" ".join(errors))
        self.errors = errors


def _supplier_names() -> tuple[str, ...]:
    from suppliers.models import Supplier

    return tuple(Supplier.objects.values_list("name", flat=True))


def style_owner(actor=None) -> User | None:
    """Whose style the WhatsApp agent uses: `Config.agent_user`, else the acting manager."""
    return Config.load().agent_user or actor


def _notes_snapshot() -> dict:
    from suppliers.models import Supplier

    return {
        str(pk): notes
        for pk, notes in Supplier.objects.exclude(notes="").values_list("id", "notes")
    }


@transaction.atomic
def approve_style(*, actor) -> StyleVersion | None:
    """Copy the draft to the agent user's style and to `Supplier.notes`. Idempotent."""
    from suppliers.models import Supplier

    require_role(actor, "manager")
    OnboardingStyle.load()
    row = OnboardingStyle.objects.select_for_update().get(pk=1)
    if row.status == OnboardingStyle.Status.APPROVED:
        return None
    if is_running(row):
        raise StyleBusy
    if not row.draft_style_md.strip():
        raise StyleInputError("No hay borrador para aprobar.")
    errors = validate_style(row.draft_style_md, _supplier_names())
    if errors:
        raise StyleInvalid(errors)

    owner = style_owner(actor)
    owner.style_md = row.draft_style_md
    owner.save(update_fields=["style_md"])
    for supplier_id, notes in row.draft_notes.items():
        Supplier.objects.filter(id=int(supplier_id)).update(notes=notes)
    version = StyleVersion.objects.create(
        user=owner,
        style_md=row.draft_style_md,
        notes_snapshot=_notes_snapshot(),
        source=row.draft_source or StyleVersion.Source.ONBOARDING,
        changelog="Aprobado en el onboarding.",
    )
    row.status, row.approved_at = OnboardingStyle.Status.APPROVED, timezone.now()
    row.save()
    return version


@transaction.atomic
def restore_style_version(version: StyleVersion, *, actor) -> StyleVersion:
    """Go back to `version`: a new `rollback` version, history is never rewritten."""
    from suppliers.models import Supplier

    require_role(actor, "manager")
    owner = version.user
    owner.style_md = version.style_md
    owner.save(update_fields=["style_md"])
    for supplier_id, notes in version.notes_snapshot.items():
        Supplier.objects.filter(id=int(supplier_id)).update(notes=notes)
    return StyleVersion.objects.create(
        user=owner,
        style_md=version.style_md,
        notes_snapshot=_notes_snapshot(),
        source=StyleVersion.Source.ROLLBACK,
        changelog=f"Vuelta a la versión del {timezone.localtime(version.created_at):%d/%m %H:%M}.",
    )


def _new_whatsapp_chats(since) -> list[dict]:
    """Messages since `since` of WhatsApp chats with active supplier numbers (read only)."""
    from messaging.models import Conversation, Message

    senders = {
        Message.Author.MANAGER: "manager",
        Message.Author.SUPPLIER: "supplier",
        Message.Author.AGENT: "agent",
    }
    conversations = Conversation.objects.filter(
        channel=Conversation.Channel.WHATSAPP,
        allowed_number__active=True,
        allowed_number__simulated=False,
        allowed_number__supplier__isnull=False,
    ).select_related("allowed_number__supplier")
    chats = []
    for conversation in conversations:
        number = conversation.allowed_number
        messages = [
            {"sender": senders[m.author], "text": m.text, "sent_at": m.sent_at}
            for m in conversation.messages.filter(sent_at__gte=since, author__in=senders)
            .exclude(text="")
            .order_by("sent_at")
        ]
        if any(m["sender"] == "manager" for m in messages):
            chats.append(
                {
                    "supplier_id": number.supplier_id,
                    "supplier_name": number.supplier.name,
                    "contact_names": [number.name] if number.name else [],
                    "messages": messages,
                }
            )
    return chats


def _alert_refresh_failed(error: str) -> None:
    from manager.models import Alert

    text = f"No se pudo actualizar el estilo del Gerente: {error}"[:300]
    try:
        from manager.services import open_alert
    except ImportError:  # until backend's manager services land
        Alert.objects.get_or_create(
            kind=Alert.Kind.STYLE_REFRESH_FAILED,
            status=Alert.Status.OPEN,
            defaults={"severity": Alert.Severity.WARNING, "text": text, "detected_at": clock.now()},
        )
        return
    open_alert(Alert.Kind.STYLE_REFRESH_FAILED, text=text)


def refresh_style(user_id: int | None = None) -> StyleVersion | None:
    """Daily refresh (ADR 0019). Returns the new `daily` version, or None if nothing changed.

    The caller holds `style_lock()`. Reads only our database, never Evolution.
    """
    owner = User.objects.filter(id=user_id).first() if user_id else Config.load().agent_user
    if owner is None or not owner.style_md:
        return None
    started = timezone.now()
    since = owner.style_refreshed_at or started - timedelta(days=1)
    try:
        chats = _new_whatsapp_chats(since)
        if not chats:
            return None
        manager_names = tuple(n for n in (owner.first_name, owner.get_full_name()) if n)
        result = update_style(owner.style_md, {}, chats, manager_names=manager_names)
        if result["style_md"] == owner.style_md and not result["changelog"]:
            return None
        owner.style_md = result["style_md"]
        owner.save(update_fields=["style_md"])
        return StyleVersion.objects.create(
            user=owner,
            style_md=result["style_md"],
            notes_snapshot=_notes_snapshot(),
            source=StyleVersion.Source.DAILY,
            changelog="\n".join(result["changelog"]),
        )
    except StyleError as exc:
        _alert_refresh_failed(str(exc))
        return None
    finally:
        User.objects.filter(id=owner.id).update(style_refreshed_at=started)
