"""Domain services for orders and purchase orders. Views, the webhook, the agents' tools and the
tasks call these; nobody writes the models directly. Services with permission rules take
`actor` as a required keyword (a `User`, or `None` for the system)."""

import logging
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import PermissionDenied
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
CUSTOMIZATION_WORDS = {"embroidery": ("bord", "embroid"), "sublimation": ("sublim", "estamp", "print", "serigraf")}


def customization_stages(order) -> set[str]:
    """Plant stages implied by the free-text customizations of the items (several at once)."""
    stages = set()
    for item in order.items.all():
        text = (item.customization or "").lower()
        for stage, words in CUSTOMIZATION_WORDS.items():
            if any(w in text for w in words):
                stages.add(stage)
    return stages
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
    order_code = (payload.get("code") or "").strip()
    existing = Order.objects.filter(code=order_code).first() if order_code else None
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
    _, _, products = _resolve_references({"items": payload["items"]})
    photos = item_photos(payload["items"])
    with transaction.atomic():
        order = Order.objects.create(
            code=order_code or next_order_code(),  # `code` below is reused for product codes
            customer=customer,
            brand=brand,
            owner=actor,
            issued_on=payload.get("issued_on") or clock.today(),
            promised_on=payload["promised_on"],
            notes=payload.get("notes") or "",
        )
        StatusChange.objects.create(order=order, status=order.status, at=clock.now(), actor=actor_label(actor))
        keyed = []
        for item, photo in zip(payload["items"], photos):
            created = OrderItem.objects.create(
                order=order,
                product=products.get(str(item.get("product") or "").strip()),
                description=(item.get("description") or "").strip(),
                quantity=item["quantity"],
                sizes=item.get("sizes") or {},
                color=item.get("color", ""),
                customization=item.get("customization", ""),
                unit_price=Decimal(str(item["unit_price"])) if item.get("unit_price") is not None else None,
                photo=photo,
            )
            keyed.append((item.get("key"), created))
        order.classification_warnings = []
        if payload.get("classification"):  # the magic form (ADR 0028): born broken down, nothing left to classify
            from .classify import apply_by_key

            apply_by_key(order, keyed, payload["classification"], order.classification_warnings)
        break_down_order(order)
        schedule_auto_classify(order)
    return order, True


def item_photos(items: list[dict]) -> list:
    """N1 (ADR 0029): each item's photo, checked before anything is written (a bad one is a 400
    `BadImage` and the order stays as it was). A new `photo` wins over a re-sent `photo_url`;
    neither leaves the item without a photo."""
    from .describe import kept_photo, photo_file

    photos = []
    for item in items:
        if item.get("photo"):
            photos.append(photo_file(item["photo"]))
        elif item.get("photo_url"):
            photos.append(kept_photo(item["photo_url"]))
        else:
            photos.append("")
    return photos


def schedule_auto_classify(order: Order) -> bool:
    """M3: an order with items still without a product classifies itself in the background, once
    this transaction commits (the sales system's API, or a form line the AI could not read)."""
    if not order.items.filter(product__isnull=True).exists():
        return False

    def send():
        try:
            from .tasks import auto_classify

            auto_classify.apply_async((order.id, 1), queue="periodic")
        except Exception:  # The broker is down: the order stays "to classify", as before.
            logger.exception("schedule_auto_classify: could not queue %s", order.code)

    transaction.on_commit(send)
    return True


def next_order_code() -> str:
    """`CP-YYYY-NNNN`, the next number of the current year; the last order of the year is
    locked for the moment of the pick so two forms submitted together never share a code."""
    year = clock.today().year
    prefix = f"CP-{year}-"
    with transaction.atomic():
        last = Order.objects.select_for_update().filter(code__startswith=prefix).order_by("-code").values_list("code", flat=True).first()
        tail = last.rsplit("-", 1)[1] if last else ""
        number = int(tail) + 1 if tail.isdigit() else 1
        while Order.objects.filter(code=f"{prefix}{number:04d}").exists():
            number += 1
    return f"{prefix}{number:04d}"


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


def effective_recipe(item: OrderItem) -> list[tuple]:
    """ADR 0029: the item's recipe in this order, `[(material, qty_per_unit)]`: its `bom_override`
    when the technical sheet was revised, else its product's. The catalogue never changes."""
    from core.models import Material

    if item.bom_override is not None:
        by_id = Material.objects.in_bulk([int(e["material_id"]) for e in item.bom_override])
        return [(by_id[int(e["material_id"])], Decimal(str(e["qty_per_unit"]))) for e in item.bom_override if int(e["material_id"]) in by_id]
    if item.product_id is None:
        return []
    return [(pm.material, pm.qty_per_unit) for pm in item.product.materials.all()]


def stage_durations(order: Order) -> dict:
    """Days per in-plant stage for this order: `Config.stage_durations` under the order's own
    `stage_overrides` (ADR 0029)."""
    return {**(Config.load().stage_durations or {}), **(order.stage_overrides or {})}


def break_down_order(order: Order) -> list[Requirement]:
    """Step 1: materials per item (quantity × qty_per_unit minus stock), one workshop requirement
    for the sewing and nothing else. `registered → broken_down`."""
    with transaction.atomic():
        order.requirements.all().delete()
        needed: dict[int, Decimal] = {}
        order.needs_classification = order.items.filter(product__isnull=True).exists()
        order.save(update_fields=["needs_classification", "updated_at"])
        for item in order.items.filter(product__isnull=False).select_related("product").prefetch_related("product__materials__material"):
            for material, qty_per_unit in effective_recipe(item):
                needed[material.id] = needed.get(material.id, Decimal("0")) + item.quantity * qty_per_unit
        requirements = []
        for material_id, qty in needed.items():
            from core.models import Material

            # Lock the material: what other open orders already reserved is not available.
            material = Material.objects.select_for_update().get(pk=material_id)
            available = max(material.stock - committed_stock(material), Decimal("0"))
            from_stock = min(available, qty)
            requirements.append(
                Requirement.objects.create(
                    order=order, kind="material", material=material, qty_needed=qty, qty_from_stock=from_stock,
                    status=Requirement.Status.COVERED if qty - from_stock <= 0 else Requirement.Status.OPEN,
                )
            )
        for item in order.items.filter(product__isnull=False):
            requirements.append(
                Requirement.objects.create(order=order, kind="workshop", product=item.product, qty_needed=item.quantity)
            )
        if order.status == Order.Status.REGISTERED:
            set_status(order, Order.Status.BROKEN_DOWN, actor="system", note="Ficha técnica contra inventario")
        compute_critical_path(order)
    return requirements


def confirm_order(order: Order, *, actor) -> Order:
    """Step 2: production confirms the breakdown; the matching proposes suppliers."""
    require_role(actor, "production", "manager")
    if order.status != Order.Status.BROKEN_DOWN:
        return order
    if order.needs_classification:
        raise UnknownReference(f"La orden {order.code} tiene ítems sin producto: clasifícalos antes de confirmar")
    with transaction.atomic():
        set_status(order, Order.Status.CONFIRMED, actor=actor, note="Ficha técnica aprobada")
        # Materials stay open: Produccion (or the manager) generates one consolidated purchase
        # order per material across orders (ADR 0025 A). Workshop and finished goods are per order.
        match_requirements([r for r in order.requirements.all() if r.kind != "material"])
    return order


EDITABLE_BY_SALES = (Order.Status.REGISTERED, Order.Status.BROKEN_DOWN)
CANCELLABLE = (Order.Status.REGISTERED, Order.Status.BROKEN_DOWN, Order.Status.CONFIRMED, Order.Status.SOURCING)


def check_order_edit(order: Order, *, actor, cancel: bool = False) -> None:
    """ADR 0025 B: sales edits and cancels only their own orders up to `broken_down`; the
    manager edits any order and cancels any before production; production touches no order."""
    role = getattr(actor, "role", None)
    if role == "manager":
        if cancel and order.status not in CANCELLABLE:
            raise UnknownReference(f"La orden {order.code} ya está en estado «{order.get_status_display()}» y no se puede cancelar")
        return
    if role != "sales":
        raise PermissionDenied("Solo Comercial y el Gerente editan órdenes")
    if order.owner_id != getattr(actor, "id", None):
        raise PermissionDenied("Comercial solo edita sus propias órdenes")
    if order.status not in EDITABLE_BY_SALES:
        raise PermissionDenied(f"La orden ya está en estado «{order.get_status_display()}»: solo el Gerente la cambia")


def _resolve_references(payload: dict) -> tuple:
    customer = brand = None
    if payload.get("customer") is not None:
        customer = Customer.objects.filter(name__iexact=str(payload["customer"]).strip()).first()
        if customer is None:
            raise UnknownReference(f"El cliente {payload['customer']} no existe")
    if payload.get("brand") is not None:
        brand = Brand.objects.filter(name__iexact=str(payload["brand"]).strip()).first()
        if brand is None:
            raise UnknownReference(f"La marca {payload['brand']} no existe")
    products = {}
    for item in payload.get("items") or []:
        if not item.get("product"):
            if not (item.get("description") or "").strip():
                raise UnknownReference("Cada ítem necesita un producto del catálogo o una descripción")
            continue
        code = str(item["product"]).strip()
        products[code] = products.get(code) or Product.objects.filter(code__iexact=code).first()
        if products[code] is None:
            raise UnknownReference(f"El producto {code} no existe")
    return customer, brand, products


def update_order(order: Order, payload: dict, *, actor) -> tuple[Order, list[str]]:
    """`PATCH /api/orders/<id>/`: header fields and, when `items` comes, the full list of items.
    Orders already broken down are broken down again; requirements that a purchase order
    already covers are left alone and reported in the warnings."""
    check_order_edit(order, actor=actor)
    customer, brand, products = _resolve_references(payload)
    photos = item_photos(payload.get("items") or [])
    warnings: list[str] = []
    with transaction.atomic():
        if customer is not None:
            order.customer = customer
        if brand is not None:
            order.brand = brand
        for field in ("promised_on", "issued_on", "notes"):
            if payload.get(field) is not None:
                setattr(order, field, payload[field])
        order.save()
        if payload.get("items") is not None:
            before = order_needs(order)
            order.items.all().delete()
            keyed = []
            for item, photo in zip(payload["items"], photos):
                created = OrderItem.objects.create(
                    order=order,
                    product=products.get(str(item.get("product") or "").strip()),
                    description=(item.get("description") or "").strip(),
                    quantity=item["quantity"],
                    sizes=item.get("sizes") or {},
                    color=item.get("color", "") or "",
                    customization=item.get("customization", "") or "",
                    unit_price=Decimal(str(item["unit_price"])) if item.get("unit_price") is not None else None,
                    photo=photo,
                )
                keyed.append((item.get("key"), created))
            if payload.get("classification"):  # ADR 0028: the edit's new items come classified too
                from .classify import apply_by_key

                apply_by_key(order, keyed, payload["classification"], warnings)
            if order.status != Order.Status.REGISTERED:
                warnings = warnings + rebreak_down_order(order, before=before)
            schedule_auto_classify(order)
        compute_critical_path(order)
    return order, warnings


def order_needs(order: Order) -> dict[tuple, Decimal]:
    """What the order's items need with their effective recipes: `("material", id)` in the
    material's unit and `("workshop", product_id)` in garments. Taken before a change so
    `rebreak_down_order` warns only about what the change moved."""
    needs: dict[tuple, Decimal] = {}
    for item in order.items.filter(product__isnull=False).select_related("product").prefetch_related("product__materials__material"):
        needs[("workshop", item.product_id)] = needs.get(("workshop", item.product_id), Decimal("0")) + item.quantity
        for material, qty_per_unit in effective_recipe(item):
            needs[("material", material.id)] = needs.get(("material", material.id), Decimal("0")) + item.quantity * qty_per_unit
    return needs


def rebreak_down_order(order: Order, *, before: dict[tuple, Decimal] | None = None) -> list[str]:
    """Recomputes the requirements of an edited order (a PATCH of its items, a technical sheet
    revision). A requirement a purchase order already covers stays as it is; the rest is rebuilt.
    When the new need of a material goes beyond what is already ordered, a complementary
    requirement for the difference lands in "Por pedir" (ADR 0029, agente 11/10 04:00). One
    warning per material or garment that this change moved away from what is ordered; none
    for the rest, even if an earlier change left them apart."""
    from core.models import Material

    if before is None:  # no snapshot: what the current requirements add up to
        before = {}
        for requirement in order.requirements.all():
            key = (requirement.kind, requirement.material_id or requirement.product_id)
            before[key] = before.get(key, Decimal("0")) + requirement.qty_needed
    kept = [r for r in order.requirements.all() if r.purchase_order_items.exists()]
    order.requirements.exclude(pk__in=[r.pk for r in kept]).delete()
    order.needs_classification = order.items.filter(product__isnull=True).exists()
    order.save(update_fields=["needs_classification", "updated_at"])
    needed: dict[int, Decimal] = {}
    garments: dict[int, int] = {}
    items = list(order.items.filter(product__isnull=False).select_related("product").prefetch_related("product__materials__material"))
    for item in items:
        garments[item.product_id] = garments.get(item.product_id, 0) + item.quantity
        for material, qty_per_unit in effective_recipe(item):
            needed[material.id] = needed.get(material.id, Decimal("0")) + item.quantity * qty_per_unit
    ordered: dict[tuple, list[Requirement]] = {}
    for requirement in kept:
        ordered.setdefault((requirement.kind, requirement.material_id or requirement.product_id), []).append(requirement)

    warnings = []
    for material_id in sorted(set(needed) | {key for kind, key in ordered if kind == "material"}):
        qty = needed.get(material_id, Decimal("0"))
        already_kept = ordered.get(("material", material_id), [])
        already = sum((r.qty_needed for r in already_kept), Decimal("0"))
        missing = qty - already
        material = Material.objects.select_for_update().get(pk=material_id)
        if missing > 0:  # everything when nothing was ordered, else the complement
            available = max(material.stock - committed_stock(material), Decimal("0"))
            from_stock = min(available, missing)
            Requirement.objects.create(
                order=order, kind="material", material=material, qty_needed=missing, qty_from_stock=from_stock,
                status=Requirement.Status.COVERED if missing - from_stock <= 0 else Requirement.Status.OPEN,
            )
        if not already_kept or missing == 0 or qty == before.get(("material", material_id), Decimal("0")):
            continue
        head = f"{material.name}: {_amount(already, material.unit)} ya pedidos en {_codes(already_kept)}"
        if missing > 0:
            warnings.append(f"{head}; faltan {_amount(missing, material.unit)} por pedir")
        else:
            warnings.append(f"{head}; con la ficha nueva bastan {_amount(qty, material.unit)}, quedan {_amount(-missing, material.unit)} de más")
    for item in items:
        if ("workshop", item.product_id) not in ordered:
            Requirement.objects.create(order=order, kind="workshop", product=item.product, qty_needed=item.quantity)
    for (kind, product_id), requirements in ordered.items():
        if kind != "workshop":
            continue
        already = sum(r.qty_needed for r in requirements)
        now = garments.get(product_id, 0)
        if already != now and now != before.get(("workshop", product_id), 0):  # sewing is assigned per order by the manager: a warning, no complement
            warnings.append(
                f"{requirements[0].product.name}: {_amount(already)} prendas ya pedidas al taller en {_codes(requirements)}; "
                f"la orden ahora pide {_amount(now)}"
            )
    return warnings


def _amount(qty, unit: str = "unit") -> str:
    text = format(Decimal(str(qty)).normalize(), "f")
    return text if unit == "unit" else f"{text} {unit}"


def _codes(requirements) -> str:
    codes = sorted({i.purchase_order.code for r in requirements for i in r.purchase_order_items.select_related("purchase_order")})
    return codes[0] if len(codes) == 1 else ", ".join(codes[:-1]) + " y " + codes[-1]


def cancel_order(order: Order, *, reason: str = "", actor) -> Order:
    """`POST /api/orders/<id>/cancel/`: the order and its suggested purchase orders are
    cancelled; purchase orders already approved stay for the manager to settle."""
    check_order_edit(order, actor=actor, cancel=True)
    with transaction.atomic():
        for po in _order_purchase_orders(order).filter(status=PurchaseOrder.Status.SUGGESTED):
            set_status(po, PurchaseOrder.Status.CANCELLED, actor=actor, note=f"Orden {order.code} cancelada")
            for item in po.items.select_related("requirement"):
                sync_requirement_status(item.requirement)
        from manager.models import Decision

        for decision in Decision.objects.filter(status="pending", kind="approve_assignment", purchase_orders__items__requirement__order=order).distinct():
            if not decision.purchase_orders.exclude(status=PurchaseOrder.Status.CANCELLED).exists():
                decision.status = "rejected"
                decision.note = f"Orden {order.code} cancelada"
                decision.resolved_at = clock.now()
                decision.save(update_fields=["status", "note", "resolved_at", "updated_at"])
        order.risk, order.risk_reason = Order.Risk.OK, ""
        order.save(update_fields=["risk", "risk_reason", "updated_at"])
        set_status(order, Order.Status.CANCELLED, actor=actor, note=reason or "Cancelada desde el dashboard")
    return order


def break_down_orders(order_ids=None, *, actor) -> dict:
    """`POST /api/orders/break-down/`: every `registered` order (or the ids given) goes through
    `break_down_order`. Returns {broken_down: [codes], skipped: [{code, reason}]}."""
    require_role(actor, "manager", "production")
    qs = Order.objects.order_by("id")
    if order_ids:
        qs = qs.filter(id__in=order_ids)
    else:
        qs = qs.filter(status=Order.Status.REGISTERED)
    done, skipped = [], []
    for order in qs:
        if order.status != Order.Status.REGISTERED:
            skipped.append({"code": order.code, "reason": f"ya está en estado «{order.get_status_display()}»"})
            continue
        break_down_order(order)
        done.append(order.code)
    for missing in sorted(set(order_ids or []) - set(qs.values_list("id", flat=True))):
        skipped.append({"code": str(missing), "reason": "no existe"})
    return {"broken_down": done, "skipped": skipped}


# --- consolidated material purchase orders (ADR 0025 A) ---------------------------------------

PURCHASING_ORDER_STATUSES = (Order.Status.CONFIRMED, Order.Status.SOURCING, Order.Status.IN_PRODUCTION)


def open_material_requirements(material_ids=None):
    """Material requirements still to order, of orders production already confirmed."""
    qs = (
        Requirement.objects.filter(kind="material", status=Requirement.Status.OPEN, order__status__in=PURCHASING_ORDER_STATUSES)
        .select_related("material", "order__customer")
        .order_by("material__kind", "material__name", "order__promised_on", "id")
    )
    if material_ids:
        qs = qs.filter(material_id__in=material_ids)
    return [r for r in qs if remaining_to_order(r) > 0]


def to_order_by_material(material_ids=None) -> dict[int, Decimal]:
    """What is still to buy per material id: the sum of `remaining_to_order` over
    `open_material_requirements`, the same number as `total_to_order` in "Por pedir", in two
    queries for every material (the inventory list)."""
    qs = Requirement.objects.filter(kind="material", status=Requirement.Status.OPEN, order__status__in=PURCHASING_ORDER_STATUSES).prefetch_related(
        "purchase_order_items__purchase_order"
    )
    if material_ids:
        qs = qs.filter(material_id__in=material_ids)
    totals: dict[int, Decimal] = {}
    for requirement in qs:
        remaining = max(requirement.qty_to_order - _covered_by(requirement.purchase_order_items.all()), Decimal("0"))
        if remaining > 0:
            totals[requirement.material_id] = totals.get(requirement.material_id, Decimal("0")) + remaining
    return totals


def incoming_by_material(material_ids=None) -> dict[int, list[dict]]:
    """Live purchase orders per material id (`OPEN_STATUSES` or `suggested`):
    `[{id, code, status, status_display, qty_pending}]` with `qty_pending` = what their items of
    that material still have to bring, ordered by `internal_due_on`. One query for every material."""
    from django.db.models import F, Sum

    statuses = tuple(PurchaseOrder.OPEN_STATUSES) + (PurchaseOrder.Status.SUGGESTED,)
    rows = PurchaseOrderItem.objects.filter(purchase_order__status__in=statuses, requirement__material__isnull=False)
    if material_ids:
        rows = rows.filter(requirement__material_id__in=material_ids)
    rows = (
        rows.values("requirement__material_id", "purchase_order_id", "purchase_order__code", "purchase_order__status", "purchase_order__internal_due_on")
        .annotate(pending=Sum(F("quantity") - F("qty_delivered")))
        .order_by("requirement__material_id", F("purchase_order__internal_due_on").asc(nulls_last=True), "purchase_order__code")
    )
    incoming: dict[int, list[dict]] = {}
    for row in rows:
        incoming.setdefault(row["requirement__material_id"], []).append(
            {
                "id": row["purchase_order_id"],
                "code": row["purchase_order__code"],
                "status": row["purchase_order__status"],
                "status_display": PurchaseOrder.Status(row["purchase_order__status"]).label,
                "qty_pending": str(max(row["pending"] or Decimal("0"), Decimal("0")).quantize(Decimal("0.01"))),
            }
        )
    return incoming


def remaining_to_order(requirement: Requirement) -> Decimal:
    """What is still to buy for a requirement: beyond stock, minus what its purchase orders
    bring or already delivered (finding of 10/10 22:10: a delivered partial purchase order
    made "Por pedir" and the alert say 1000 while the generated order said 400)."""
    return max(requirement.qty_to_order - _covered(requirement), Decimal("0"))


def pending_purchases(*, with_prices: bool, material_ids=None) -> list[dict]:
    """The "Por pedir" view: open requirements grouped by material, with the matching's
    suggestion. Prices (and currency) only for the manager."""
    config = Config.load()
    groups: dict[int, dict] = {}
    for requirement in open_material_requirements(material_ids):
        material = requirement.material
        group = groups.setdefault(
            material.id,
            {
                "material": {"id": material.id, "sku": material.sku, "name": material.name, "kind": material.kind, "unit": material.unit, "image": material.image.url if material.image else None},
                "total_to_order": Decimal("0"),
                "orders": [],
                "due_on": None,
                "suggested_supplier": None,
                "reference_price": None,
                "currency": None,
                "lead_time_days": None,
                "candidates": [],
                "alert_id": None,
                "_first": requirement,
            },
        )
        due = requirement.order.promised_on - timedelta(days=config.buffer_days)
        remaining = remaining_to_order(requirement)
        group["total_to_order"] += remaining
        group["orders"].append({"id": requirement.order_id, "code": requirement.order.code, "customer_name": requirement.order.customer.name, "qty": str(remaining), "due_on": due})
        group["due_on"] = min(group["due_on"], due) if group["due_on"] else due
    from manager.models import Alert

    for material_id, group in groups.items():
        candidates = rank_candidates(group.pop("_first"))
        if candidates:
            best = candidates[0]
            supplier = Supplier.objects.get(pk=best["supplier_id"])
            group["suggested_supplier"] = {"id": best["supplier_id"], "name": best["supplier_name"]}
            group["currency"] = best["currency"] if with_prices else None
            group["lead_time_days"] = supplier.lead_time_days
            group["reference_price"] = best["unit_price"] if with_prices else None
            if with_prices:  # The "Cambiar" menu: every supplier with a rate, best first.
                group["candidates"] = [
                    {"supplier": {"id": c["supplier_id"], "name": c["supplier_name"]}, "unit_price": c["unit_price"], "currency": c["currency"], "score": c["score"]}
                    for c in candidates
                ]
        alert = Alert.objects.filter(kind="purchase_suggested", status="open", detail__material__id=material_id).order_by("-id").first()
        group["alert_id"] = alert.id if alert else None
        group["total_to_order"] = str(group["total_to_order"].quantize(Decimal("0.01")))
    return list(groups.values())


def generate_purchase_orders(material_ids=None, *, actor, supplier_overrides=None) -> dict:
    """One suggested purchase order per material for every open requirement of the confirmed
    orders (all materials, or the ids given), with one item per requirement, and one
    `approve_assignment` decision for the batch. Idempotent: a material with nothing open is
    skipped. `supplier_overrides` ({material_id: supplier_id}) forces the supplier of a material
    ("Cambiar"); it must have a current rate. Returns
    `{"created": [PurchaseOrder], "decision": Decision | None, "skipped": [{material_id, reason}]}`."""
    require_role(actor, "manager", "production")
    requirements = open_material_requirements(material_ids)
    overrides = {int(k): int(v) for k, v in (supplier_overrides or {}).items()}
    with transaction.atomic():
        created, decision = match_requirements(requirements, consolidate=True, supplier_overrides=overrides)
        ordered = {po.items.first().requirement.material_id for po in created if po.items.exists()}
        if ordered:  # The suggestion is answered: close it before the next tick can repeat it.
            from manager.models import Alert

            Alert.objects.filter(kind="purchase_suggested", status__in=("open", "acknowledged"), material_id__in=ordered).update(
                status="resolved", resolved_at=clock.now()
            )
    with_requirements = {r.material_id for r in requirements}
    skipped = [
        {"material_id": material_id, "reason": "sin proveedor con tarifa vigente" if material_id in with_requirements else "sin requerimientos abiertos"}
        for material_id in sorted(set(material_ids or []) | with_requirements)
        if material_id not in ordered
    ]
    return {"created": created, "decision": decision, "skipped": skipped}


def sync_requirement_status(requirement: Requirement) -> Requirement:
    """open → ordered → covered from what its purchase orders bring (ADR 0025)."""
    if requirement.qty_to_order <= 0:
        status = Requirement.Status.COVERED
    else:
        items = list(requirement.purchase_order_items.select_related("purchase_order"))
        delivered = sum((i.qty_delivered for i in items), Decimal("0"))
        live = any(i.purchase_order.status in PurchaseOrder.OPEN_STATUSES + ("suggested",) for i in items)
        status = Requirement.Status.COVERED if delivered >= requirement.qty_to_order else (Requirement.Status.ORDERED if live else Requirement.Status.OPEN)
    if requirement.status != status:
        requirement.status = status
        requirement.save(update_fields=["status", "updated_at"])
    return requirement


def _order_purchase_orders(order: Order):
    return PurchaseOrder.objects.filter(items__requirement__order=order).distinct()


def compute_critical_path(order: Order) -> Order:
    """Materials arrive, then the in-plant stages, then sewing (plant or workshop), then
    finishing. Stores the path, `estimated_on` and the risk."""
    durations = stage_durations(order)
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
    stages += sorted(customization_stages(order))
    for stage in stages:
        end = cursor + timedelta(days=int(durations.get(stage, 1)))
        path.append(_step(dict(Order.Stage.choices)[stage], "production", cursor, end, True, stage=stage))
        cursor = end

    workshops = [po for po in live if po.supplier.kind == "workshop"]
    if workshops:
        sewing_end = max(po_date(po) for po in workshops)
        for po in workshops:
            path.append(_step(f"Costura {po.code}", "workshop", cursor, po_date(po), po_date(po) == sewing_end, po))
        cursor = max(sewing_end, cursor)
    else:
        end = cursor + timedelta(days=int(durations.get("sewing", 3)))
        path.append(_step("Costura en planta", "production", cursor, end, True, stage="sewing"))
        cursor = end

    end = cursor + timedelta(days=int(durations.get("finishing", 1)))
    path.append(_step("Acabado y entrega", "delivery", cursor, end, True, stage="finishing"))

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


def _step(name, kind, start, end, critical, po=None, *, stage=None):
    """A supplier's date before the step's start (the plant hands the cut pieces after the
    workshop's deadline, a committed date already past) never draws a step backwards: it ends
    at its start and `late_by` says by how many days."""
    late_by = max((start - end).days, 0)
    end = max(start, end)
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
        "stage": stage,  # the key of `stage_overrides` / `Config.stage_durations`; null for supplier steps
        "late_by": late_by or None,
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


def match_requirements(requirements: list[Requirement], *, exclude: Supplier | None = None, redistributed_from=None, consolidate: bool = False, supplier_overrides=None):
    """Step 3: one suggested purchase order per requirement and supplier; a large workshop
    requirement is split across workshops when the first one lacks free capacity. With
    `consolidate`, the requirements of the same material become ONE purchase order with an item
    per requirement (ADR 0025 A). Then one `approve_assignment` decision for the whole batch."""
    from manager.services import create_decision

    config = Config.load()
    created: list[PurchaseOrder] = []
    proposal: list[dict] = []
    all_requirements = list(requirements)
    with transaction.atomic():
        if consolidate:
            groups: dict[tuple, list[Requirement]] = {}
            for requirement in requirements:
                groups.setdefault((requirement.kind, requirement.material_id, requirement.product_id), []).append(requirement)
            for group in groups.values():
                pending = [(r, remaining_to_order(r)) for r in group]
                pending = [(r, remaining) for r, remaining in pending if remaining > 0]
                if not pending:
                    continue
                candidates = rank_candidates(pending[0][0], exclude=exclude)
                if not candidates:
                    logger.warning("match: no supplier for material %s", pending[0][0].material_id)
                    continue
                candidate = candidates[0]
                forced = (supplier_overrides or {}).get(pending[0][0].material_id)
                if forced:
                    candidate = next((c for c in candidates if c["supplier_id"] == forced), None)
                    if candidate is None:
                        material = pending[0][0].material
                        raise UnknownReference(f"El proveedor {forced} no tiene tarifa vigente para {material.name if material else 'el insumo'}")
                supplier = Supplier.objects.get(pk=candidate["supplier_id"])
                due = min(r.order.promised_on for r, _ in pending) - timedelta(days=config.buffer_days)
                # A suggested (not yet approved) purchase order of the same material and supplier
                # absorbs the new requirements instead of a second one (ADR 0025 A.7).
                po = (
                    PurchaseOrder.objects.filter(status=PurchaseOrder.Status.SUGGESTED, supplier=supplier, items__requirement__material_id=pending[0][0].material_id)
                    .order_by("id")
                    .first()
                    if pending[0][0].material_id
                    else None
                )
                merged = po is not None
                if merged:
                    po.internal_due_on = min(po.internal_due_on, due) if po.internal_due_on else due
                    po.save(update_fields=["internal_due_on", "updated_at"])
                else:
                    po = PurchaseOrder.objects.create(
                        code=_next_code(pending[0][0].kind), supplier=supplier, suggested_supplier=supplier,
                        rationale=candidate["rationale"], scores=candidate["scores"], internal_due_on=due,
                    )
                for requirement, remaining in pending:
                    PurchaseOrderItem.objects.create(purchase_order=po, requirement=requirement, quantity=remaining, unit_price=Decimal(candidate["unit_price"]))
                    sync_requirement_status(requirement)
                if not merged:
                    StatusChange.objects.create(purchase_order=po, status=po.status, at=clock.now(), actor="system", note=candidate["rationale"][:300])
                created.append(po)
                items = list(po.items.select_related("requirement__order"))
                proposal.append(
                    {
                        "purchase_order": {"id": po.id, "code": po.code},
                        "purchase_order_code": po.code,
                        "supplier": {"id": supplier.id, "name": supplier.name},
                        "quantity": str(sum((i.quantity for i in items), Decimal("0"))),
                        "unit_price": candidate["unit_price"],
                        "currency": supplier.currency,
                        "committed_on": None,
                        "rationale": candidate["rationale"],
                        "merged": merged,
                        "orders": [{"id": i.requirement.order_id, "code": i.requirement.order.code, "qty": str(i.quantity)} for i in items],
                        "candidates": [
                            {**{k: v for k, v in c.items() if k != "free_capacity"}, "supplier": {"id": c["supplier_id"], "name": c["supplier_name"]}}
                            for c in candidates
                        ],
                    }
                )
            requirements = []  # The per-requirement loop below has nothing left to do.
        for requirement in requirements:
            remaining = remaining_to_order(requirement)
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
                sync_requirement_status(requirement)
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
        orders = {req.order for req in all_requirements}
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
        if decision.purchase_orders.count() != len(created) or any(entry.get("merged") for entry in proposal):
            _refresh_decision(decision, created, proposal, detail)
    return created, decision


def _refresh_decision(decision, created, proposal, detail) -> None:
    """A batch that joined an existing pending decision (merged purchase orders): the decision
    covers every purchase order of the batch and its proposal entries are replaced by code."""
    from manager.models import Decision

    decision.purchase_orders.add(*created)
    by_code = {entry.get("purchase_order_code"): entry for entry in decision.detail.get("proposal", [])}
    for entry in proposal:
        by_code[entry["purchase_order_code"]] = entry
    pos = list(decision.purchase_orders.select_related("supplier"))
    decision.detail = {**decision.detail, "after": detail.get("after"), "proposal": list(by_code.values())}
    decision.summary = f"Asignar {len(pos)} pedido(s) a {', '.join(sorted({po.supplier.name for po in pos}))}"[:300]
    decision.save(update_fields=["detail", "summary", "updated_at"])


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
    return _covered_by(requirement.purchase_order_items.select_related("purchase_order"))


def _covered_by(items) -> Decimal:
    """`_covered` over items already loaded (with their purchase order), for the aggregates."""
    total = Decimal("0")
    for item in items:
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
        po.save(update_fields=["committed_on", "terms", "updated_at"])  # follow-ups: the tick plans them (ADR 0027)
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


IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic")


def image_name(field) -> str:
    """The storage name of a file field when it holds an image, else empty."""
    name = getattr(field, "name", "") or ""
    return name if name.lower().endswith(IMAGE_SUFFIXES) else ""


def record_progress(po: PurchaseOrder, *, units_done: int, note: str = "", message_id=None, photo=None, actor) -> ProgressReport:
    """A progress report from WhatsApp (`message_id`), the dashboard (`actor`) or the public page.
    A WhatsApp or simulator report without its own photo shows the image of its message: the
    agent's tool only passes the message (agente, 11/10 04:30), and the file is shared, not copied."""
    if actor is not None:
        require_role(actor, "production", "manager")
    if not photo and message_id:
        from messaging.models import Message

        message = Message.objects.filter(pk=message_id).first()
        photo = image_name(message.media) if message else ""
    with transaction.atomic():
        report = ProgressReport.objects.create(
            purchase_order=po,
            units_done=units_done,
            note=note,
            message_id=message_id,
            photo=photo,
            reported_at=clock.now(),
        )
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
        for item in po.items.select_related("requirement"):
            sync_requirement_status(item.requirement)
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
        for item in po.items.select_related("requirement"):
            sync_requirement_status(item.requirement)
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


def answer_follow_up_requests(request_ids, *, summary: str) -> int:
    """The agent's `answer_follow_up` (ADR 0027 §6): see `follow_up_requests`."""
    from .follow_up_requests import answer_follow_up_requests as answer

    return answer(request_ids, summary=summary)
