"""Supplier scores and payment totals, computed on demand (the demo data is small)."""

from collections import defaultdict
from decimal import Decimal

from operations.models import Payment, PurchaseOrder

from .models import Supplier

OPEN = PurchaseOrder.OPEN_STATUSES


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
