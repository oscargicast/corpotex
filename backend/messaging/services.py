"""The turn queue and the messaging services (ADR 0010, 0016, 0017, 0018, 0020).

`Turn` is the source of truth: at most one `pending` per conversation, `claim_next_turn` takes it
with a row lock, `finish_turn` marks exactly what the batch carried. Celery only dispatches."""

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from celery import current_app
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core import clock
from core.models import Config, User
from operations.models import ProgressReport, PurchaseOrder
from suppliers.models import Supplier

from .exceptions import ForeignPurchaseOrder, NumberNotAllowed, SendFailed
from .models import AllowedNumber, Conversation, Message, Turn

logger = logging.getLogger(__name__)

BATCH_DELAY = timedelta(seconds=5)
BATCH_CAP = timedelta(seconds=20)
STALE_RUNNING = timedelta(minutes=10)
MAX_ATTEMPTS = 3
QUIET_HOURS = getattr(settings, "QUIET_HOURS", (21, 7))  # The manager never writes first at night.


@dataclass
class TurnBatch:
    turn: Turn
    message_ids: list[int] = field(default_factory=list)
    decision_ids: list[int] = field(default_factory=list)
    follow_up_purchase_order_ids: list[int] = field(default_factory=list)
    new_purchase_order_ids: list[int] = field(default_factory=list)
    alert_ids: list[int] = field(default_factory=list)
    web_report_ids: list[int] = field(default_factory=list)
    follow_up: dict | None = None  # {kind, reason, mode, purchase_orders: {id: {kind, reason}}}; the tick's or a person's request (ADR 0027)
    follow_up_request_ids: list[int] = field(default_factory=list)  # asked requests the supplier may be answering (ADR 0027 §6)

    def is_empty(self) -> bool:
        return not any(
            (self.message_ids, self.decision_ids, self.follow_up_purchase_order_ids,
             self.new_purchase_order_ids, self.alert_ids, self.web_report_ids)
        )

    def is_proactive_only(self) -> bool:
        return not (self.message_ids or self.decision_ids or self.web_report_ids or self.alert_ids) and bool(
            self.follow_up_purchase_order_ids or self.new_purchase_order_ids
        )


# --- conversations --------------------------------------------------------------------------


def dashboard_conversation(user: User) -> Conversation:
    conversation, _ = Conversation.objects.get_or_create(channel=Conversation.Channel.DASHBOARD, user=user)
    return conversation


def conversation_for_number(number: AllowedNumber, channel: str) -> Conversation:
    conversation, _ = Conversation.objects.get_or_create(channel=channel, allowed_number=number)
    return conversation


def conversation_for_supplier(supplier: Supplier) -> Conversation | None:
    """Where proactive turns go (ADR 0016): the conversation with the most recent inbound
    message among the supplier's active numbers; else a new one for the first active number,
    real ones before simulated (WhatsApp beats the simulator, D1 finding of 10/10); None
    without active numbers."""
    numbers = list(supplier.numbers.filter(active=True).order_by("simulated", "id"))
    if not numbers:
        return None
    latest = (
        Message.objects.filter(conversation__allowed_number__in=numbers, author=Message.Author.SUPPLIER)
        .order_by("-sent_at")
        .select_related("conversation")
        .first()
    )
    if latest:
        return latest.conversation
    number = numbers[0]
    channel = Conversation.Channel.SIMULATOR if number.simulated else Conversation.Channel.WHATSAPP
    return conversation_for_number(number, channel)


# --- queue ----------------------------------------------------------------------------------


def enqueue_turn(conversation: Conversation, reason: str) -> Turn:
    """The only entry to the queue. Reuses the pending turn; pushes `available_at` 5 s ahead
    (cap 20 s from creation) so consecutive messages are batched; the dashboard waits nothing.
    Dispatches `run_turn` when the transaction commits."""
    now = timezone.now()
    if reason == Turn.Reason.MESSAGE and conversation.channel != Conversation.Channel.DASHBOARD:
        clear_awaiting_reply(conversation)
    with transaction.atomic():
        turn = Turn.objects.select_for_update().filter(conversation=conversation, status=Turn.Status.PENDING).first()
        if turn is None:
            available = now if conversation.channel == Conversation.Channel.DASHBOARD else now + BATCH_DELAY
            turn = Turn.objects.create(conversation=conversation, reason=reason, available_at=available)
        elif conversation.channel != Conversation.Channel.DASHBOARD:
            turn.available_at = min(now + BATCH_DELAY, turn.created_at + BATCH_CAP)
            turn.save(update_fields=["available_at", "updated_at"])
        countdown = max(0.0, (turn.available_at - now).total_seconds())
        transaction.on_commit(lambda: dispatch_turn(conversation.id, countdown))
    return turn


def clear_awaiting_reply(conversation: Conversation) -> int:
    """The supplier wrote: their open orders stop waiting for an answer (ADR 0027 §2)."""
    number = conversation.allowed_number
    if number is None or number.supplier_id is None:
        return 0
    return PurchaseOrder.objects.filter(supplier_id=number.supplier_id, status__in=PurchaseOrder.OPEN_STATUSES).exclude(
        awaiting_reply_since=None, reminded_at=None
    ).update(awaiting_reply_since=None, reminded_at=None)


def dispatch_turn(conversation_id: int, countdown: float = 0.0) -> None:
    """By task name: `messaging` never imports `agent`."""
    try:
        current_app.send_task("agent.tasks.run_turn", args=[conversation_id], countdown=countdown, queue="turns")
    except Exception:  # The broker is down; the tick's sweep retries.
        logger.exception("dispatch_turn: could not send run_turn for conversation %s", conversation_id)


def _paused() -> bool:
    return bool(Config.load().claude_last_error)


def _in_follow_up_window() -> bool:
    from manager.follow_up import in_window

    return in_window(clock.now(), Config.load())


def _night_for_requests() -> bool:
    """`QUIET_HOURS`, or 21-7 when it is off in `.env`: a person's request never wakes a supplier."""
    start, end = QUIET_HOURS or (21, 7)
    hour = timezone.localtime(clock.now()).hour
    return hour >= start or hour < end


def _quiet_hours() -> bool:
    if not QUIET_HOURS:
        return False  # Disabled from .env (QUIET_HOURS=).
    start, end = QUIET_HOURS
    hour = timezone.localtime(clock.now()).hour
    return hour >= start or hour < end


def claim_next_turn(conversation_id: int | None = None) -> TurnBatch | None:
    """Takes one available turn (row lock, skip locked) for a conversation without another
    `running` turn. Nothing is handed out while Claude is disconnected. A batch that turns out
    empty is closed without calling the model; a proactive-only WhatsApp batch waits for the
    manager's hours."""
    if _paused():
        return None
    now = timezone.now()
    with transaction.atomic():
        qs = Turn.objects.select_for_update(skip_locked=True).filter(
            status=Turn.Status.PENDING, available_at__lte=now
        ).exclude(conversation__turns__status=Turn.Status.RUNNING)
        if conversation_id is not None:
            qs = qs.filter(conversation_id=conversation_id)
        turn = qs.order_by("available_at", "id").first()
        if turn is None:
            return None
        batch = _build_batch(turn)
        if batch.is_empty():
            turn.status = Turn.Status.DONE
            turn.save(update_fields=["status", "updated_at"])
            return None
        requested = (batch.follow_up or {}).get("kind") == "requested"
        channel = turn.conversation.channel
        if batch.follow_up and not requested and batch.is_proactive_only() and not _in_follow_up_window():
            return None  # the tick's follow-up goes only inside the window set by the manager
        if requested and channel == Conversation.Channel.WHATSAPP and batch.is_proactive_only() and _night_for_requests():
            return None  # a person's request skips window and mode, not the night on a real number
        if not batch.follow_up and channel != Conversation.Channel.DASHBOARD and batch.is_proactive_only() and _quiet_hours():
            return None  # the first contact keeps QUIET_HOURS
        turn.status = Turn.Status.RUNNING
        turn.attempts += 1
        turn.save(update_fields=["status", "attempts", "updated_at"])
    return batch


def _build_batch(turn: Turn) -> TurnBatch:
    conversation = turn.conversation
    batch = TurnBatch(turn=turn)
    batch.message_ids = list(
        conversation.messages.filter(status=Message.Status.RECEIVED).order_by("sent_at", "id").values_list("id", flat=True)
    )
    if conversation.channel == Conversation.Channel.DASHBOARD:
        from manager.models import AlertNotification

        batch.alert_ids = list(
            AlertNotification.objects.filter(user=conversation.user, sent_at__isnull=True, alert__status="open")
            .order_by("alert_id")
            .values_list("alert_id", flat=True)
            .distinct()
        )
        return batch
    from manager.models import Decision

    batch.decision_ids = list(
        Decision.objects.filter(conversation=conversation, communicated_at__isnull=True)
        .exclude(status="pending")
        .values_list("id", flat=True)
    )
    open_pos = PurchaseOrder.objects.filter(conversation=conversation)
    if turn.follow_up:
        wanted = [int(i) for i in (turn.follow_up.get("purchase_orders") or {})]
        batch.follow_up_purchase_order_ids = list(
            PurchaseOrder.objects.filter(id__in=wanted, status__in=PurchaseOrder.OPEN_STATUSES).values_list("id", flat=True)
        )
        if batch.follow_up_purchase_order_ids:
            batch.follow_up = turn.follow_up
    batch.new_purchase_order_ids = list(open_pos.filter(status=PurchaseOrder.Status.APPROVED).values_list("id", flat=True))
    batch.web_report_ids = list(
        ProgressReport.objects.filter(purchase_order__conversation=conversation, message__isnull=True, acknowledged_at__isnull=True)
        .values_list("id", flat=True)
    )
    number = conversation.allowed_number
    if (batch.message_ids or batch.web_report_ids) and number is not None and number.supplier_id:
        from operations.follow_up_requests import open_request_ids_for_supplier

        batch.follow_up_request_ids = open_request_ids_for_supplier(number.supplier_id)
    return batch


def finish_turn(batch: TurnBatch, session_id: str | None, error: str | None = None) -> Turn:
    """Marks only what the batch carried. The session id is kept even on error so a retry
    resumes the same thread. Errors re-queue (inheriting attempts); the third one gives up."""
    turn = batch.turn
    conversation = turn.conversation
    now = timezone.now()
    with transaction.atomic():
        if session_id and conversation.agent_session != session_id:
            conversation.agent_session = session_id
            conversation.save(update_fields=["agent_session", "updated_at"])
        if error is None:
            Message.objects.filter(id__in=batch.message_ids).update(status=Message.Status.PROCESSED)
            if batch.decision_ids:
                from manager.models import Decision

                Decision.objects.filter(id__in=batch.decision_ids).update(communicated_at=clock.now())
            if batch.follow_up:
                _close_follow_up(batch, sent=Message.objects.filter(turn=turn, author=Message.Author.AGENT).exists())
            from operations.services import set_status

            for po in PurchaseOrder.objects.filter(id__in=batch.new_purchase_order_ids, status=PurchaseOrder.Status.APPROVED):
                set_status(po, PurchaseOrder.Status.NEGOTIATING, actor="agent", note="Primer contacto enviado")
            if batch.alert_ids:
                from manager.models import AlertNotification

                AlertNotification.objects.filter(user=conversation.user, alert_id__in=batch.alert_ids, sent_at__isnull=True).update(sent_at=now)
                from manager.models import Alert

                Alert.objects.filter(id__in=batch.alert_ids, kind="follow_up_answered", status="open").update(status="resolved", resolved_at=clock.now())
            ProgressReport.objects.filter(id__in=batch.web_report_ids).update(acknowledged_at=now)
            turn.status = Turn.Status.DONE
            turn.error = ""
            turn.save(update_fields=["status", "error", "updated_at"])
        else:
            turn.status = Turn.Status.ERROR
            turn.error = error[:500]
            turn.save(update_fields=["status", "error", "updated_at"])
            if turn.attempts >= MAX_ATTEMPTS:
                from manager.services import open_alert

                if batch.follow_up:  # counts as the day's follow-up: the tick must not retry it every minute
                    PurchaseOrder.objects.filter(id__in=batch.follow_up_purchase_order_ids).update(last_follow_up_on=clock.today())

                Message.objects.filter(id__in=batch.message_ids).update(status=Message.Status.ERROR, error=turn.error)
                open_alert("turn_failed", text=f"El agente falló 3 veces en la conversación {conversation.id}: {turn.error[:120]}")
            else:
                _requeue(turn)
        pending = Turn.objects.filter(conversation=conversation, status=Turn.Status.PENDING).first()
        if pending:
            countdown = max(0.0, (pending.available_at - now).total_seconds())
            transaction.on_commit(lambda: dispatch_turn(conversation.id, countdown))
    return turn


def _close_follow_up(batch: TurnBatch, *, sent: bool) -> None:
    """ADR 0027 §3, agreed with `agente`: the day's follow-up is spent whether the agent wrote or
    skipped (`skip_follow_up` leaves `follow_up_note`). A message sent without a supplier message
    in the batch starts the wait (checkpoint) or marks the reminder. A skipped reminder is marked
    too but keeps the wait: not insisting with the supplier must not hide the silence from the
    manager, so the stalled alert still comes (agreed with `agente`, 11/10 01:40)."""
    now = clock.now()
    per_order = (batch.follow_up or {}).get("purchase_orders") or {}
    answered = bool(batch.message_ids)
    requested = []
    for po in PurchaseOrder.objects.filter(id__in=batch.follow_up_purchase_order_ids):
        kind = (per_order.get(str(po.id)) or {}).get("kind") or batch.follow_up.get("kind")
        po.last_follow_up_on = clock.today()
        fields = ["last_follow_up_on", "updated_at"]
        if sent:
            po.follow_up_note = ""
            po.last_follow_up_kind, po.last_follow_up_at = kind, now
            fields += ["follow_up_note", "last_follow_up_kind", "last_follow_up_at"]
            if kind == "requested":  # a person asked: the wait starts even if the supplier was writing
                po.awaiting_reply_since, po.reminded_at = now, None
                fields += ["awaiting_reply_since", "reminded_at"]
            elif not answered:
                if kind == "reminder":
                    po.reminded_at = now
                    fields.append("reminded_at")
                else:
                    po.awaiting_reply_since, po.reminded_at = now, None
                    fields += ["awaiting_reply_since", "reminded_at"]
        elif kind == "reminder":
            po.reminded_at = now
            fields.append("reminded_at")
        po.save(update_fields=fields)
        if kind == "requested":
            requested.append(po.id)
    if requested:
        from operations.follow_up_requests import mark_asked

        mark_asked(requested, sent=sent)


def _requeue(turn: Turn, *, count_attempt: bool = True) -> Turn:
    conversation = turn.conversation
    pending = Turn.objects.filter(conversation=conversation, status=Turn.Status.PENDING).first()
    if pending is None:
        pending = Turn.objects.create(
            conversation=conversation,
            reason=turn.reason,
            attempts=turn.attempts if count_attempt else max(0, turn.attempts - 1),
            available_at=timezone.now(),
        )
    return pending


def recover_stuck_turns() -> int:
    """Turns left `running` by a dead worker go back to the queue without counting an attempt."""
    with transaction.atomic():
        stuck = list(Turn.objects.select_for_update().filter(status=Turn.Status.RUNNING))
        for turn in stuck:
            turn.status = Turn.Status.ERROR
            turn.error = "worker restarted"
            turn.save(update_fields=["status", "error", "updated_at"])
            pending = _requeue(turn, count_attempt=False)
            transaction.on_commit(lambda cid=pending.conversation_id: dispatch_turn(cid))
    if stuck:
        logger.warning("recover_stuck_turns: requeued %d turn(s)", len(stuck))
    return len(stuck)


def sweep_turns() -> int:
    """The tick: dispatches available pending turns (in case Redis lost a task) and fails turns
    running for too long."""
    now = timezone.now()
    for turn in Turn.objects.filter(status=Turn.Status.RUNNING, updated_at__lt=now - STALE_RUNNING):
        finish_turn(TurnBatch(turn=turn), None, error="timeout: running for more than 10 minutes")
    if _paused():
        return 0
    count = 0
    for turn in Turn.objects.filter(status=Turn.Status.PENDING, available_at__lte=now).exclude(
        conversation__turns__status=Turn.Status.RUNNING
    ):
        dispatch_turn(turn.conversation_id)
        count += 1
    return count


# --- turn state -----------------------------------------------------------------------------


def turn_state(batch: TurnBatch, *, with_history: bool = False) -> dict:
    """Fresh state for the WhatsApp agent. Keys agreed with `personalidad`; never the
    customer's name, the promised date nor the buffer."""
    conversation = batch.turn.conversation
    number = conversation.allowed_number
    supplier = number.supplier if number else None
    config = Config.load()
    style_md = config.agent_user.style_md if config.agent_user_id else ""
    from manager import follow_up

    pos = (
        PurchaseOrder.objects.filter(supplier=supplier, status__in=PurchaseOrder.OPEN_STATUSES + ("suggested",))
        .select_related("supplier")
        .prefetch_related("items__requirement__material", "items__requirement__product", "status_changes", "progress_reports")
        if supplier
        else PurchaseOrder.objects.none()
    )
    from manager.models import Decision
    from suppliers.models import Rate

    def rate_for(po):
        item = po.items.first()
        if not item:
            return None
        rate = Rate.objects.filter(supplier=po.supplier, material=item.requirement.material, product=item.requirement.product).order_by("-valid_from").first()
        return str(rate.unit_price) if rate else None

    state = {
        "now": clock.now().isoformat(),
        "channel": conversation.channel,
        "supplier": {
            "name": supplier.name if supplier else "",
            "kind": supplier.kind if supplier else "",
            "city": supplier.city if supplier else "",
            "currency": supplier.currency if supplier else "PEN",
            "notes": supplier.notes if supplier else "",
            "contact_name": number.name if number and not number.simulated else "",
        },
        "purchase_orders": [
            {
                "code": po.code,
                "status": po.status,
                "status_display": po.get_status_display(),
                "items": [
                    {
                        "name": (i.requirement.material or i.requirement.product).name,
                        "quantity": str(i.quantity),
                        "unit_price": str(i.unit_price),
                    }
                    for i in po.items.all()
                ],
                "rate_unit_price": rate_for(po),
                "internal_due_on": po.internal_due_on.isoformat() if po.internal_due_on else None,
                "committed_on": po.committed_on.isoformat() if po.committed_on else None,
                "terms": po.terms,
                "units_done": _units_done(po),
                "report_link_sent_at": po.report_link_sent_at.isoformat() if po.report_link_sent_at else None,
                "is_follow_up": po.id in batch.follow_up_purchase_order_ids,
                "is_new": po.id in batch.new_purchase_order_ids,
                # ADR 0027 §3 (contract with `agente`)
                "follow_up_reason": ((batch.follow_up or {}).get("purchase_orders") or {}).get(str(po.id), {}).get("reason") if po.id in batch.follow_up_purchase_order_ids else None,
                "expected_units": follow_up.expected_units(po),
                "total_units": follow_up.total_units(po),
                "last_report_at": _iso(follow_up.last_report_at(po)),
                "awaiting_reply_since": _iso(po.awaiting_reply_since),
                "follow_up_note": po.follow_up_note,
            }
            for po in pos
        ],
        "decisions": [
            {
                "id": d.id,
                "kind": d.kind,
                "status": d.status,
                "summary": d.summary,
                "note": d.note,
                "purchase_order_codes": list(d.purchase_orders.values_list("code", flat=True)),
            }
            for d in Decision.objects.filter(id__in=batch.decision_ids)
        ],
        "new_messages": [
            {"id": m.id, "text": m.text, "media_url": m.media.url if m.media else None, "sent_at": m.sent_at.isoformat()}
            for m in Message.objects.filter(id__in=batch.message_ids).order_by("sent_at", "id")
        ],
        "web_reports": [
            {"purchase_order_code": r.purchase_order.code, "units_done": r.units_done, "reported_at": r.reported_at.isoformat()}
            for r in ProgressReport.objects.filter(id__in=batch.web_report_ids).select_related("purchase_order")
        ],
        "style_md": style_md,
        "manager_name": config.agent_user.first_name if config.agent_user_id else "",
    }
    if batch.follow_up:
        state["follow_up"] = _follow_up_context(batch, conversation, supplier, config)
    from operations.models import FollowUpRequest

    state["open_follow_up_requests"] = [
        {"id": r.id, "purchase_order_code": r.purchase_order.code, "asked_at": _iso(r.asked_at)}
        for r in FollowUpRequest.objects.filter(id__in=batch.follow_up_request_ids).select_related("purchase_order").order_by("asked_at", "id")
    ]
    if with_history:
        state["history"] = [
            {"sender": _sender(m), "text": m.text, "sent_at": m.sent_at.isoformat()} for m in message_history(conversation, 20)
        ]
    return state


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _follow_up_context(batch: TurnBatch, conversation: Conversation, supplier, config: Config) -> dict:
    """The top-level `follow_up` of a follow-up turn (ADR 0027 §3, contract with `agente`)."""
    from manager.follow_up import effective_mode
    from manager.models import Decision

    def last(author):
        message = conversation.messages.filter(author=author).order_by("-sent_at", "-id").first()
        return {"text": message.text, "sent_at": message.sent_at.isoformat()} if message else None

    supplier_message, agent_message = last(Message.Author.SUPPLIER), last(Message.Author.AGENT)
    pending = (
        Decision.objects.filter(status="pending", purchase_orders__supplier=supplier).distinct().order_by("created_at") if supplier else Decision.objects.none()
    )
    return {
        "mode": effective_mode(supplier, config) if supplier else config.follow_up_mode,
        "kind": batch.follow_up.get("kind"),
        "reason": batch.follow_up.get("reason"),
        "last_supplier_message_at": supplier_message["sent_at"] if supplier_message else None,
        "last_agent_message_at": agent_message["sent_at"] if agent_message else None,
        "last_supplier_message": supplier_message,
        "last_agent_message": agent_message,
        "pending_decisions": [
            {"kind": d.kind, "summary": d.summary, "purchase_order_codes": list(d.purchase_orders.values_list("code", flat=True)), "created_at": d.created_at.isoformat()}
            for d in pending
        ],
    }


def _sender(message: Message) -> str:
    return {"supplier": "supplier", "agent": "agent", "manager": "manager", "user": "user"}[message.author]


def _units_done(po: PurchaseOrder) -> int:
    latest = po.progress_reports.order_by("-reported_at", "-id").first()
    return latest.units_done if latest else 0


def assistant_turn_state(batch: TurnBatch, *, with_history: bool = False) -> dict:
    """State for the dashboard assistant: the user, the view they were on, their new messages
    and the alerts to tell them about, filtered by role (ADR 0017, 0020)."""
    from core.serializers import serializer_for
    from manager.models import Alert, AlertNotification

    conversation = batch.turn.conversation
    user = conversation.user
    messages = list(Message.objects.filter(id__in=batch.message_ids).order_by("sent_at", "id"))
    context = next((m.context for m in reversed(messages) if m.context), None)
    alerts = []
    for alert in Alert.objects.filter(id__in=batch.alert_ids).select_related("order", "purchase_order__supplier", "decision"):
        data = serializer_for(Alert, user.role)(alert, context={"role": user.role}).data
        data.pop("text", None)  # The model writes from structured data, never from Alert.text.
        data["decision"] = (
            {"id": alert.decision_id, "kind": alert.decision.kind, "summary": alert.decision.summary if user.role == "manager" else None}
            if alert.decision_id
            else None
        )
        data["repeat"] = AlertNotification.objects.filter(alert=alert, user=user, sent_at__isnull=False).exists()
        if alert.kind == "follow_up_answered":
            detail = alert.detail or {}
            data.update(
                {
                    "purchase_order": detail.get("purchase_order"),
                    "supplier_name": detail.get("supplier_name"),
                    "order_codes": detail.get("order_codes") or [],
                    "answer_summary": detail.get("answer_summary"),
                    "requested_at": detail.get("requested_at"),
                    "url": detail.get("url"),
                }
            )
            data.pop("detail", None)
        if alert.kind == "purchase_suggested":
            detail = alert.detail or {}
            with_prices = user.role == "manager"
            data.update(
                {
                    "material": {k: (detail.get("material") or {}).get(k) for k in ("id", "sku", "name", "unit")},
                    "total_to_order": detail.get("total_to_order"),
                    "orders": [{k: o.get(k) for k in ("code", "qty", "due_on")} for o in detail.get("orders") or []],
                    "suggested_supplier": detail.get("suggested_supplier"),
                    "reference_price": detail.get("reference_price") if with_prices else None,
                    "currency": detail.get("currency") if with_prices else None,
                }
            )
            data.pop("detail", None)
        alerts.append(data)
    state = {
        "now": clock.now().isoformat(),
        "user": {"first_name": user.first_name, "role": user.role},
        "context": context,
        "new_messages": [{"id": m.id, "text": m.text, "sent_at": m.sent_at.isoformat()} for m in messages],
        "pending_action": conversation.pending_action,
        "alerts": alerts,
    }
    if with_history:
        state["history"] = [
            {"sender": _sender(m), "text": m.text, "sent_at": m.sent_at.isoformat()} for m in message_history(conversation, 20)
        ]
    return state


# --- messages -------------------------------------------------------------------------------


def message_history(conversation: Conversation, limit: int = 20):
    """The last `limit` messages, oldest first."""
    rows = list(conversation.messages.order_by("-sent_at", "-id")[:limit])
    rows.reverse()
    return rows


def latest_photo_id(message_ids) -> int | None:
    message = Message.objects.filter(id__in=message_ids).exclude(media="").order_by("-sent_at", "-id").first()
    return message.id if message else None


def purchase_order_for_conversation(conversation: Conversation, code: str) -> PurchaseOrder:
    """The purchase order must belong to the conversation's supplier (any of its numbers)."""
    supplier = conversation.supplier
    po = PurchaseOrder.objects.filter(code=code).select_related("supplier").first()
    if po is None or supplier is None or po.supplier_id != supplier.id:
        raise ForeignPurchaseOrder(code)
    return po


def send_text(conversation: Conversation, text: str, turn: Turn | None) -> Message:
    """Saves the outgoing message and, on WhatsApp, sends it through Evolution. Re-checks the
    allowlist: an inactive or simulated number never gets a WhatsApp message."""
    number = conversation.allowed_number
    if number is None or not number.active:
        raise NumberNotAllowed(getattr(number, "phone", "?"))
    if conversation.channel == Conversation.Channel.WHATSAPP and number.simulated:
        raise NumberNotAllowed(number.phone)
    message = Message.objects.create(
        conversation=conversation, author=Message.Author.AGENT, text=text, status=Message.Status.SENT, sent_at=timezone.now(), turn=turn
    )
    if conversation.channel == Conversation.Channel.WHATSAPP:
        try:
            message.external_id = _evolution_send(number.phone, text) or None
            message.save(update_fields=["external_id", "updated_at"])
        except Exception as exc:
            message.status = Message.Status.FAILED
            message.error = str(exc)[:500]
            message.save(update_fields=["status", "error", "updated_at"])
            raise SendFailed(str(exc)) from exc
    return message


def _evolution_send(phone: str, text: str) -> str | None:
    """Thin wrapper over the orquestador's client (`messaging/evolution.py`)."""
    from messaging.evolution import EvolutionClient

    result = EvolutionClient.from_settings().send_text(phone, text)
    if isinstance(result, dict):
        key = result.get("key") or {}
        return key.get("id") or result.get("id")
    return result


def record_assistant_action(conversation: Conversation, turn: Turn, action: dict) -> Message:
    """A card for a tool that changed something: `text = title`."""
    return Message.objects.create(
        conversation=conversation,
        author=Message.Author.AGENT,
        text=action.get("title", ""),
        status=Message.Status.SENT,
        sent_at=timezone.now(),
        turn=turn,
        action={"kind": "tool", **action},
    )


def post_assistant_message(conversation: Conversation, turn: Turn | None, text: str, action: dict | None = None) -> Message:
    """The assistant's final answer (or an alert notice with `action = {kind: alert, alert_ids}`)."""
    return Message.objects.create(
        conversation=conversation,
        author=Message.Author.AGENT,
        text=text,
        status=Message.Status.SENT,
        sent_at=timezone.now(),
        turn=turn,
        action=action,
    )


def mark_assistant_read(conversation: Conversation, up_to_id: int) -> int:
    return conversation.messages.filter(author=Message.Author.AGENT, id__lte=up_to_id, read_at__isnull=True).update(read_at=timezone.now())


def unread_assistant_count(user: User) -> int:
    return Message.objects.filter(conversation__channel="dashboard", conversation__user=user, author=Message.Author.AGENT, read_at__isnull=True).count()
