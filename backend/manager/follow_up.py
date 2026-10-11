"""Proactive follow-up configured by the manager (ADR 0027 §1-§2): deterministic code decides
when a supplier may get a message (checkpoints proportional to the term, the "always" cases, a
reminder when they do not answer), inside the window and on working days, at most one message
per supplier and day plus one reminder. The agent then decides whether to write (§3).

`plan_for_today()` is the single source: the tick enqueues what is due, and the preview shows
the rest of the day."""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from core import clock
from core.models import Config, FollowUpMode

REMINDER_AFTER = {FollowUpMode.BALANCED: timedelta(hours=4), FollowUpMode.HIGH: timedelta(hours=2)}  # minimal: next working day
BEHIND_POINTS = 15  # progress more than 15 points under the straight line is "behind"
NO_REPORT_SHARE = 0.30  # no report at all past 30 % of the term
PERCENT_CHECKPOINTS = {FollowUpMode.MINIMAL: (50,), FollowUpMode.BALANCED: (30, 60, 85)}


@dataclass
class PlannedFollowUp:
    supplier: object
    mode: str
    kind: str  # checkpoint | reminder
    at: datetime
    purchase_orders: list = field(default_factory=list)
    reasons: dict = field(default_factory=dict)  # po id -> (kind, reason)

    @property
    def reason(self) -> str:
        texts = [reason for _, reason in self.reasons.values()]
        if len(self.purchase_orders) == 1:
            return texts[0]
        return "; ".join(f"{po.code}: {self.reasons[po.id][1]}" for po in self.purchase_orders)

    def payload(self) -> dict:
        """What the tick stores in `Turn.follow_up`."""
        return {
            "kind": self.kind,
            "reason": self.reason,
            "mode": self.mode,
            "purchase_orders": {str(po.id): {"kind": kind, "reason": reason} for po in self.purchase_orders for kind, reason in [self.reasons[po.id]]},
        }


def effective_mode(supplier, config: Config | None = None) -> str:
    config = config or Config.load()
    return supplier.follow_up_mode or config.follow_up_mode


def offset_for(supplier) -> timedelta:
    """A fixed delay per supplier inside the first hour of the window, so the day's first
    messages do not all leave at 09:00 sharp."""
    return timedelta(minutes=(supplier.id * 37) % 60)


def in_window(when: datetime, config: Config) -> bool:
    local = timezone.localtime(when)
    return local.weekday() in config.follow_up_weekdays and config.follow_up_window_start <= local.time() < config.follow_up_window_end


def window_opening(day: date, supplier, config: Config) -> datetime:
    return timezone.make_aware(datetime.combine(day, config.follow_up_window_start)) + offset_for(supplier)


def next_working_day(day: date, config: Config) -> date | None:
    for step in range(1, 8):
        candidate = day + timedelta(days=step)
        if candidate.weekday() in config.follow_up_weekdays:
            return candidate
    return None


def previous_working_day(day: date, config: Config) -> date:
    for step in range(1, 8):
        candidate = day - timedelta(days=step)
        if candidate.weekday() in config.follow_up_weekdays:
            return candidate
    return day - timedelta(days=7)


def term(po) -> tuple[date, date] | None:
    """From the confirmation (or the approval, or the creation) to the agreed date."""
    end = po.committed_on or po.internal_due_on
    if end is None:
        return None
    changes = sorted(po.status_changes.all(), key=lambda c: c.at)
    started = next((c.at for c in changes if c.status == "confirmed"), None) or next((c.at for c in changes if c.status == "approved"), None)
    start = timezone.localtime(started or po.created_at).date()
    return start, max(end, start)


def total_units(po) -> int:
    return int(sum(item.quantity for item in po.items.all()))


def units_done(po) -> int:
    reports = sorted(po.progress_reports.all(), key=lambda r: r.reported_at)
    return reports[-1].units_done if reports else 0


def last_report_at(po):
    reports = sorted(po.progress_reports.all(), key=lambda r: r.reported_at)
    return reports[-1].reported_at if reports else None


def expected_units(po, today: date | None = None) -> int | None:
    """Straight-line progress expected today, between the start of the term and the agreed date."""
    span = term(po)
    if span is None:
        return None
    start, end = span
    today = today or clock.today()
    length = max((end - start).days, 1)
    share = min(max((today - start).days / length, 0), 1)
    return int(total_units(po) * share)


def checkpoint_days(mode: str, length: int) -> dict[int, str]:
    """Day index (from the start of the term) -> reason, by mode (ADR 0027 §2 table)."""
    if length < 2:
        return {}  # a one-day order is "delivery today/tomorrow"
    eve = length - 1
    if mode == FollowUpMode.HIGH:
        days = {d: "control diario" for d in range(1, eve)}
    else:
        days = {}
        for pct in PERCENT_CHECKPOINTS[mode]:
            day = int(length * pct / 100)
            if 1 <= day < eve:
                days.setdefault(day, f"punto de control del {pct} %")
    days[eve] = "víspera de la entrega"
    return days


def _supplier_wrote_since(po, since: datetime) -> bool:
    conversation = po.conversation
    if conversation is not None and conversation.messages.filter(author="supplier", sent_at__gte=since).exists():
        return True
    return any(r.reported_at >= since for r in po.progress_reports.all())


def _always_reason(po, today: date) -> str | None:
    """Written whatever the mode: delivery today or tomorrow, progress behind, or no report past 30 %."""
    span = term(po)
    if span is None:
        return None
    start, end = span
    if end == today:
        return "entrega hoy"
    if end == today + timedelta(days=1):
        return "entrega mañana"
    total = total_units(po)
    length = max((end - start).days, 1)
    elapsed = (today - start).days / length
    if total and po.progress_reports.all():
        expected_pct = round(min(max(elapsed, 0), 1) * 100)
        done_pct = round(units_done(po) * 100 / total)
        if done_pct < expected_pct - BEHIND_POINTS:
            return f"avance atrasado ({done_pct} % contra {expected_pct} % esperado)"
    elif total and elapsed > NO_REPORT_SHARE:
        return f"sin reporte de avance ({round(min(elapsed, 1) * 100)} % del plazo)"
    return None


def _checkpoint_reason(po, mode: str, today: date, config: Config, now: datetime) -> str | None:
    """Today's checkpoint for the order, if any: one whose day is today, or fell on a non-working
    day since the previous working day. Skipped by the mode's rule."""
    span = term(po)
    if span is None:
        return None
    start, end = span
    if today >= end:
        return None
    since_day = previous_working_day(today, config)
    days = checkpoint_days(mode, (end - start).days)
    due = [(d, reason) for d, reason in sorted(days.items()) if since_day < start + timedelta(days=d) <= today]
    if not due:
        return None
    day, reason = due[-1]
    if mode == FollowUpMode.MINIMAL:
        earlier = [d for d in days if d < day]
        previous = start + timedelta(days=earlier[-1]) if earlier else start
        if _supplier_wrote_since(po, timezone.make_aware(datetime.combine(previous, time.min))):
            return None
    elif mode == FollowUpMode.BALANCED:
        recent = last_report_at(po)
        expected = expected_units(po, today) or 0
        if recent and recent >= now - timedelta(hours=24) and total_units(po) and units_done(po) * 100 / total_units(po) >= expected * 100 / total_units(po) - BEHIND_POINTS:
            return None  # reported in the last 24 h and on pace
    return reason


def _reminder_at(po, mode: str, supplier, config: Config) -> datetime | None:
    """When the reminder of an unanswered follow-up is due (not before the window opens)."""
    if po.awaiting_reply_since is None or po.reminded_at is not None:
        return None
    sent_day = timezone.localtime(po.awaiting_reply_since).date()
    if mode == FollowUpMode.MINIMAL:
        day = next_working_day(sent_day, config)
        return window_opening(day, supplier, config) if day else None
    due = po.awaiting_reply_since + REMINDER_AFTER[mode]
    local = timezone.localtime(due)
    if local.weekday() in config.follow_up_weekdays and config.follow_up_window_start <= local.time() < config.follow_up_window_end:
        return due
    day = local.date() if local.time() < config.follow_up_window_start and local.weekday() in config.follow_up_weekdays else next_working_day(local.date(), config)
    return window_opening(day, supplier, config) if day else None


def open_purchase_orders(supplier_ids=None):
    from operations.models import PurchaseOrder

    qs = (
        PurchaseOrder.objects.filter(status__in=PurchaseOrder.OPEN_STATUSES, supplier__status="active", supplier__is_in_house=False)
        .select_related("supplier", "conversation")
        .prefetch_related("status_changes", "progress_reports", "items")
        .order_by("supplier_id", "committed_on", "id")
    )
    if supplier_ids:
        qs = qs.filter(supplier_id__in=supplier_ids)
    return qs


def plan_for_today(now: datetime | None = None, supplier_ids=None) -> list[PlannedFollowUp]:
    """What each supplier gets today, with the time it may go. Empty on non-working days."""
    config = Config.load()
    now = now or clock.now()
    today = timezone.localtime(now).date()
    if today.weekday() not in config.follow_up_weekdays:
        return []
    by_supplier: dict[int, list] = {}
    for po in open_purchase_orders(supplier_ids):
        by_supplier.setdefault(po.supplier_id, []).append(po)
    plan = []
    for pos in by_supplier.values():
        supplier = pos[0].supplier
        mode = effective_mode(supplier, config)
        followed_today = any(po.last_follow_up_on == today for po in pos)
        reminders = {}
        for po in pos:
            due = _reminder_at(po, mode, supplier, config)
            if due and timezone.localtime(due).date() <= today:  # also one that came due on an earlier day (tick down, window change; agente 11/10)
                since = timezone.localtime(po.awaiting_reply_since)
                reminders[po.id] = (due, f"sin respuesta desde las {since:%H:%M}" if since.date() == today else f"sin respuesta desde el {since:%d/%m}")
        checkpoints = {}
        reminder_occupies_day = mode == FollowUpMode.MINIMAL and reminders
        if not followed_today and not reminder_occupies_day:
            for po in pos:
                if po.awaiting_reply_since is not None:
                    continue  # waiting for an answer: the reminder covers it
                reason = _always_reason(po, today) or _checkpoint_reason(po, mode, today, config, now)
                if reason:
                    checkpoints[po.id] = reason
        if checkpoints:
            covered = [po for po in pos if po.id in checkpoints or po.id in reminders]
            reasons = {po.id: ("checkpoint", checkpoints[po.id]) if po.id in checkpoints else ("reminder", reminders[po.id][1]) for po in covered}
            at = window_opening(today, supplier, config)
            plan.append(PlannedFollowUp(supplier=supplier, mode=mode, kind="checkpoint", at=at, purchase_orders=covered, reasons=reasons))
        elif reminders:
            covered = [po for po in pos if po.id in reminders]
            at = max(due for due, _ in reminders.values())
            plan.append(
                PlannedFollowUp(supplier=supplier, mode=mode, kind="reminder", at=at, purchase_orders=covered, reasons={po.id: ("reminder", reminders[po.id][1]) for po in covered})
            )
    return sorted(plan, key=lambda p: (p.at, p.supplier.name))


def enqueue_due_follow_ups(now: datetime | None = None) -> int:
    """The tick: one `follow_up` turn per supplier conversation whose plan is due now, inside the
    window. Nothing else enqueues follow-up turns (ADR 0027 §2)."""
    from messaging.models import Turn
    from messaging.services import conversation_for_supplier, enqueue_turn

    config = Config.load()
    now = now or clock.now()
    if not in_window(now, config):
        return 0
    queued = 0
    for planned in plan_for_today(now):
        if planned.at > now:
            continue
        conversation = next((po.conversation for po in planned.purchase_orders if po.conversation and po.conversation.allowed_number_id), None)
        conversation = conversation or conversation_for_supplier(planned.supplier)
        if conversation is None or conversation.allowed_number is None or not conversation.allowed_number.active:
            continue
        if conversation.turns.filter(status__in=(Turn.Status.PENDING, Turn.Status.RUNNING)).exists():
            continue  # one turn at a time; the next tick tries again
        for po in planned.purchase_orders:
            if po.conversation_id != conversation.id:
                po.conversation = conversation
                po.save(update_fields=["conversation", "updated_at"])
        turn = enqueue_turn(conversation, "follow_up")
        turn.follow_up = planned.payload()
        turn.save(update_fields=["follow_up", "updated_at"])
        queued += 1
    return queued


def refresh_next_follow_up(now: datetime | None = None) -> None:
    """`next_follow_up_at` is the next computed opportunity: today's planned time, else None."""
    from operations.models import PurchaseOrder

    planned = {po.id: p.at for p in plan_for_today(now) for po in p.purchase_orders}
    for po in PurchaseOrder.objects.filter(status__in=PurchaseOrder.OPEN_STATUSES).only("id", "next_follow_up_at"):
        value = planned.get(po.id)
        if po.next_follow_up_at != value:
            PurchaseOrder.objects.filter(pk=po.pk).update(next_follow_up_at=value)


def stalled_purchase_orders(now: datetime | None = None):
    """Unanswered after the reminder: the reminder's own gap has passed (a day in minimal)."""
    now = now or clock.now()
    for po in open_purchase_orders():
        if po.awaiting_reply_since is None or po.reminded_at is None:
            continue
        gap = REMINDER_AFTER.get(effective_mode(po.supplier), timedelta(days=1))
        if now >= po.reminded_at + gap:
            yield po


def preview(now: datetime | None = None) -> list[dict]:
    """`GET /api/settings/follow-up/preview/`: today's plan."""
    return [
        {
            "supplier": {"id": p.supplier.id, "name": p.supplier.name},
            "purchase_orders": [po.code for po in p.purchase_orders],
            "at": p.at,
            "kind": p.kind,
            "reason": p.reason,
            "mode": p.mode,
        }
        for p in plan_for_today(now)
    ]
