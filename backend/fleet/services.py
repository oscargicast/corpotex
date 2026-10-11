"""Dispatches (customer orders going out) as the dashboard lists them (ADR 0026 §3)."""

from django.utils import timezone

from operations.models import Order, Route, RouteStop, StatusChange
from operations.routes import LIVE, delivery_point, with_dispatch_fields


def local_date(value):
    return timezone.localtime(value).date() if value else None


def dispatches(*, statuses=("ready", "delivered"), date_from=None, date_to=None, vehicle_ids=None, unassigned=False) -> list[dict]:
    """One row per ready or delivered order. The day is the delivery's for delivered orders and
    the scheduled one for ready orders; a ready order's vehicle is the live route carrying it,
    a delivered order's the route that delivered it."""
    orders = list(with_dispatch_fields(Order.objects.filter(status__in=statuses)).select_related("customer"))
    ids = [o.id for o in orders]
    stops: dict[int, RouteStop] = {}
    visible = LIVE + (Route.Status.COMPLETED,)
    for stop in RouteStop.objects.filter(order_id__in=ids, route__vehicle__isnull=False, route__status__in=visible).select_related("route__vehicle").order_by("route_id"):
        stops[stop.order_id] = stop  # The latest route wins.
    delivered = dict(StatusChange.objects.filter(order_id__in=ids, status="delivered").order_by("at").values_list("order_id", "at"))
    rows = []
    for order in orders:
        stop = stops.get(order.id)
        if order.status == Order.Status.READY and stop is not None and stop.route.status not in LIVE:
            stop = None  # The trip ended without it: back to the pool.
        delivered_at = None
        if order.status == Order.Status.DELIVERED:
            delivered_at = (stop.delivered_at if stop and stop.delivered_at else None) or delivered.get(order.id)
        day = local_date(delivered_at) or order.delivery_on
        if (date_from and day < date_from) or (date_to and day > date_to):
            continue
        if unassigned and (order.status != Order.Status.READY or stop is not None):
            continue
        if vehicle_ids and (stop is None or stop.route.vehicle_id not in vehicle_ids):
            continue
        when = local_date(delivered_at) or (local_date(stop.eta) if stop and stop.eta else order.delivery_on)
        point = delivery_point(order)
        vehicle = stop.route.vehicle if stop else None
        rows.append(
            {
                "order": {"id": order.id, "code": order.code, "customer_name": order.customer.name, "units": order.units, "promised_on": order.promised_on},
                "status": order.status,
                "scheduled_on": order.delivery_on,
                "delivered_at": delivered_at,
                "address": point["address"] or "",
                "lat": point["lat"],
                "lng": point["lng"],
                "route_id": stop.route_id if stop else None,
                "vehicle": {"id": vehicle.id, "name": vehicle.name, "color": vehicle.color} if vehicle else None,
                "stop": {"id": stop.id, "position": stop.position, "eta": stop.eta} if stop else None,
                "on_time": when <= order.promised_on,
            }
        )
    rows.sort(key=lambda r: (r["delivered_at"] is not None, local_date(r["delivered_at"]) or r["scheduled_on"], r["stop"]["eta"] if r["stop"] and r["stop"]["eta"] else timezone.now(), r["order"]["code"]))
    return rows
