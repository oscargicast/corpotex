"""Reactive follow-up (ADR 0027 §6): Comercial, Producción or the Gerente ask for progress of a
purchase order or of every open one of an order. The agent asks the supplier (a `follow_up` turn
with `kind = "requested"`, outside the window and the mode: a person asked), unless the order is
already waiting for an answer: then the request hangs on that wait. The supplier's answer goes
back, summarised, to the assistant of whoever asked."""

from collections import OrderedDict
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from core import clock

from .models import FollowUpRequest, PurchaseOrder

BRAKE = timedelta(hours=2)
NIGHT = (21, 7)  # a person's request to a real WhatsApp waits for the morning, even with QUIET_HOURS off
ROLE_LABELS = {"manager": "Gerente", "sales": "Comercial", "production": "Producción"}


def role_label(user) -> str:
    return ROLE_LABELS.get(getattr(user, "role", None), "El equipo")


def open_purchase_orders_of_order(order):
    return (
        PurchaseOrder.objects.filter(items__requirement__order=order, status__in=PurchaseOrder.OPEN_STATUSES)
        .select_related("supplier", "conversation")
        .distinct()
        .order_by("supplier_id", "committed_on", "id")
    )


def waiting_since(po: PurchaseOrder, now=None):
    """The original question this order is still waiting on: an unanswered follow-up, or a
    request asked less than 2 h ago. None when nobody is waiting."""
    now = now or clock.now()
    if po.awaiting_reply_since:
        return po.awaiting_reply_since
    recent = po.follow_up_requests.filter(status=FollowUpRequest.Status.ASKED, asked_at__gte=now - BRAKE).order_by("-asked_at").first()
    return recent.asked_at if recent else None


def channel_for(po: PurchaseOrder):
    """The conversation to ask through, or None: the own plant and suppliers without an active
    number (real or simulated) get no message."""
    from messaging.services import conversation_for_supplier

    if po.supplier.is_in_house:
        return None
    if po.conversation and po.conversation.allowed_number_id and po.conversation.allowed_number.active:
        return po.conversation
    return conversation_for_supplier(po.supplier)


def quiet_until(conversation, now):
    """Night on a real WhatsApp: the hour the request may go (07:00), else None. The simulator
    answers at once (orquestador, 11/10)."""
    from messaging.models import Conversation
    from messaging.services import QUIET_HOURS

    if conversation.channel != Conversation.Channel.WHATSAPP:
        return None
    start, end = QUIET_HOURS or NIGHT
    local = timezone.localtime(now)
    if not (local.hour >= start or local.hour < end):
        return None
    day = local.date() if local.hour < end else local.date() + timedelta(days=1)
    return timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time().replace(hour=end)))


def request_follow_up(purchase_orders, *, actor, subject: str, dry_run: bool = False) -> dict:
    """One request per open purchase order. Orders already waiting hang on that wait (`asked`,
    with the original time) and queue nothing; the rest go in one `requested` turn per supplier.
    `dry_run` (the assistant's preview) creates and queues nothing."""
    from messaging.services import agent_paused_for

    now = clock.now()
    reason = f"{role_label(actor)} pide avance de {subject}"
    rows, to_ask = [], OrderedDict()
    with transaction.atomic():
        for po in purchase_orders:
            if po.status not in PurchaseOrder.OPEN_STATUSES:
                continue
            conversation = channel_for(po)
            paused = conversation is not None and agent_paused_for(conversation)
            if paused:
                conversation = None  # ADR 0030: nothing goes to a paused supplier
            original = waiting_since(po, now) if conversation else None
            if paused:
                status, skip_reason = FollowUpRequest.Status.SKIPPED, "agente en pausa"
            elif conversation is None:
                status, skip_reason = FollowUpRequest.Status.SKIPPED, "sin canal"
            else:
                status, skip_reason = (FollowUpRequest.Status.ASKED if original else FollowUpRequest.Status.PENDING), ""
            request = None
            if not dry_run:
                request = FollowUpRequest.objects.create(
                    purchase_order=po, requested_by=actor, requested_at=now, status=status, asked_at=original, skip_reason=skip_reason
                )
            later = None
            if conversation and not original:
                later = quiet_until(conversation, now)
                to_ask.setdefault(conversation.id, (conversation, later, []))[2].append(po)
            rows.append(
                {
                    "id": request.id if request else None,
                    "purchase_order": {"id": po.id, "code": po.code},
                    "supplier_name": po.supplier.name,
                    "status": status,
                    "asked_at": original,
                    "already_asked": bool(original),
                    "skip_reason": skip_reason,
                    "channel": conversation.channel if conversation else None,
                    "in_house": po.supplier.is_in_house,
                    "goes_at": later,
                }
            )
        if not dry_run:
            for conversation, later, pos in to_ask.values():
                _enqueue_requested(conversation, pos, actor=actor, reason=reason, available_at=later)
    detail = _detail(rows, dry_run)
    for row in rows:
        row.pop("in_house"), row.pop("goes_at")
    return {"requests": rows, "detail": detail}


def _detail(rows: list[dict], dry_run: bool) -> str:
    if not rows:
        return "No hay pedidos abiertos a los que pedirles avance."
    waiting = [r for r in rows if r["already_asked"]]
    asking = sorted({r["supplier_name"] for r in rows if r["status"] == FollowUpRequest.Status.PENDING and not r["goes_at"]})
    morning = sorted({(r["supplier_name"], timezone.localtime(r["goes_at"]).strftime("%H:%M")) for r in rows if r["status"] == FollowUpRequest.Status.PENDING and r["goes_at"]})
    parts = []
    if asking:
        parts.append(("Le escribiría a " if dry_run else "Le pedimos avance a ") + _join(asking) + ".")
    for name, at in morning:
        parts.append(f"A {name} se le escribirá a las {at}: de noche no se le escribe a los proveedores.")  # never names the channel (#119)
    for name in sorted({r["supplier_name"] for r in rows if r["status"] == FollowUpRequest.Status.SKIPPED and r["in_house"]}):
        parts.append(f"A {name} no se le escribe: es la planta propia.")
    skipped = [r for r in rows if r["status"] == FollowUpRequest.Status.SKIPPED and not r["in_house"]]
    for name in sorted({r["supplier_name"] for r in skipped if r["skip_reason"] == "agente en pausa"}):
        parts.append(f"A {name} no se le escribe: el agente está en pausa.")
    for name in sorted({r["supplier_name"] for r in skipped if r["skip_reason"] != "agente en pausa"}):
        parts.append(f"A {name} no se le puede escribir: no tiene número.")
    for row in waiting:
        when = timezone.localtime(row["asked_at"])
        at = f"a las {when:%H:%M}" if when.date() == timezone.localdate() else f"el {when:%d/%m} a las {when:%H:%M}"
        parts.append(f"A {row['supplier_name']} ya se le preguntó {at} por {row['purchase_order']['code']}; te avisamos en el asistente cuando conteste.")
    return " ".join(parts)


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " y " + names[-1]


def _enqueue_requested(conversation, pos: list[PurchaseOrder], *, actor, reason: str, available_at=None) -> None:
    from manager.follow_up import effective_mode
    from messaging.models import Turn
    from messaging.services import enqueue_turn

    supplier = pos[0].supplier
    for po in pos:
        if po.conversation_id != conversation.id:
            po.conversation = conversation
            po.save(update_fields=["conversation", "updated_at"])
    turn = enqueue_turn(conversation, "follow_up")
    payload = dict(turn.follow_up or {})
    orders = dict(payload.get("purchase_orders") or {})
    for po in pos:
        orders[str(po.id)] = {"kind": "requested", "reason": reason}
    earlier = payload.get("reason") if payload.get("kind") not in (None, "requested") else None
    payload.update(
        kind="requested",
        reason=f"{reason}; {earlier}" if earlier else reason,
        mode=effective_mode(supplier),
        requested_by=actor.id if actor else None,
        purchase_orders=orders,
    )
    turn.follow_up = payload
    fields = ["follow_up", "updated_at"]
    if available_at and turn.reason == Turn.Reason.FOLLOW_UP and turn.available_at < available_at:
        turn.available_at = available_at  # night on WhatsApp: the sweep dispatches it at 07:00
        fields.append("available_at")
    turn.save(update_fields=fields)


def mark_asked(purchase_order_ids, *, sent_at=None) -> None:
    """Closing a `requested` turn: the pending requests become `asked`, at the time of the agent's
    message when it wrote, else at the time of the wait they hang on."""
    now = clock.now()
    for po in PurchaseOrder.objects.filter(id__in=purchase_order_ids):
        asked_at = sent_at or po.awaiting_reply_since or now
        po.follow_up_requests.filter(status=FollowUpRequest.Status.PENDING).update(status=FollowUpRequest.Status.ASKED, asked_at=asked_at)


def open_request_ids_for_supplier(supplier_id) -> list[int]:
    return list(
        FollowUpRequest.objects.filter(
            status=FollowUpRequest.Status.ASKED, purchase_order__supplier_id=supplier_id, purchase_order__status__in=PurchaseOrder.OPEN_STATUSES
        )
        .order_by("asked_at", "id")
        .values_list("id", flat=True)
    )


def answer_follow_up_requests(request_ids, *, summary: str) -> int:
    """The supplier answered (agent's `answer_follow_up`): the requests become `answered` and
    whoever asked gets a notice in their assistant with the summary and the order's link."""
    now = clock.now()
    summary = (summary or "").strip()[:300]
    answered = 0
    notified = set()
    requests = FollowUpRequest.objects.filter(id__in=request_ids, status__in=(FollowUpRequest.Status.PENDING, FollowUpRequest.Status.ASKED)).select_related(
        "purchase_order__supplier", "requested_by"
    )
    with transaction.atomic():
        for request in requests:
            request.status = FollowUpRequest.Status.ANSWERED
            request.answered_at = now
            request.answer_summary = summary
            request.save(update_fields=["status", "answered_at", "answer_summary", "updated_at"])
            # The supplier answered: nobody waits on this order any more, whatever the race between
            # the question's closing and the reply (orquestador, 11/10 01:05).
            PurchaseOrder.objects.filter(pk=request.purchase_order_id).update(awaiting_reply_since=None, reminded_at=None)
            answered += 1
            key = (request.requested_by_id, request.purchase_order_id)
            if request.requested_by_id and request.requested_by.is_active and key not in notified:
                notified.add(key)
                _notify_answer(request, summary)
    return answered


def _notify_answer(request: FollowUpRequest, summary: str) -> None:
    """One `follow_up_answered` alert for the person who asked, and their assistant turn (ADR 0020
    style). It resolves itself once the assistant tells them."""
    from manager.models import Alert, AlertNotification
    from messaging.services import dashboard_conversation, enqueue_turn

    po = request.purchase_order
    order_codes = sorted(set(po.items.values_list("requirement__order__code", flat=True)))
    text = f"{po.supplier.name} respondió sobre {po.code}" + (f" ({', '.join(order_codes)})" if order_codes else "") + f": {summary}"
    alert = Alert.objects.create(
        kind="follow_up_answered",
        severity="info",
        purchase_order=po,
        text=text[:300],
        detail={
            "request_id": request.id,
            "purchase_order": {"id": po.id, "code": po.code},
            "supplier_name": po.supplier.name,
            "order_codes": order_codes,
            "answer_summary": summary,
            "requested_at": request.requested_at.isoformat(),
            "url": f"/purchase-orders/{po.id}",
        },
        detected_at=clock.now(),
    )
    turn = enqueue_turn(dashboard_conversation(request.requested_by), "alert")
    AlertNotification.objects.create(alert=alert, user=request.requested_by, turn=turn)


def skip_closed() -> int:
    """Requests of orders that closed before the supplier answered."""
    return FollowUpRequest.objects.filter(status__in=(FollowUpRequest.Status.PENDING, FollowUpRequest.Status.ASKED)).exclude(
        purchase_order__status__in=PurchaseOrder.OPEN_STATUSES
    ).update(status=FollowUpRequest.Status.SKIPPED, skip_reason="El pedido se cerró antes de la respuesta.")


def _local(value):
    """Like DRF's DateTimeField: Lima time with its offset (these dicts skip the serializer fields)."""
    return timezone.localtime(value).isoformat() if value else None


def pending_follow_up(po: PurchaseOrder) -> dict | None:
    """The latest request on the order, for its detail."""
    requests = sorted(po.follow_up_requests.all(), key=lambda r: (r.requested_at, r.id))  # prefetched by the list
    if not requests:
        return None
    request = requests[-1]
    return {
        "requested_by_role": getattr(request.requested_by, "role", None),
        "requested_by_role_display": role_label(request.requested_by),
        "requested_at": _local(request.requested_at),
        "status": request.status,
        "asked_at": _local(request.asked_at),
        "answered_at": _local(request.answered_at),
        "answer_summary": request.answer_summary or None,
    }


def last_follow_up(po: PurchaseOrder) -> dict | None:
    if not po.last_follow_up_at:
        return None
    return {"kind": po.last_follow_up_kind, "at": _local(po.last_follow_up_at), "awaiting_reply": po.awaiting_reply_since is not None}
