"""Delivery routes over Piura (ADR 0024, B4.8; corrected 10/10 23:35): they leave the plant
and deliver orders to customers. There are no supplier pickups: Lima ships through Sullana
Express and the workshops deliver at the plant. Nearest neighbour plus a 2-opt pass over
haversine distances; no external service, the path is straight lines.

Routes without a vehicle are the projected routes of the redistribution (ADR 0024) and keep
working as before. Routes with a vehicle come from `plan_day` (ADR 0026): ready orders shared
among the fleet by capacity and shift, one trip per vehicle and day."""

import math
from dataclasses import dataclass, field
from datetime import date as date_type, datetime, time, timedelta

from django.db import transaction
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from core import clock
from core.models import Config

from .models import Order, Route, RouteStop

SPEED_KMH = 25
STOP_MINUTES = 10
START_HOUR = 8
SHIFT_END_HOUR = 18
CLOSED = (Order.Status.DELIVERED, Order.Status.CANCELLED)
LIVE = (Route.Status.PLANNED, Route.Status.IN_PROGRESS)


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1, lat2, lng2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lng2 - lng1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def delivery_date(order: Order):
    """The day the order goes out: the day Produccion scheduled, else the critical path's
    estimate, else the promised day."""
    return order.scheduled_delivery_on or order.estimated_on or order.promised_on


def delivery_point(order: Order) -> dict:
    """Where the order is delivered: its own address (a Caja Piura agency) or the customer's."""
    customer = order.customer
    if order.delivery_lat is not None and order.delivery_lng is not None:
        return {"name": customer.name, "address": order.delivery_address or customer.address, "lat": order.delivery_lat, "lng": order.delivery_lng}
    return {"name": customer.name, "address": customer.address, "lat": customer.lat, "lng": customer.lng}


def candidate_stops(date, *, exclude_orders=(), include_orders=()) -> list[dict]:
    """One delivery per open order due that day whose customer has coordinates. `exclude_orders`
    leaves orders out; `include_orders` forces orders in whatever their day (the "before" picture
    of a redistribution, planned as it was)."""
    excluded = {o.id for o in exclude_orders}
    included = {o.id for o in include_orders}
    stops = []
    for order in Order.objects.exclude(status__in=CLOSED).select_related("customer").order_by("id"):
        point = delivery_point(order)
        if order.id in excluded or point["lat"] is None or point["lng"] is None:
            continue
        if delivery_date(order) != date and order.id not in included:
            continue
        stops.append({"kind": RouteStop.Kind.DELIVERY, **point, "customer": order.customer, "order": order})
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
    """The route in force: `planned` or `in_progress`. With `date`, that day's; without it, the
    upcoming route touched most recently (a just-approved recalculation wins over an older plan),
    else the latest one. Only routes without a vehicle: the fleet's trips live apart (ADR 0026)."""
    qs = Route.objects.filter(status__in=LIVE, vehicle__isnull=True)
    if date is not None:
        if isinstance(date, str):
            date = date_type.fromisoformat(date)
        return qs.filter(date=date).order_by("-id").first()
    today = clock.today()
    upcoming = qs.filter(date__gte=today).order_by("-updated_at", "-id").first()
    return upcoming or qs.order_by("-date", "-id").first()


def plan_route(
    date, *, actor=None, status: str = Route.Status.PLANNED, recalculated_from: Route | None = None, exclude_orders=(), include_orders=()
) -> Route | None:
    """Plans the deliveries of `date`. `planned` replaces the day's previous planned route (which
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
    plant_name = config.plant_name or "Planta"
    ordered = order_stops(plant, candidate_stops(date, exclude_orders=exclude_orders, include_orders=include_orders))
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
        RouteStop.objects.create(route=route, position=0, kind=RouteStop.Kind.PLANT, name=plant_name, lat=plant[0], lng=plant[1], eta=eta)
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
                customer=stop.get("customer"),
                order=stop.get("order"),
            )
        leg = haversine_km(points[-2], points[-1])
        distance += leg
        eta += timedelta(minutes=leg / SPEED_KMH * 60)
        RouteStop.objects.create(route=route, position=len(ordered) + 1, kind=RouteStop.Kind.PLANT, name=plant_name, lat=plant[0], lng=plant[1], eta=eta)
        route.distance_km = round(distance, 2)
        route.duration_min = round(distance / SPEED_KMH * 60 + STOP_MINUTES * len(ordered))
        route.path = {"type": "LineString", "coordinates": [[lng, lat] for lat, lng in points]}
        route.save(update_fields=["distance_km", "duration_min", "path", "updated_at"])
        if previous is not None and previous.id != route.id:
            previous.status = Route.Status.REPLACED
            previous.save(update_fields=["status", "updated_at"])
    return route


def promote(route: Route) -> Route:
    """The manager approved the redistribution: `proposed → planned`. The route it recalculates
    (and any planned route of its day) becomes `replaced`; when the delivery moved to another
    day, the old day is re-planned without it if anything else goes out that day."""
    if route.status != Route.Status.PROPOSED:
        return route
    with transaction.atomic():
        for previous in Route.objects.filter(date=route.date, status__in=LIVE, vehicle__isnull=True).exclude(pk=route.pk):
            previous.status = Route.Status.REPLACED
            previous.save(update_fields=["status", "updated_at"])
        before = route.recalculated_from
        if before is not None and before.date != route.date and before.status in (Route.Status.PLANNED, Route.Status.IN_PROGRESS):
            before.status = Route.Status.REPLACED
            before.save(update_fields=["status", "updated_at"])
            if candidate_stops(before.date):
                plan_route(before.date, recalculated_from=before)
        route.status = Route.Status.PLANNED
        route.save(update_fields=["status", "updated_at"])
    return route


def discard(route: Route) -> Route:
    if route.status == Route.Status.PROPOSED:
        route.status = Route.Status.DISCARDED
        route.save(update_fields=["status", "updated_at"])
    return route


def propose_for_redistribution(orders, old_dates: dict) -> tuple[Route | None, Route | None]:
    """The route picture of a redistribution for the affected order: `before`, the planned
    route of the delivery day it had (planned on the fly, as it was, if nobody had planned it),
    and `after`, a `proposed` route of its new delivery day carrying it, linked through
    `recalculated_from`."""
    orders = sorted(orders, key=lambda o: o.id)
    if not orders:
        return None, None
    order = orders[0]
    order.refresh_from_db()
    old = old_dates.get(order.id) or delivery_date(order)
    new = delivery_date(order)
    before = current_route(old) or plan_route(old, include_orders=[order])
    if before is None:
        return None, None
    after = plan_route(new, status=Route.Status.PROPOSED, recalculated_from=before, include_orders=[order])
    return before, after


# --- fleet: per-vehicle planning (ADR 0026) ---------------------------------------------------


class DispatchError(Exception):
    """A dispatch change that cannot happen (the order already left, the route is closed). The
    views answer 409 with the message, which is for people."""


REASONS = {"capacity": "No cabe: capacidad", "shift": "No cabe: jornada", "no_coordinates": "Sin coordenadas"}


@dataclass
class DayPlan:
    routes: list[Route] = field(default_factory=list)
    unassigned: list[dict] = field(default_factory=list)  # {order_id, code, reason, reason_display}
    suggested_next_day: list[int] = field(default_factory=list)


def plant_point() -> tuple[tuple[float, float] | None, str]:
    config = Config.load()
    if config.plant_lat is None or config.plant_lng is None:
        return None, ""
    return (config.plant_lat, config.plant_lng), config.plant_name or "Planta"


def with_dispatch_fields(qs):
    """Annotates `units` (garments) and `delivery_on` (`delivery_date` in SQL)."""
    return qs.annotate(units=Coalesce(Sum("items__quantity"), 0), delivery_on=Coalesce("scheduled_delivery_on", "estimated_on", "promised_on"))


def dispatch_pool(date, *, order_ids=None, vehicles=None) -> list[Order]:
    """Ready orders that go out on `date`, plus the overdue ones (their day already passed and
    no vehicle carries them), never one on a route already on the road nor one that a vehicle
    outside `vehicles` already carries that day. Overdue first, then by promised day."""
    today = clock.today()
    on_the_road = RouteStop.objects.filter(route__status=Route.Status.IN_PROGRESS, route__vehicle__isnull=False, order__isnull=False).values("order_id")
    qs = with_dispatch_fields(Order.objects.filter(status=Order.Status.READY)).select_related("customer").exclude(id__in=on_the_road)
    if vehicles is not None:
        others = RouteStop.objects.filter(route__status=Route.Status.PLANNED, route__date=date, route__vehicle__isnull=False, order__isnull=False)
        qs = qs.exclude(id__in=others.exclude(route__vehicle__in=vehicles).values("order_id"))
    planned_elsewhere = RouteStop.objects.filter(route__status=Route.Status.PLANNED, route__vehicle__isnull=False, order__isnull=False).exclude(route__date=date)
    overdue = Q(delivery_on__lt=today) & ~Q(id__in=planned_elsewhere.values("order_id")) if date >= today else Q(pk__in=[])
    qs = qs.filter(Q(delivery_on=date) | overdue)
    if order_ids:
        qs = qs.filter(id__in=order_ids)
    return sorted(qs, key=lambda o: (o.delivery_on >= date, o.promised_on, o.id))


def stop_for(order: Order) -> dict:
    return {"kind": RouteStop.Kind.DELIVERY, **delivery_point(order), "customer": order.customer, "order": order, "units": getattr(order, "units", None) or 0}


def trip_minutes(plant, ordered: list[dict]) -> float:
    return tour_length(plant, ordered) / SPEED_KMH * 60 + STOP_MINUTES * len(ordered) if ordered else 0.0


def shift_minutes() -> int:
    return (SHIFT_END_HOUR - START_HOUR) * 60


def fits(vehicle, plant, stops: list[dict]) -> bool:
    if sum(s["units"] for s in stops) > vehicle.capacity_units:
        return False
    return trip_minutes(plant, order_stops(plant, stops)) <= shift_minutes()


def sweep(plant, stops: list[dict]) -> list[dict]:
    """By angle around the plant, starting after the widest empty sector so that no cluster is
    split across the start."""
    if len(stops) < 2:
        return list(stops)
    ordered = sorted(stops, key=lambda s: math.atan2(s["lat"] - plant[0], s["lng"] - plant[1]))
    angles = [math.atan2(s["lat"] - plant[0], s["lng"] - plant[1]) for s in ordered]
    gaps = [(angles[(i + 1) % len(angles)] - angles[i]) % (2 * math.pi) for i in range(len(angles))]
    start = (gaps.index(max(gaps)) + 1) % len(ordered)
    return ordered[start:] + ordered[:start]


def assign(vehicles, plant, stops: list[dict]) -> tuple[dict[int, list[dict]], list[dict]]:
    """Sweep: fill the vehicles in turn (largest first) following the angle; a stop that does
    not fit the current vehicle opens the next one, and a later vehicle with room takes it
    before giving up. Returns ({vehicle_id: stops}, leftovers)."""
    loads: dict[int, list[dict]] = {v.id: [] for v in vehicles}
    leftovers, current = [], 0
    for stop in sweep(plant, stops):
        for index in list(range(current, len(vehicles))) + list(range(current)):
            vehicle = vehicles[index]
            if fits(vehicle, plant, loads[vehicle.id] + [stop]):
                loads[vehicle.id].append(stop)
                current = max(current, index)
                break
        else:
            leftovers.append(stop)
    return loads, leftovers


def improve(vehicles, plant, loads: dict[int, list[dict]]) -> None:
    """Relocation: move a stop to another vehicle when the total distance drops and neither
    vehicle breaks its capacity or shift. Repeats until nothing improves."""
    for _ in range(20):
        moved = False
        for a in vehicles:
            for stop in list(loads[a.id]):
                for b in vehicles:
                    if b.id == a.id or not fits(b, plant, loads[b.id] + [stop]):
                        continue
                    without = [s for s in loads[a.id] if s is not stop]
                    before = tour_length(plant, order_stops(plant, loads[a.id])) + tour_length(plant, order_stops(plant, loads[b.id]))
                    after = tour_length(plant, order_stops(plant, without)) + tour_length(plant, order_stops(plant, loads[b.id] + [stop]))
                    if after + 1e-6 < before:
                        loads[a.id], loads[b.id] = without, loads[b.id] + [stop]
                        moved = True
                        break
                if moved:
                    break
            if moved:
                break
        if not moved:
            return


def insert_cheapest(vehicles, plant, loads: dict[int, list[dict]], stop: dict) -> bool:
    best = None
    for vehicle in vehicles:
        candidate = loads[vehicle.id] + [stop]
        if not fits(vehicle, plant, candidate):
            continue
        extra = tour_length(plant, order_stops(plant, candidate)) - tour_length(plant, order_stops(plant, loads[vehicle.id]))
        if best is None or extra < best[0]:
            best = (extra, vehicle)
    if best is None:
        return False
    loads[best[1].id].append(stop)
    return True


def priority(stop: dict, date) -> tuple:
    """Lower sorts first: overdue, then by promised day."""
    order = stop["order"]
    return (delivery_date(order) >= date, order.promised_on, order.id)


def make_room(vehicles, plant, loads: dict[int, list[dict]], vehicle, stop: dict) -> bool:
    """Moves the vehicle's smaller stops to other vehicles until `stop` fits in it."""
    trial = {k: list(v) for k, v in loads.items()}
    for moving in sorted(trial[vehicle.id], key=lambda s: s["units"]):
        if fits(vehicle, plant, trial[vehicle.id] + [stop]):
            break
        for other in vehicles:
            if other.id != vehicle.id and fits(other, plant, trial[other.id] + [moving]):
                trial[vehicle.id].remove(moving)
                trial[other.id].append(moving)
                break
    if not fits(vehicle, plant, trial[vehicle.id] + [stop]):
        return False
    trial[vehicle.id].append(stop)
    loads.update(trial)
    return True


def eject_for(vehicles, plant, loads: dict[int, list[dict]], stop: dict, date) -> list[dict] | None:
    """Takes lower-priority stops out of a vehicle until `stop` fits; returns them (None when no
    vehicle can make room that way)."""
    for vehicle in vehicles:
        lower = sorted((s for s in loads[vehicle.id] if priority(s, date) > priority(stop, date)), key=lambda s: priority(s, date), reverse=True)
        kept, ejected = list(loads[vehicle.id]), []
        for candidate in lower:
            if fits(vehicle, plant, kept + [stop]):
                break
            kept.remove(candidate)
            ejected.append(candidate)
        if fits(vehicle, plant, kept + [stop]):
            loads[vehicle.id] = kept + [stop]
            return ejected
    return None


def why_not(vehicles, plant, loads, stop) -> str:
    """Capacity when no vehicle has room for its garments; shift when one has room but the trip
    would end after `SHIFT_END_HOUR`."""
    room = [v for v in vehicles if sum(s["units"] for s in loads[v.id]) + stop["units"] <= v.capacity_units]
    return "shift" if room else "capacity"


def vehicles_in_shift(date, vehicle_ids=None):
    from fleet.models import Vehicle

    qs = Vehicle.objects.filter(is_active=True)
    if vehicle_ids:
        qs = qs.filter(id__in=vehicle_ids)
    busy = Route.objects.filter(date=date, status=Route.Status.IN_PROGRESS, vehicle__isnull=False).values("vehicle_id")
    return list(qs.exclude(id__in=busy).order_by("-capacity_units", "id"))


def plan_day(date, *, vehicle_ids=None, order_ids=None, actor) -> DayPlan:
    """Shares the day's ready orders among the vehicles in shift (ADR 0026 §2): admission by
    priority up to the fleet's capacity, sweep by angle, nearest neighbour plus 2-opt per
    vehicle, relocation between vehicles, and what does not fit goes to `unassigned` with its
    reason and the suggestion of the next day. Replaces the planned routes of the vehicles
    involved (with `order_ids`, only those orders are planned; the rest of their old routes go
    back to the day's pool); routes on the road are never touched."""
    from core.permissions import require_role

    require_role(actor, "manager", "production")
    if isinstance(date, str):
        date = date_type.fromisoformat(date)
    plant, plant_name = plant_point()
    if plant is None:
        raise DispatchError("La planta no tiene coordenadas (Config.plant_lat/plant_lng).")
    vehicles = vehicles_in_shift(date, vehicle_ids)
    plan = DayPlan()
    capacity_left = sum(v.capacity_units for v in vehicles)
    biggest = max((v.capacity_units for v in vehicles), default=0)
    admitted, rejected = [], []
    for order in dispatch_pool(date, order_ids=order_ids, vehicles=vehicles):
        stop = stop_for(order)
        if stop["lat"] is None or stop["lng"] is None:
            plan.unassigned.append(unassigned_row(order, "no_coordinates"))
        elif stop["units"] > biggest or stop["units"] > capacity_left:
            rejected.append(stop)
        else:
            admitted.append(stop)
            capacity_left -= stop["units"]
    loads, leftovers = assign(vehicles, plant, admitted)
    # Repair by priority: what the sweep left out goes in where it fits, or after moving smaller
    # stops to another vehicle, or in place of lower-priority stops (which queue up again).
    queue = sorted(leftovers + rejected, key=lambda s: priority(s, date))
    while queue:
        stop = queue.pop(0)
        if insert_cheapest(vehicles, plant, loads, stop) or any(make_room(vehicles, plant, loads, v, stop) for v in vehicles):
            continue
        ejected = eject_for(vehicles, plant, loads, stop, date)
        if ejected is None:
            plan.unassigned.append(unassigned_row(stop["order"], why_not(vehicles, plant, loads, stop)))
        else:
            queue = sorted(queue + ejected, key=lambda s: priority(s, date))
    improve(vehicles, plant, loads)
    plan.suggested_next_day = [row["order_id"] for row in plan.unassigned if row["reason"] != "no_coordinates"]
    with transaction.atomic():
        previous = {r.vehicle_id: r for r in Route.objects.filter(date=date, status=Route.Status.PLANNED, vehicle__in=vehicles)}
        for route in previous.values():
            route.status = Route.Status.REPLACED
            route.save(update_fields=["status", "updated_at"])
        for vehicle in vehicles:
            if not loads[vehicle.id]:
                continue
            route = Route.objects.create(date=date, status=Route.Status.PLANNED, vehicle=vehicle, recalculated_from=previous.get(vehicle.id))
            write_stops(route, plant, plant_name, order_stops(plant, loads[vehicle.id]))
            plan.routes.append(route)
            for stop in loads[vehicle.id]:
                order = stop["order"]
                if delivery_date(order) != date:  # Overdue: it now goes out on this day.
                    Order.objects.filter(pk=order.pk).update(scheduled_delivery_on=date)
    return plan


def unassigned_row(order: Order, reason: str) -> dict:
    return {"order_id": order.id, "code": order.code, "reason": reason, "reason_display": REASONS[reason]}


def write_stops(route: Route, plant, plant_name: str, ordered: list[dict], *, start: datetime | None = None) -> Route:
    """(Re)writes the stops of a vehicle's route: plant, deliveries in order, plant. The ETA is
    the arrival, from `start` (08:00 of the day by default) at `SPEED_KMH`; each delivery then
    takes `STOP_MINUTES`."""
    tz = timezone.get_default_timezone()
    eta = start or datetime.combine(route.date, time(START_HOUR, 0), tzinfo=tz)
    delivered = {s.order_id: s.delivered_at for s in route.stops.filter(order__isnull=False, delivered_at__isnull=False)}
    route.stops.all().delete()
    points = [plant] + [(s["lat"], s["lng"]) for s in ordered] + [plant]
    distance = 0.0
    RouteStop.objects.create(route=route, position=0, kind=RouteStop.Kind.PLANT, name=plant_name, lat=plant[0], lng=plant[1], eta=eta)
    for index, stop in enumerate(ordered, start=1):
        leg = haversine_km(points[index - 1], points[index])
        distance += leg
        eta += timedelta(minutes=leg / SPEED_KMH * 60 + (STOP_MINUTES if index > 1 else 0))
        RouteStop.objects.create(
            route=route, position=index, kind=RouteStop.Kind.DELIVERY, name=stop["name"], address=stop.get("address") or "",
            lat=stop["lat"], lng=stop["lng"], eta=eta, customer=stop.get("customer"), order=stop.get("order"),
            delivered_at=delivered.get(stop["order"].id) if stop.get("order") else None,
        )
    leg = haversine_km(points[-2], points[-1])
    distance += leg
    eta += timedelta(minutes=leg / SPEED_KMH * 60 + (STOP_MINUTES if ordered else 0))
    RouteStop.objects.create(route=route, position=len(ordered) + 1, kind=RouteStop.Kind.PLANT, name=plant_name, lat=plant[0], lng=plant[1], eta=eta)
    route.distance_km = round(distance, 2)
    route.duration_min = round(trip_minutes(plant, ordered))
    route.path = {"type": "LineString", "coordinates": [[lng, lat] for lat, lng in points]}
    route.save(update_fields=["distance_km", "duration_min", "path", "updated_at"])
    return route


def route_orders(route: Route) -> list[Order]:
    return [s.order for s in route.stops.filter(order__isnull=False).select_related("order__customer").order_by("position")]


def reoptimize(route: Route, orders: list[Order]) -> Route:
    """Re-plans a planned route with these orders; without orders it is `replaced`."""
    if route.status != Route.Status.PLANNED:
        raise DispatchError(f"La ruta {route.id} ya no está planificada.")
    if not orders:
        route.status = Route.Status.REPLACED
        route.save(update_fields=["status", "updated_at"])
        return route
    plant, plant_name = plant_point()
    orders = list(with_dispatch_fields(Order.objects.filter(id__in=[o.id for o in orders])).select_related("customer"))
    return write_stops(route, plant, plant_name, order_stops(plant, [stop_for(o) for o in orders]))


def vehicle_route_of(order: Order, statuses=LIVE) -> Route | None:
    """The vehicle route that carries the order (the latest one)."""
    return Route.objects.filter(vehicle__isnull=False, status__in=statuses, stops__order=order).order_by("-id").first()


def move_dispatch(order: Order, *, scheduled_on=None, vehicle=None, actor) -> Order:
    """`PATCH dispatches/<id>/`: reschedule a ready order to another day and/or move it to
    another vehicle. The planned routes involved are re-optimised; the order may exceed the
    target's capacity (the route's summary shows it)."""
    from core.permissions import require_role

    require_role(actor, "manager", "production")
    if order.status != Order.Status.READY:
        raise DispatchError(f"La orden {order.code} no está lista para despacho.")
    current = vehicle_route_of(order)
    if current is not None and current.status == Route.Status.IN_PROGRESS:
        raise DispatchError(f"La orden {order.code} ya salió en {current.vehicle.name}.")
    with transaction.atomic():
        if scheduled_on is not None:
            order.scheduled_delivery_on = scheduled_on
            order.save(update_fields=["scheduled_delivery_on", "updated_at"])
        day = delivery_date(order)
        target = None
        if vehicle is not None:
            target = Route.objects.filter(vehicle=vehicle, date=day, status__in=LIVE).order_by("-id").first()
            if target is not None and target.status == Route.Status.IN_PROGRESS:
                raise DispatchError(f"{vehicle.name} ya salió; su ruta no se puede cambiar.")
        stays = current is not None and current.date == day and (vehicle is None or (target is not None and target.id == current.id))
        if current is not None and not stays:
            reoptimize(current, [o for o in route_orders(current) if o.id != order.id])
        if vehicle is not None and not stays:
            if target is None:
                target = Route.objects.create(date=day, status=Route.Status.PLANNED, vehicle=vehicle)
            reoptimize(target, [o for o in route_orders(target) if o.id != order.id] + [order])
    return order


def start_route(route: Route, *, actor) -> Route:
    from core.permissions import require_role

    require_role(actor, "manager", "production")
    if route.vehicle_id is None:
        raise DispatchError("Solo se inicia la ruta de un vehículo.")
    if route.status == Route.Status.IN_PROGRESS:
        return route
    if route.status != Route.Status.PLANNED:
        raise DispatchError(f"La ruta está {route.get_status_display().lower()}.")
    if Route.objects.filter(vehicle=route.vehicle, status=Route.Status.IN_PROGRESS).exists():
        raise DispatchError(f"{route.vehicle.name} ya tiene una ruta en curso.")
    now = clock.now()
    with transaction.atomic():
        if route.date == clock.today():  # The ETAs count from the real departure.
            retime(route, now)
        route.status, route.started_at = Route.Status.IN_PROGRESS, now
        route.save(update_fields=["status", "started_at", "updated_at"])
    return route


def retime(route: Route, start: datetime) -> None:
    """Arrival ETAs again from `start`, same stops in the same order (their ids stay)."""
    stops = list(route.stops.order_by("position"))
    eta = start
    for previous, stop in zip([None] + stops[:-1], stops):
        if previous is not None:
            eta += timedelta(minutes=haversine_km((previous.lat, previous.lng), (stop.lat, stop.lng)) / SPEED_KMH * 60)
            if previous.kind == RouteStop.Kind.DELIVERY:
                eta += timedelta(minutes=STOP_MINUTES)
        stop.eta = eta
        stop.save(update_fields=["eta", "updated_at"])


def complete_route(route: Route, *, actor) -> Route:
    from core.permissions import require_role

    require_role(actor, "manager", "production")
    if route.status == Route.Status.COMPLETED:
        return route
    if route.status != Route.Status.IN_PROGRESS:
        raise DispatchError("Solo se completa una ruta en curso.")
    route.status, route.completed_at = Route.Status.COMPLETED, clock.now()
    route.save(update_fields=["status", "completed_at", "updated_at"])
    return route


def deliver_stop(route: Route, stop: RouteStop, *, actor, at=None) -> RouteStop:
    """The stop is delivered: its order goes `ready → delivered`. A planned route starts on its
    first delivery. Idempotent."""
    from core.permissions import require_role

    from .services import set_status

    require_role(actor, "manager", "production")
    if stop.route_id != route.id or stop.kind != RouteStop.Kind.DELIVERY:
        raise DispatchError("La parada no es una entrega de esta ruta.")
    if stop.delivered_at:
        return stop
    if route.status == Route.Status.PLANNED:
        start_route(route, actor=actor)
        route.refresh_from_db()
        stop.refresh_from_db()
    if route.status != Route.Status.IN_PROGRESS:
        raise DispatchError(f"La ruta está {route.get_status_display().lower()}.")
    when = at or clock.now()
    with transaction.atomic():
        stop.delivered_at = when
        stop.save(update_fields=["delivered_at", "updated_at"])
        if stop.order_id and stop.order.status == Order.Status.READY:
            set_status(stop.order, Order.Status.DELIVERED, actor=actor, note=f"Entregada por {route.vehicle.name}" if route.vehicle_id else "", at=when)
    return stop
