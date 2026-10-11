"""Domain services for orders and purchase orders. Views, the webhook, the agents' tools and the
tasks call these; nobody writes the models directly. Services with permission rules take
`actor` as a required keyword (a `User`, or `None` for the system)."""

import logging
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from core import clock
from core.models import Config, Customer, Brand, Product
from core.permissions import require_role
from suppliers.models import Rate, Supplier
from suppliers.services import supplier_load, supplier_scores

from .exceptions import ManagerApprovalRequired, UnknownReference
from .models import (
    Order,
    OrderItem,
    Payment,
    ProgressReport,
    PurchaseOrder,
    PurchaseOrderItem,
    Requirement,
    StatusChange,
    Delivery,
)

logger = logging.getLogger(__name__)

PO_PREFIX = {"workshop": "PT", "material": "PI", "finished": "PF"}
CUSTOMIZATION_STAGE = {"embroidery": "embroidery", "sublimation": "sublimation", "print": "sublimation"}
SCORE_WEIGHTS = {"price": 0.35, "on_time": 0.30, "quality": 0.20, "load": 0.15}
DEFAULT_SCORE = 0.7  # Unrated suppliers start neutral.


# --- orders ---------------------------------------------------------------------------------


def actor_label(actor) -> str:
    """What the timeline shows: a username, "agent", "system" or "" (public page)."""
    if actor is None:
        return "system"
    if isinstance(actor, str):
        return actor
    return getattr(actor, "username", "") or "system"


def set_status(obj, status: str, *, actor=None, note: str = "", at=None, save: bool = True):
    """The single point where an order or a purchase order changes status: writes the
    `StatusChange` row the timeline reads. No row when the status does not change."""
    if obj.status == status:
        return obj
    obj.status = status
    if save:
        obj.save(update_fields=["status", "updated_at"])
    target = {"order": obj} if isinstance(obj, Order) else {"purchase_order": obj}
    StatusChange.objects.create(status=status, at=at or clock.now(), actor=actor_label(actor)[:60], note=note[:300], **target)
    return obj


def register_order(payload: dict, *, actor) -> tuple[Order, bool]:
    """The simulated sales system (`POST /api/orders/`). Idempotent by `code`: an existing code
    returns the stored order untouched. Returns (order, created)."""
    require_role(actor, "sales", "manager")
    existing = Order.objects.filter(code=payload["code"]).first()
    if existing:
        return existing, False
    # Every reference must exist before anything is written: the sales system only sends
    # customers, brands and products the catalogue already knows (400 otherwise).
    customer = Customer.objects.filter(name__iexact=payload["customer"].strip()).first()
    if customer is None:
        raise UnknownReference(f"El cliente {payload['customer']} no existe")
    brand = Brand.objects.filter(name__iexact=payload["brand"].strip()).first()
    if brand is None:
        raise UnknownReference(f"La marca {payload['brand']} no existe")
    products = {}
    for item in payload["items"]:
        code = str(item["product"]).strip()
        products[code] = products.get(code) or Product.objects.filter(code__iexact=code).first()
        if products[code] is None:
            raise UnknownReference(f"El producto {code} no existe")
    with transaction.atomic():
        order = Order.objects.create(
            code=payload["code"],
            customer=customer,
            brand=brand,
            owner=actor,
            issued_on=payload.get("issued_on") or clock.today(),
            promised_on=payload["promised_on"],
        )
        StatusChange.objects.create(order=order, status=order.status, at=clock.now(), actor=actor_label(actor))
        for item in payload["items"]:
            product = products[str(item["product"]).strip()]
            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=item["quantity"],
                sizes=item.get("sizes") or {},
                color=item.get("color", ""),
                customization=item.get("customization", ""),
                unit_price=Decimal(str(item["unit_price"])),
            )
        break_down_order(order)
    return order, True


OPEN_ORDER_STATUSES = [s for s, _ in Order.Status.choices if s not in ("delivered", "cancelled")]


def committed_stock_by_material() -> dict[int, Decimal]:
    """Stock already reserved by open orders (`Requirement.qty_from_stock`), per material id.
    Shared by the breakdown and the inventory views, so both count the same thing."""
    totals: dict[int, Decimal] = {}
    rows = Requirement.objects.filter(kind="material", order__status__in=OPEN_ORDER_STATUSES).values_list("material_id", "qty_from_stock")
    for material_id, qty in rows:
        totals[material_id] = totals.get(material_id, Decimal("0")) + qty
    return totals


def committed_stock(material) -> Decimal:
    return committed_stock_by_material().get(material.id, Decimal("0"))


def break_down_order(order: Order) -> list[Requirement]:
    """Step 1: materials per item (quantity × qty_per_unit minus stock), one workshop requirement
    for the sewing and nothing else. `registered → broken_down`."""
    with transaction.atomic():
        order.requirements.all().delete()
        needed: dict[int, Decimal] = {}
        for item in order.items.select_related("product").prefetch_related("product__materials__material"):
            for pm in item.product.materials.all():
                needed[pm.material_id] = needed.get(pm.material_id, Decimal("0")) + item.quantity * pm.qty_per_unit
        requirements = []
        for material_id, qty in needed.items():
            from core.models import Material

            # Lock the material: what other open orders already reserved is not available.
            material = Material.objects.select_for_update().get(pk=material_id)
            available = max(material.stock - committed_stock(material), Decimal("0"))
            from_stock = min(available, qty)
            requirements.append(
                Requirement.objects.create(
                    order=order, kind="material", material=material, qty_needed=qty, qty_from_stock=from_stock
                )
            )
        for item in order.items.all():
            requirements.append(
                Requirement.objects.create(order=order, kind="workshop", product=item.product, qty_needed=item.quantity)
            )
        if order.status == Order.Status.REGISTERED:
            set_status(order, Order.Status.BROKEN_DOWN, actor="system", note="Desglose contra inventario")
        compute_critical_path(order)
    return requirements


def confirm_order(order: Order, *, actor) -> Order:
    """Step 2: production confirms the breakdown; the matching proposes suppliers."""
    require_role(actor, "production", "manager")
    if order.status != Order.Status.BROKEN_DOWN:
        return order
    with transaction.atomic():
        set_status(order, Order.Status.CONFIRMED, actor=actor, note="Desglose confirmado")
        match_requirements(list(order.requirements.all()))
    return order


def _order_purchase_orders(order: Order):
    return PurchaseOrder.objects.filter(items__requirement__order=order).distinct()


def compute_critical_path(order: Order) -> Order:
    """Materials arrive, then the in-plant stages, then sewing (plant or workshop), then
    finishing. Stores the path, `estimated_on` and the risk."""
    config = Config.load()
    durations = config.stage_durations or {}
    today = clock.today()
    if order.status in (Order.Status.READY, Order.Status.DELIVERED, Order.Status.CANCELLED):
        # Nothing left to produce: the estimate is the delivery itself, never a risk.
        if order.status == Order.Status.READY:
            order.estimated_on = min(order.estimated_on or today, max(today, order.promised_on if order.promised_on >= today else today))
        order.risk, order.risk_reason = Order.Risk.OK, ""
        order.save(update_fields=["estimated_on", "risk", "risk_reason", "updated_at"])
        return order
    pos = list(_order_purchase_orders(order).select_related("supplier"))
    # Suggested purchase orders count: until the manager decides, they are the only plan.
    live = [po for po in pos if po.status in PurchaseOrder.OPEN_STATUSES + ("suggested",)]

    def po_date(po):
        """A committed date is the truth. Before the supplier commits, the deadline cannot beat
        the supplier's lead time counted from tomorrow (one day to agree): a replacement
        workshop found today still needs its 8 days, whatever the internal due date says."""
        if po.committed_on:
            return po.committed_on
        earliest = today + timedelta(days=1 + (po.supplier.lead_time_days or 0))
        return max(po.internal_due_on or today, earliest)

    path = []
    materials = [po for po in live if po.supplier.kind == "material"]
    start = today
    if materials:
        arrival = max(po_date(po) for po in materials)
        for po in materials:
            path.append(_step(f"Insumos {po.code}", "material", today, po_date(po), po_date(po) == arrival, po))
        cursor = max(arrival, today)
    else:
        cursor = today

    stages = ["cutting"]
    customizations = {i.customization for i in order.items.all() if i.customization}
    stages += sorted({CUSTOMIZATION_STAGE[c] for c in customizations if c in CUSTOMIZATION_STAGE})
    for stage in stages:
        end = cursor + timedelta(days=int(durations.get(stage, 1)))
        path.append(_step(dict(Order.Stage.choices)[stage], "production", cursor, end, True))
        cursor = end

    workshops = [po for po in live if po.supplier.kind == "workshop"]
    if workshops:
        sewing_end = max(po_date(po) for po in workshops)
        for po in workshops:
            path.append(_step(f"Costura {po.code}", "workshop", cursor, po_date(po), po_date(po) == sewing_end, po))
        cursor = max(sewing_end, cursor)
    else:
        end = cursor + timedelta(days=int(durations.get("sewing", 3)))
        path.append(_step("Costura en planta", "production", cursor, end, True))
        cursor = end

    end = cursor + timedelta(days=int(durations.get("finishing", 1)))
    path.append(_step("Acabado y entrega", "delivery", cursor, end, True))

    order.critical_path = path
    order.estimated_on = end
    slack = (order.promised_on - end).days
    if slack < 0:
        order.risk, order.risk_reason = Order.Risk.IN_DANGER, f"Llegaría {-slack} día(s) después de lo prometido"
    elif slack <= 1:
        order.risk, order.risk_reason = Order.Risk.AT_RISK, "Sin margen frente a la fecha prometida"
    else:
        order.risk, order.risk_reason = Order.Risk.OK, ""
    order.save(update_fields=["critical_path", "estimated_on", "risk", "risk_reason", "updated_at"])
    return order


def _step(name, kind, start, end, critical, po=None):
    today = clock.today()
    if end < today:
        status = "done"
    elif start <= today:
        status = "in_progress"
    else:
        status = "pending"
    if po and po.committed_on and po.internal_due_on and po.committed_on > po.internal_due_on:
        status = "late"
    return {
        "id": f"{kind}-{po.code if po else name}",
        "name": name,
        "kind": kind,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "critical": critical,
        "status": status,
        "purchase_order_id": po.id if po else None,
    }


# --- matching -------------------------------------------------------------------------------


def _next_code(kind: str) -> str:
    prefix = PO_PREFIX[kind]
    n = PurchaseOrder.objects.filter(code__startswith=f"{prefix}-").count() + 1
    while PurchaseOrder.objects.filter(code=f"{prefix}-{n:04d}").exists():
        n += 1
    return f"{prefix}-{n:04d}"


def rank_candidates(requirement: Requirement, *, exclude: Supplier | None = None) -> list[dict]:
    """Suppliers of the right kind with a current rate for the item, scored 0 to 1 per
    criterion and combined with SCORE_WEIGHTS. Sorted best first."""
    filters = {"supplier__status": "active", "supplier__kind": requirement.kind}
    if requirement.material_id:
        filters["material"] = requirement.material
    else:
        filters["product"] = requirement.product
    rates = Rate.objects.filter(**filters).select_related("supplier").order_by("supplier_id", "-valid_from")
    latest: dict[int, Rate] = {}
    for rate in rates:
        latest.setdefault(rate.supplier_id, rate)
    if exclude:
        latest.pop(exclude.id, None)
    if not latest:
        return []
    min_price = min(r.unit_price for r in latest.values())
    ranked = []
    for rate in latest.values():
        supplier = rate.supplier
        scores_db = supplier_scores(supplier)
        load = supplier_load(supplier)
        load_score = 1.0
        if supplier.weekly_capacity:
            load_score = max(0.0, 1.0 - float(load["units"]) / supplier.weekly_capacity)
        scores = {
            "price": round(float(min_price / rate.unit_price), 2) if rate.unit_price else 0.0,
            "on_time": scores_db["on_time"] if scores_db["on_time"] is not None else DEFAULT_SCORE,
            "quality": round(scores_db["quality"] / 5, 2) if scores_db["quality"] is not None else DEFAULT_SCORE,
            "load": round(load_score, 2),
        }
        score = round(sum(SCORE_WEIGHTS[k] * scores[k] for k in SCORE_WEIGHTS), 3)
        free = None
        if supplier.weekly_capacity:
            free = max(Decimal("0"), Decimal(supplier.weekly_capacity) - load["units"])
        ranked.append(
            {
                "supplier_id": supplier.id,
                "supplier_name": supplier.name,
                "score": score,
                "scores": scores,
                "unit_price": str(rate.unit_price),
                "currency": supplier.currency,
                "load_pct": load["pct"],
                "free_capacity": str(free) if free is not None else None,
                "rationale": _rationale(supplier, scores, rate.unit_price == min_price),
            }
        )
    ranked.sort(key=lambda c: c["score"], reverse=True)
    return ranked


def _rationale(supplier: Supplier, scores: dict, cheapest: bool) -> str:
    parts = []
    if cheapest:
        parts.append("mejor precio")
    if scores["on_time"] >= 0.85:
        parts.append("buen cumplimiento")
    if scores["quality"] >= 0.85:
        parts.append("buena calidad")
    if scores["load"] >= 0.5:
        parts.append("capacidad libre")
    elif scores["load"] < 0.2:
        parts.append("casi sin capacidad")
    if supplier.is_in_house:
        parts.append("planta propia")
    return ", ".join(parts).capitalize() if parts else "Cumple los requisitos"


def match_requirements(requirements: list[Requirement], *, exclude: Supplier | None = None, redistributed_from=None):
    """Step 3: one suggested purchase order per requirement and supplier; a large workshop
    requirement is split across workshops when the first one lacks free capacity. Then one
    `approve_assignment` decision for the whole batch."""
    from manager.services import create_decision

    config = Config.load()
    created: list[PurchaseOrder] = []
    proposal: list[dict] = []
    with transaction.atomic():
        for requirement in requirements:
            remaining = requirement.qty_to_order - _covered(requirement)
            if remaining <= 0:
                continue
            candidates = rank_candidates(requirement, exclude=exclude)
            if not candidates:
                logger.warning("match: no supplier for requirement %s", requirement.id)
                continue
            due = requirement.order.promised_on - timedelta(days=config.buffer_days)
            for candidate in candidates:
                if remaining <= 0:
                    break
                supplier = Supplier.objects.get(pk=candidate["supplier_id"])
                take = remaining
                if requirement.kind == "workshop" and candidate["free_capacity"] is not None:
                    free = Decimal(candidate["free_capacity"])
                    if free <= 0:
                        continue
                    take = min(remaining, free) if candidate is not candidates[-1] else remaining
                po = PurchaseOrder.objects.create(
                    code=_next_code(requirement.kind),
                    supplier=supplier,
                    suggested_supplier=supplier,
                    rationale=candidate["rationale"],
                    scores=candidate["scores"],
                    internal_due_on=due,
                    redistributed_from=redistributed_from,
                )
                PurchaseOrderItem.objects.create(
                    purchase_order=po, requirement=requirement, quantity=take, unit_price=Decimal(candidate["unit_price"])
                )
                StatusChange.objects.create(purchase_order=po, status=po.status, at=clock.now(), actor="system", note=candidate["rationale"][:300])
                created.append(po)
                proposal.append(
                    {
                        "purchase_order": {"id": po.id, "code": po.code},
                        "purchase_order_code": po.code,
                        "supplier": {"id": supplier.id, "name": supplier.name},
                        "quantity": str(take),
                        "unit_price": candidate["unit_price"],
                        "currency": supplier.currency,
                        "committed_on": None,
                        "rationale": candidate["rationale"],
                        "candidates": [  # Nested `supplier` like the proposal entry; flat keys kept for older cards.
                            {**{k: v for k, v in c.items() if k != "free_capacity"}, "supplier": {"id": c["supplier_id"], "name": c["supplier_name"]}}
                            for c in candidates
                        ],
                    }
                )
                remaining -= take
        if not created:
            return created, None
        orders = {req.order for req in requirements}
        before = _snapshot(orders) if redistributed_from else None
        for order in orders:
            compute_critical_path(order)
        detail = {"before": before, "after": _snapshot(orders), "proposal": proposal}
        if redistributed_from:
            detail["cancelled"] = {
                "code": redistributed_from.code,
                "supplier_name": redistributed_from.supplier.name,
                "quantity": str(sum((i.quantity for i in redistributed_from.items.all()), Decimal("0"))),
                "units_done": _units_done(redistributed_from),
            }
        names = ", ".join(sorted({po.supplier.name for po in created}))
        decision = create_decision(
            kind="approve_assignment",
            purchase_orders=created,
            summary=f"Asignar {len(created)} pedido(s) a {names}",
            detail=detail,
        )
    return created, decision


def _snapshot(orders) -> dict:
    order = sorted(orders, key=lambda o: o.id)[0]
    order.refresh_from_db()
    total = sum(
        (i.quantity * i.unit_price for po in _order_purchase_orders(order).filter(status__in=PurchaseOrder.OPEN_STATUSES + ("suggested", "delivered")) for i in po.items.all()),
        Decimal("0"),
    )
    currencies = {po.supplier.currency for po in _order_purchase_orders(order).select_related("supplier")}
    currency = currencies.pop() if len(currencies) == 1 else "PEN"  # Mixed currencies: the UI shows per-line amounts.
    return {"estimated_on": order.estimated_on.isoformat() if order.estimated_on else None, "total_amount": str(total), "currency": currency, "route_id": None}


def _covered(requirement: Requirement) -> Decimal:
    """What live purchase orders will bring plus what cancelled ones already delivered."""
    total = Decimal("0")
    for item in requirement.purchase_order_items.select_related("purchase_order"):
        if item.purchase_order.status in PurchaseOrder.OPEN_STATUSES + ("suggested", "delivered"):
            total += item.quantity
        else:
            total += item.qty_delivered
    return total


def _units_done(po: PurchaseOrder) -> int:
    latest = po.progress_reports.order_by("-reported_at", "-id").first()
    return latest.units_done if latest else 0


# --- purchase orders ------------------------------------------------------------------------


def approve_purchase_orders(purchase_orders, *, actor) -> list[PurchaseOrder]:
    """The manager approved: `suggested → approved`, recalc the orders, pick the conversation
    and queue the first contact. The in-house plant needs no negotiation."""
    from messaging.services import conversation_for_supplier, enqueue_turn
    from manager.services import open_alert

    require_role(actor, "manager")
    approved = []
    with transaction.atomic():
        for po in purchase_orders:
            if po.status != PurchaseOrder.Status.SUGGESTED:
                continue
            if po.supplier.is_in_house:
                po.committed_on = po.internal_due_on
                po.save(update_fields=["committed_on", "updated_at"])
                set_status(po, PurchaseOrder.Status.CONFIRMED, actor=actor, note="Planta propia: sin negociación")
                _create_payments(po)
                approved.append(po)
                continue
            conversation = conversation_for_supplier(po.supplier)
            po.conversation = conversation
            po.save(update_fields=["conversation", "updated_at"])
            set_status(po, PurchaseOrder.Status.APPROVED, actor=actor)
            approved.append(po)
            if conversation is None:
                open_alert("no_channel", purchase_order=po, text=f"{po.supplier.name} no tiene un número activo para el pedido {po.code}")
            else:
                enqueue_turn(conversation, "purchase_order_approved")
        for order in {i.requirement.order for po in approved for i in po.items.select_related("requirement__order")}:
            if order.status == Order.Status.CONFIRMED:
                set_status(order, Order.Status.SOURCING, actor=actor, note="Pedidos aprobados")
            compute_critical_path(order)
    return approved


def confirm_purchase_order(po: PurchaseOrder, *, unit_price, committed_on: date, terms: str = "") -> PurchaseOrder:
    """The supplier agreed. Boss rules in code: a price above the current rate or a date past
    `internal_due_on` raise `ManagerApprovalRequired`. Idempotent for the same terms."""
    unit_price = Decimal(str(unit_price))
    if po.status == PurchaseOrder.Status.CONFIRMED and po.committed_on == committed_on and all(
        i.unit_price == unit_price for i in po.items.all()
    ):
        return po
    item = po.items.select_related("requirement").first()
    rate = None
    if item:
        rate = Rate.objects.filter(
            supplier=po.supplier, material=item.requirement.material, product=item.requirement.product
        ).order_by("-valid_from").first()
    if rate and unit_price > rate.unit_price:
        raise ManagerApprovalRequired(f"El precio {unit_price} supera la tarifa vigente {rate.unit_price}")
    if po.internal_due_on and committed_on > po.internal_due_on:
        raise ManagerApprovalRequired(f"La fecha {committed_on} pasa el límite interno {po.internal_due_on}")
    with transaction.atomic():
        po.items.update(unit_price=unit_price)
        po.committed_on = committed_on
        po.terms = terms or po.terms
        po.next_follow_up_at = clock.now() + timedelta(hours=po.supplier.follow_up_every_hours)
        po.save(update_fields=["committed_on", "terms", "next_follow_up_at", "updated_at"])
        set_status(po, PurchaseOrder.Status.CONFIRMED, actor="agent", note=f"Entrega {committed_on:%d/%m} a {unit_price}")
        _create_payments(po)
        for order in _orders_of(po):
            compute_critical_path(order)
    return po


def _create_payments(po: PurchaseOrder) -> None:
    if po.payments.exists():
        return
    total = sum((i.quantity * i.unit_price for i in po.items.all()), Decimal("0"))
    half = (total / 2).quantize(Decimal("0.01"))
    Payment.objects.create(purchase_order=po, kind="advance", amount=half)
    Payment.objects.create(purchase_order=po, kind="balance", amount=total - half)


def _orders_of(po: PurchaseOrder):
    return {i.requirement.order for i in po.items.select_related("requirement__order")}


def record_progress(po: PurchaseOrder, *, units_done: int, note: str = "", message_id=None, photo=None, actor) -> ProgressReport:
    """A progress report from WhatsApp (`message_id`), the dashboard (`actor`) or the public page."""
    if actor is not None:
        require_role(actor, "production", "manager")
    with transaction.atomic():
        report = ProgressReport.objects.create(
            purchase_order=po,
            units_done=units_done,
            note=note,
            message_id=message_id,
            photo=photo,
            reported_at=clock.now(),
        )
        po.next_follow_up_at = clock.now() + timedelta(hours=po.supplier.follow_up_every_hours)
        po.save(update_fields=["next_follow_up_at", "updated_at"])
        if po.status == PurchaseOrder.Status.CONFIRMED:
            who = actor if actor is not None else ("agent" if message_id else "system")
            set_status(po, PurchaseOrder.Status.IN_PROGRESS, actor=who, note=f"Primer avance: {units_done}")
    return report


def record_delivery(po: PurchaseOrder, *, qty_received, qty_defective=0, quality: int = 5, note: str = "", actor) -> Delivery:
    """A delivery; when everything is in, the purchase order closes and gets its rating."""
    require_role(actor, "production", "manager")
    qty_received = Decimal(str(qty_received))
    qty_defective = Decimal(str(qty_defective))
    with transaction.atomic():
        delivery = Delivery.objects.create(
            purchase_order=po,
            qty_received=qty_received,
            qty_defective=qty_defective,
            quality=quality,
            received_by=actor,
            received_at=clock.now(),
            note=note,
        )
        remaining = qty_received
        for item in po.items.all():
            take = min(remaining, item.quantity - item.qty_delivered)
            if take > 0:
                item.qty_delivered += take
                item.save(update_fields=["qty_delivered", "updated_at"])
                remaining -= take
        if all(i.qty_delivered >= i.quantity for i in po.items.all()):
            po.rating = _rate(po)
            po.save(update_fields=["rating", "updated_at"])
            set_status(po, PurchaseOrder.Status.DELIVERED, actor=actor, note=f"Calificación {po.rating['score']}")
            for order in _orders_of(po):
                _advance_order(order)
    return delivery


def _rate(po: PurchaseOrder) -> dict:
    deliveries = list(po.deliveries.all())
    delivered_on = max(d.received_at for d in deliveries).date()
    due = po.committed_on or po.internal_due_on or delivered_on
    delay = (delivered_on - due).days
    received = sum((d.qty_received for d in deliveries), Decimal("0"))
    defective = sum((d.qty_defective for d in deliveries), Decimal("0"))
    quality = sum(d.quality for d in deliveries) / len(deliveries)
    item = po.items.select_related("requirement").first()
    rate = None
    if item:
        rate = Rate.objects.filter(supplier=po.supplier, material=item.requirement.material, product=item.requirement.product).order_by("-valid_from").first()
    price_vs_ref = float((item.unit_price - rate.unit_price) / rate.unit_price * 100) if item and rate and rate.unit_price else 0.0
    defect_pct = float(defective / received * 100) if received else 0.0
    score = max(0.0, min(1.0, 0.5 * (1 if delay <= 0 else max(0, 1 - delay / 7)) + 0.3 * quality / 5 + 0.2 * (1 - defect_pct / 100)))
    return {
        "delay_days": delay,
        "quality": round(quality, 2),
        "defect_pct": str(Decimal(defect_pct).quantize(Decimal("0.01"))),
        "price_vs_ref_pct": str(Decimal(price_vs_ref).quantize(Decimal("0.01"))),
        "score": str(Decimal(score).quantize(Decimal("0.01"))),
        "rated_at": clock.now().isoformat(),
    }


def _advance_order(order: Order) -> None:
    """When every live purchase order of an order is delivered, the order moves on."""
    pos = _order_purchase_orders(order)
    if pos.exists() and not pos.exclude(status__in=("delivered", "cancelled", "cancelled_by_supplier", "declined_by_supplier")).exists():
        if order.status in (Order.Status.SOURCING, Order.Status.CONFIRMED):
            set_status(order, Order.Status.IN_PRODUCTION, actor="system", note="Todos los pedidos entregados")
    compute_critical_path(order)


def cancel_by_supplier(po: PurchaseOrder, *, reason: str, units_done: int | None = None):
    """The supplier cannot go on: record what was done, cancel and redistribute the rest.
    Idempotent: a cancelled purchase order does not redistribute again."""
    if po.status == PurchaseOrder.Status.CANCELLED_BY_SUPPLIER:
        return po, [], None
    with transaction.atomic():
        done = units_done if units_done is not None else _units_done(po)
        if done:
            delivery = Delivery.objects.create(purchase_order=po, qty_received=done, quality=4, received_at=clock.now(), note=f"Cancelación: {reason}")
            remaining = delivery.qty_received
            for item in po.items.all():
                take = min(remaining, item.quantity - item.qty_delivered)
                if take > 0:
                    item.qty_delivered += take
                    item.save(update_fields=["qty_delivered", "updated_at"])
                    remaining -= take
        po.terms = (po.terms + "\n" if po.terms else "") + f"Cancelado por el proveedor: {reason}"
        po.save(update_fields=["terms", "updated_at"])
        set_status(po, PurchaseOrder.Status.CANCELLED_BY_SUPPLIER, actor="agent", note=reason)
        created, decision = redistribute(po)
    return po, created, decision


def redistribute(po: PurchaseOrder):
    """What the cancelled purchase order left uncovered goes back to the matching, excluding
    its supplier. The new purchase orders carry `redistributed_from`; the decision carries
    `before`, `after` and `cancelled`."""
    requirements = [i.requirement for i in po.items.select_related("requirement__order")]
    orders = {r.order for r in requirements}
    old_dates = {order.id: order.estimated_on or order.promised_on for order in orders}  # Delivery days as planned.
    for order in orders:
        compute_critical_path(order)
    created, decision = match_requirements(requirements, exclude=po.supplier, redistributed_from=po)
    for order in orders:
        compute_critical_path(order)
    if decision is not None:
        from .routes import propose_for_redistribution

        before, after = propose_for_redistribution(orders, old_dates)
        if after is not None:
            detail = dict(decision.detail)
            detail["before"] = {**(detail.get("before") or {}), "route_id": before.id}
            detail["after"] = {**(detail.get("after") or {}), "route_id": after.id}
            decision.detail = detail
            decision.save(update_fields=["detail", "updated_at"])
    return created, decision


def mark_payment_paid(payment: Payment, *, method: str, receipt=None, actor) -> Payment:
    require_role(actor, "manager")
    if payment.paid_at:
        return payment
    payment.paid_at = clock.now()
    payment.method = method
    if receipt is not None:
        payment.receipt = receipt
    payment.save(update_fields=["paid_at", "method", "receipt", "updated_at"])
    po = payment.purchase_order
    if payment.kind == "advance" and po.status == PurchaseOrder.Status.CONFIRMED:
        set_status(po, PurchaseOrder.Status.IN_PROGRESS, actor=actor, note="Adelanto pagado")
    return payment


# --- public report link (ADR 0024 C) -------------------------------------------------------


def report_url(po: PurchaseOrder) -> str:
    return f"{settings.PUBLIC_BASE_URL}/report/{po.report_token}"


def mark_report_link_sent(po: PurchaseOrder) -> None:
    po.report_link_sent_at = timezone.now()
    po.save(update_fields=["report_link_sent_at", "updated_at"])


def record_public_report(token, *, units_done: int, photo=None, note: str = "") -> ProgressReport:
    from messaging.services import enqueue_turn

    po = PurchaseOrder.objects.select_related("supplier", "conversation").get(report_token=token)
    report = record_progress(po, units_done=units_done, note=note, photo=photo, actor=None)
    if po.conversation_id:
        enqueue_turn(po.conversation, "web_report")
    return report
