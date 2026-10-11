"""Supplier scores and payment totals, computed on demand (the demo data is small)."""

from collections import defaultdict
from decimal import Decimal

from core import clock
from operations.models import Payment, PurchaseOrder

from .models import Supplier

OPEN = PurchaseOrder.OPEN_STATUSES


def _normalize(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def create_suggested_suppliers(candidates: list[dict], *, actor) -> dict:
    """The assistant's `suggest_suppliers` tool (ADR 0024): web candidates become suppliers
    `pending_review`. The url and excerpt go to `source_detail`, never to `notes` (which the
    WhatsApp agent reads). Deduplicates by normalized name + city against existing suppliers."""
    from core.permissions import require_role

    require_role(actor, "manager")
    existing = {(_normalize(s.name), _normalize(s.city)) for s in Supplier.objects.only("name", "city")}
    created, skipped = [], []
    for candidate in candidates:
        name = " ".join(str(candidate.get("name", "")).split())[:160]
        city = " ".join(str(candidate.get("city", "")).split())[:80]
        key = (_normalize(name), _normalize(city))
        if not name or key in existing:
            skipped.append({"name": name, "city": city})
            continue
        existing.add(key)
        kind = candidate.get("kind") if candidate.get("kind") in ("workshop", "material", "finished") else "workshop"
        specialty = " ".join(str(candidate.get("specialty", "")).split())[:60]
        supplier = Supplier.objects.create(
            name=name,
            kind=kind,
            specialties=[specialty] if specialty else [],
            city=city,
            source=Supplier.Source.EXTERNAL,
            source_detail={"url": str(candidate.get("source_url", ""))[:500], "evidence": str(candidate.get("evidence", ""))[:300]},
            status=Supplier.Status.PENDING_REVIEW,
            notes="",
        )
        created.append({"id": supplier.id, "name": supplier.name, "city": supplier.city, "kind": supplier.kind})
    return {"created": created, "skipped": skipped}


def supplier_scores(supplier: Supplier) -> dict:
    """{on_time, quality} from the `rating` of its closed purchase orders; None when unrated."""
    ratings = [po.rating for po in supplier.purchase_orders.filter(rating__isnull=False) if po.rating]
    if not ratings:
        return {"on_time": None, "quality": None}
    on_time = sum(1 for r in ratings if (r.get("delay_days") or 0) <= 0) / len(ratings)
    quality = sum(float(r.get("quality") or 0) for r in ratings) / len(ratings)
    return {"on_time": round(on_time, 2), "quality": round(quality, 2)}


def supplier_load(supplier: Supplier) -> dict:
    """Units in open purchase orders and the share of the weekly capacity they take."""
    units = Decimal("0")
    for po in supplier.purchase_orders.filter(status__in=OPEN).prefetch_related("items"):
        units += sum((item.quantity for item in po.items.all()), Decimal("0"))
    pct = None
    if supplier.weekly_capacity:
        pct = round(float(units) / supplier.weekly_capacity * 100, 1)
    return {"units": units, "pct": pct}


def payments_summary(payments) -> list[dict]:
    """Paid and pending totals grouped by currency; PEN and USD are never added together."""
    totals: dict[str, dict] = defaultdict(lambda: {"paid": Decimal("0"), "pending": Decimal("0"), "overdue_count": 0})
    for payment in payments:
        currency = payment.purchase_order.supplier.currency
        bucket = totals[currency]
        if payment.paid_at:
            bucket["paid"] += payment.amount
        else:
            bucket["pending"] += payment.amount
            if payment.is_overdue:
                bucket["overdue_count"] += 1
    return [
        {
            "currency": currency,
            "paid": str(values["paid"].quantize(Decimal("0.01"))),
            "pending": str(values["pending"].quantize(Decimal("0.01"))),
            "overdue_count": values["overdue_count"],
        }
        for currency, values in sorted(totals.items())
    ]


def payments_by_supplier() -> list[dict]:
    """The Monitor's table: one row per supplier and currency."""
    rows = []
    payments = Payment.objects.select_related("purchase_order__supplier").order_by("purchase_order__supplier__name")
    by_supplier: dict[int, list] = defaultdict(list)
    for payment in payments:
        by_supplier[payment.purchase_order.supplier_id].append(payment)
    for supplier_id, items in by_supplier.items():
        supplier = items[0].purchase_order.supplier
        for summary in payments_summary(items):
            rows.append({"supplier": {"id": supplier.id, "name": supplier.name}, **summary})
    return rows


# --- registration, numbers and import (B4.5) ------------------------------------------------


class NumberConflict(Exception):
    """The phone already belongs to a number, or the number has a conversation (the view answers 400)."""


SUPPLIER_FIELDS = (
    "name", "kind", "specialties", "city", "address", "lat", "lng", "weekly_capacity",
    "lead_time_days", "follow_up_every_hours", "follow_up_mode", "currency", "notes", "is_in_house", "agent_paused",
)


def _clean(data: dict) -> dict:
    cleaned = {k: v for k, v in data.items() if k in SUPPLIER_FIELDS}
    if "specialties" in cleaned:
        cleaned["specialties"] = [s.strip() for s in cleaned["specialties"] if s and s.strip()]
    return cleaned


def create_supplier(data: dict, *, actor, source: str = "registered", status: str = "active") -> Supplier:
    """Manager registration (`POST /api/suppliers/`) and the public self-registration. An optional
    `phone` creates its AllowedNumber inactive: the manager activates it after checking (ADR 0016)."""
    from messaging.models import AllowedNumber

    if source != Supplier.Source.SELF_REGISTERED:
        from core.permissions import require_role

        require_role(actor, "manager")
    phone = (data.get("phone") or "").strip()
    if phone and AllowedNumber.objects.filter(phone=phone).exists():
        raise NumberConflict(f"El número {phone} ya está registrado")
    supplier = Supplier.objects.create(source=source, status=status, **_clean(data))
    if phone:
        AllowedNumber.objects.create(phone=phone, name=(data.get("contact_name") or "").strip(), supplier=supplier, active=False)
    if data.get("rates"):
        replace_rates(supplier, data["rates"])
    return supplier


def update_supplier(supplier: Supplier, data: dict, *, actor) -> Supplier:
    """`PATCH /api/suppliers/<id>/`: approve or discard (`status`), edit the card, rename the
    contact and replace the reference prices (`rates`, the full list)."""
    from django.db import transaction

    from core.permissions import require_role

    require_role(actor, "manager")
    with transaction.atomic():
        resumed = supplier.agent_paused and data.get("agent_paused") is False
        for field, value in _clean(data).items():
            setattr(supplier, field, value)
        if data.get("status") in dict(Supplier.Status.choices):
            supplier.status = data["status"]
        supplier.save()
        if resumed:  # ADR 0030: the first contacts approved during the pause go out now
            from messaging.services import resume_agent

            resume_agent([supplier.id])
        if data.get("contact_name") is not None:
            set_contact_name(supplier, data["contact_name"])
        if data.get("rates") is not None:
            replace_rates(supplier, data["rates"])
    return supplier


def set_contact_name(supplier: Supplier, name: str) -> None:
    """The contact is the name on the supplier's first real number (what the bot greets)."""
    number = supplier.numbers.filter(simulated=False).order_by("-active", "id").first()
    if number is not None:
        number.name = name.strip()
        number.save(update_fields=["name", "updated_at"])


class RateError(Exception):
    """A rate names a missing item, both or neither of material/product, or a bad price (400)."""


def replace_rates(supplier: Supplier, rates: list[dict]) -> list:
    """The full list of reference prices replaces the previous one. Each rate is
    `{material_id | product_id, unit_price, valid_from?}` (today by default). Purchase orders keep
    their own `unit_price`, so history does not move."""
    from core.models import Material, Product

    from .models import Rate

    built = []
    for index, raw in enumerate(rates):
        material_id, product_id = raw.get("material_id"), raw.get("product_id")
        if bool(material_id) == bool(product_id):
            raise RateError(f"Tarifa {index + 1}: indica material_id o product_id, no ambos")
        material = Material.objects.filter(pk=material_id).first() if material_id else None
        product = Product.objects.filter(pk=product_id).first() if product_id else None
        if material_id and material is None:
            raise RateError(f"Tarifa {index + 1}: el insumo {material_id} no existe")
        if product_id and product is None:
            raise RateError(f"Tarifa {index + 1}: el producto {product_id} no existe")
        price = Decimal(str(raw.get("unit_price", "0")))
        if price <= 0:
            raise RateError(f"Tarifa {index + 1}: el precio debe ser mayor que 0")
        built.append(Rate(supplier=supplier, material=material, product=product, unit_price=price, valid_from=raw.get("valid_from") or clock.today()))
    supplier.rates.all().delete()
    return Rate.objects.bulk_create(built)


def simulated_phone(text: str) -> str:
    """The seed's format for a simulator number: `sim-<slug>` (ASCII, lowercase, dashes)."""
    import re
    import unicodedata

    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return f"sim-{slug}"[:40]


def add_number(supplier: Supplier, *, phone: str = "", name: str = "", simulated: bool = False, actor):
    """A real number is created inactive, for the manager to switch on after checking (ADR 0016).
    A simulated one (P6b, the "Para pruebas" checkbox) takes the seed's `sim-<slug>` format, from
    the phone typed or the supplier's name, and is active at once so the simulator takes it."""
    from core.permissions import require_role
    from messaging.models import AllowedNumber

    require_role(actor, "manager")
    phone = phone.strip()
    if simulated:
        phone = phone if phone.startswith("sim-") else simulated_phone(phone or supplier.name)
        base, n = phone, 2
        while AllowedNumber.objects.filter(phone=phone).exists():  # a second simulated number for the same supplier
            phone, n = f"{base[:40 - len(str(n)) - 1]}-{n}", n + 1
    elif not phone:
        raise NumberConflict("Falta el número")
    if AllowedNumber.objects.filter(phone=phone).exists():
        raise NumberConflict(f"El número {phone} ya está registrado")
    return AllowedNumber.objects.create(phone=phone, name=name.strip(), supplier=supplier, active=simulated, simulated=simulated)


def update_number(number, *, active=None, name=None, phone=None, actor):
    """Numbers are never deleted: they are deactivated. The phone changes only while the number
    has no conversation, so history never points at another person."""
    from core.permissions import require_role
    from messaging.models import AllowedNumber

    require_role(actor, "manager")
    fields = []
    if active is not None:
        number.active = active
        fields.append("active")
    if name is not None:
        number.name = name.strip()
        fields.append("name")
    if phone is not None and phone.strip() != number.phone:
        phone = phone.strip()
        if number.conversations.exists():
            raise NumberConflict("El número ya tiene conversación; agrega otro número en vez de cambiarlo")
        if AllowedNumber.objects.filter(phone=phone).exclude(pk=number.pk).exists():
            raise NumberConflict(f"El número {phone} ya está registrado")
        number.phone = phone
        fields.append("phone")
    if fields:
        number.save(update_fields=fields + ["updated_at"])
    return number


CSV_COLUMNS = ("name", "kind", "specialties", "city", "weekly_capacity", "lead_time_days", "currency", "phone", "lat", "lng")


def import_suppliers_csv(text: str, *, actor) -> dict:
    """`POST /api/suppliers/import/`: one row per supplier; `specialties` separated by `;`. A row
    matches an existing supplier by `phone` first, then by `name`. Returns {created, updated, errors}."""
    import csv
    from io import StringIO

    from core.permissions import require_role
    from messaging.models import AllowedNumber

    require_role(actor, "manager")
    reader = csv.DictReader(StringIO(text.lstrip("﻿")))
    missing = [c for c in ("name", "kind") if c not in (reader.fieldnames or [])]
    if missing:
        return {"created": [], "updated": [], "errors": [{"row": 0, "error": f"Faltan columnas: {', '.join(missing)}"}]}
    created, updated, errors = [], [], []
    kinds = dict(Supplier.kind.field.choices)
    for index, row in enumerate(reader, start=2):
        row = {k: (v or "").strip() for k, v in row.items() if k}
        name, kind = row.get("name", ""), row.get("kind", "")
        if not name or kind not in kinds:
            errors.append({"row": index, "error": "name vacío o kind inválido (material, workshop, finished)"})
            continue
        try:
            data = {
                "name": name,
                "kind": kind,
                "specialties": [s for s in row.get("specialties", "").split(";") if s.strip()],
                "city": row.get("city", ""),
                "weekly_capacity": int(row["weekly_capacity"]) if row.get("weekly_capacity") else None,
                "lead_time_days": int(row["lead_time_days"]) if row.get("lead_time_days") else 7,
                "currency": row.get("currency") or "PEN",
                "lat": float(row["lat"]) if row.get("lat") else None,
                "lng": float(row["lng"]) if row.get("lng") else None,
            }
        except ValueError as exc:
            errors.append({"row": index, "error": f"Valor inválido: {exc}"})
            continue
        phone = row.get("phone", "")
        number = AllowedNumber.objects.filter(phone=phone).select_related("supplier").first() if phone else None
        existing = number.supplier if number and number.supplier_id else None
        if existing is None:
            existing = Supplier.objects.filter(name__iexact=name).first()
            if existing:
                data.pop("name")  # Matched by name: the stored spelling stays.
        if existing:
            for field, value in data.items():
                if value not in (None, "", []):
                    setattr(existing, field, value)
            existing.save()
            if phone and not number:
                AllowedNumber.objects.create(phone=phone, supplier=existing, active=False)
            updated.append({"id": existing.id, "name": existing.name})
        else:
            supplier = create_supplier({**data, "phone": phone}, actor=actor)
            created.append({"id": supplier.id, "name": supplier.name})
    return {"created": created, "updated": updated, "errors": errors}
