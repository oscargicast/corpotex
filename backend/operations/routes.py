"""Multi-stop routes over Piura (ADR 0024, B4.8): the plant first and last, one pickup per
open workshop purchase order due that day, one delivery per `ready` order. Nearest neighbour
plus a 2-opt pass over haversine distances; no external service, the path is straight lines."""

import math
from datetime import date as date_type, datetime, time, timedelta

from django.db import transaction
from django.utils import timezone

from core import clock
from core.models import Config

from .models import Order, PurchaseOrder, Route, RouteStop

SPEED_KMH = 25
STOP_MINUTES = 10
START_HOUR = 8


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def _pickup_date(po: PurchaseOrder):
    return po.committed_on or po.internal_due_on


def candidate_stops(date, *, exclude=()) -> list[dict]:
    """Points with coordinates for that day. `exclude` leaves purchase orders out (the "before"
    picture of a redistribution)."""
    excluded = {po.id for po in exclude}
    stops = []
    pos = (
        PurchaseOrder.objects.filter(status__in=PurchaseOrder.OPEN_STATUSES + ("suggested",), supplier__kind="workshop")
        .exclude(supplier__is_in_house=True)
        .select_related("supplier")
    )
    for po in pos:
        supplier = po.supplier
        if po.id in excluded or _pickup_date(po) != date or supplier.lat is None or supplier.lng is None:
            continue
        stops.append(
            {
                "kind": RouteStop.Kind.PICKUP, "name": supplier.name, "address": supplier.address, "lat": supplier.lat, "lng": supplier.lng,
                "supplier": supplier, "purchase_order": po,
            }
        )
    today = clock.today()
    for order in Order.objects.filter(status=Order.Status.READY).select_related("customer"):
        customer = order.customer
        # A ready order goes out on its promised day, or today when that day already passed.
        if max(today, order.promised_on) != date or customer.lat is None or customer.lng is None:
            continue
        stops.append(
            {
                "kind": RouteStop.Kind.DELIVERY, "name": customer.name, "address": customer.address, "lat": customer.lat, "lng": customer.lng,
                "customer": customer, "order": order,
            }
        )
    return stops


def order_stops(plant: tuple[float, float], stops: list[dict]) -> list[dict]:
    """Nearest neighbour from the plant, then 2-opt until no swap shortens the loop."""
    remaining = list(stops)
    ordered: list[dict] = []
    here = plant
    while remaining:
        nearest = min(remaining, key=lambda s: haversine_km(here, (s["lat"], s["lng"])))
        remaining.remove(nearest)
        ordered.append(nearest)
        here = (nearest["lat"], nearest["lng"])
    return two_opt(plant, ordered)


def tour_length(plant, ordered) -> float:
    points = [plant] + [(s["lat"], s["lng"]) for s in ordered] + [plant]
    return sum(haversine_km(points[i], points[i + 1]) for i in range(len(points) - 1))


def two_opt(plant, ordered: list[dict]) -> list[dict]:
    best = list(ordered)
    improved = True
    while improved and len(best) > 2:
        improved = False
        for i in range(len(best) - 1):
            for j in range(i + 1, len(best)):
                candidate = best[: i] + best[i : j + 1][::-1] + best[j + 1 :]
                if tour_length(plant, candidate) + 1e-9 < tour_length(plant, best):
                    best, improved = candidate, True
    return best


def current_route(date=None) -> Route | None:
    """The route in force: `planned` or `in_progress`, for `date` or the nearest upcoming day."""
    qs = Route.objects.filter(status__in=(Route.Status.PLANNED, Route.Status.IN_PROGRESS))
    if date is not None:
        return qs.filter(date=date).order_by("-id").first()
    today = clock.today()
    upcoming = qs.filter(date__gte=today).order_by("date", "-id").first()
    return upcoming or qs.order_by("-date", "-id").first()


def plan_route(date, *, actor=None, status: str = Route.Status.PLANNED, recalculated_from: Route | None = None, exclude=()) -> Route | None:
    """Plans the route of `date`. `planned` replaces the day's previous planned route (which
    becomes `replaced`, linked through `recalculated_from`); `proposed` leaves it untouched
    until the manager decides. None without plant coordinates."""
    if actor is not None:
        from core.permissions import require_role

        require_role(actor, "manager", "production")
    if isinstance(date, str):
        date = date_type.fromisoformat(date)
    config = Config.load()
    if config.plant_lat is None or config.plant_lng is None:
        return None
    plant = (config.plant_lat, config.plant_lng)
    ordered = order_stops(plant, candidate_stops(date, exclude=exclude))
    with transaction.atomic():
        previous = None
        if status == Route.Status.PLANNED:
            previous = current_route(date)
            recalculated_from = recalculated_from or previous
        route = Route.objects.create(date=date, status=status, recalculated_from=recalculated_from)
        tz = timezone.get_default_timezone()
        eta = datetime.combine(date, time(START_HOUR, 0), tzinfo=tz)
        points = [plant] + [(s["lat"], s["lng"]) for s in ordered] + [plant]
        distance = 0.0
        RouteStop.objects.create(
            route=route, position=0, kind=RouteStop.Kind.PICKUP, name=config.plant_name or "Planta", lat=plant[0], lng=plant[1], eta=eta
        )
        for index, stop in enumerate(ordered, start=1):
            leg = haversine_km(points[index - 1], points[index])
            distance += leg
            eta += timedelta(minutes=leg / SPEED_KMH * 60 + STOP_MINUTES)
            RouteStop.objects.create(
                route=route,
                position=index,
                kind=stop["kind"],
                name=stop["name"],
                address=stop.get("address", ""),
                lat=stop["lat"],
                lng=stop["lng"],
                eta=eta,
                supplier=stop.get("supplier"),
                customer=stop.get("customer"),
                purchase_order=stop.get("purchase_order"),
                order=stop.get("order"),
            )
        leg = haversine_km(points[-2], points[-1])
        distance += leg
        eta += timedelta(minutes=leg / SPEED_KMH * 60)
        RouteStop.objects.create(
            route=route, position=len(ordered) + 1, kind=RouteStop.Kind.DELIVERY, name=config.plant_name or "Planta", lat=plant[0], lng=plant[1], eta=eta
        )
        route.distance_km = round(distance, 2)
        route.duration_min = round(distance / SPEED_KMH * 60 + STOP_MINUTES * len(ordered))
        route.path = {"type": "LineString", "coordinates": [[lng, lat] for lat, lng in points]}
        route.save(update_fields=["distance_km", "duration_min", "path", "updated_at"])
        if previous is not None and previous.id != route.id:
            previous.status = Route.Status.REPLACED
            previous.save(update_fields=["status", "updated_at"])
    return route


def promote(route: Route) -> Route:
    """The manager approved the redistribution: `proposed → planned`, the day's planned route
    becomes `replaced`."""
    if route.status != Route.Status.PROPOSED:
        return route
    with transaction.atomic():
        for previous in Route.objects.filter(date=route.date, status__in=(Route.Status.PLANNED, Route.Status.IN_PROGRESS)).exclude(pk=route.pk):
            previous.status = Route.Status.REPLACED
            previous.save(update_fields=["status", "updated_at"])
        route.status = Route.Status.PLANNED
        route.save(update_fields=["status", "updated_at"])
    return route


def discard(route: Route) -> Route:
    if route.status == Route.Status.PROPOSED:
        route.status = Route.Status.DISCARDED
        route.save(update_fields=["status", "updated_at"])
    return route


def propose_for_redistribution(created: list[PurchaseOrder]) -> tuple[Route | None, Route | None]:
    """The route picture of a redistribution: the day the new purchase orders are due, as it was
    planned without them (`before`, created on the fly if nobody had planned it) and as it would
    look with them (`after`, `proposed`)."""
    dates = [_pickup_date(po) for po in created if _pickup_date(po)]
    if not dates:
        return None, None
    date = min(dates)
    before = current_route(date) or plan_route(date, exclude=created)
    if before is None:
        return None, None
    after = plan_route(date, status=Route.Status.PROPOSED, recalculated_from=before)
    return before, after
