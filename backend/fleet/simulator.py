"""The vehicle simulator (ADR 0026 §5): each Celery tick moves the vehicle along the straight
legs of its route in progress, waits at each delivery and marks it delivered, and completes the
route back at the plant. Only routes that Produccion started; state lives in `Vehicle.sim_*`."""

from datetime import timedelta

from django.db import transaction

from core import clock
from operations import routes
from operations.models import Route, RouteStop

from .live import live_route, record_position
from .models import Vehicle
from .track import bearing


def geometry(route: Route) -> tuple[list[RouteStop], list[float]]:
    """The route's stops and the metres from the start to each one."""
    stops = list(route.stops.order_by("position"))
    covered = [0.0]
    for a, b in zip(stops, stops[1:]):
        covered.append(covered[-1] + routes.haversine_km((a.lat, a.lng), (b.lat, b.lng)) * 1000)
    return stops, covered


def point_at(stops, covered, metres: float) -> tuple[float, float, float | None]:
    for i in range(len(stops) - 1):
        if metres <= covered[i + 1] or i == len(stops) - 2:
            a, b = stops[i], stops[i + 1]
            span = covered[i + 1] - covered[i]
            f = 0.0 if span <= 0 else min(max((metres - covered[i]) / span, 0.0), 1.0)
            heading = bearing((a.lat, a.lng), (b.lat, b.lng)) if span > 0 else None
            return a.lat + (b.lat - a.lat) * f, a.lng + (b.lng - a.lng) * f, heading
    return stops[0].lat, stops[0].lng, None


def start(vehicle: Vehicle, *, speed_factor: float = 12, interval_s: int = 3, actor) -> Vehicle:
    from core.permissions import require_role

    from .tasks import simulate_tick

    require_role(actor, "manager", "production")
    route = live_route(vehicle)
    if route is None:
        raise routes.DispatchError(f"{vehicle.name} no tiene una ruta en curso: inicia la ruta primero.")
    stops, covered = geometry(route)
    done = [i for i, s in enumerate(stops) if s.delivered_at]
    run = vehicle.sim_run + 1
    if vehicle.sim_active:
        # Already running on this route (one route on the road per vehicle): a new speed
        # keeps where the vehicle is and any wait at a stop.
        progress, wait_until = vehicle.sim_progress_m, vehicle.sim_wait_until
    else:
        progress, wait_until = (covered[max(done)] if done else 0.0), None
    Vehicle.objects.filter(pk=vehicle.pk).update(
        sim_active=True, sim_progress_m=progress, sim_speed_factor=speed_factor, sim_interval_s=interval_s, sim_wait_until=wait_until, sim_run=run
    )
    transaction.on_commit(lambda: simulate_tick.apply_async((vehicle.pk, run), queue="periodic"))
    vehicle.refresh_from_db()
    return vehicle


def stop(vehicle: Vehicle, *, actor) -> Vehicle:
    from core.permissions import require_role

    require_role(actor, "manager", "production")
    Vehicle.objects.filter(pk=vehicle.pk).update(sim_active=False, sim_wait_until=None, sim_run=vehicle.sim_run + 1)
    vehicle.refresh_from_db()
    return vehicle


def step(vehicle: Vehicle, now=None) -> bool:
    """One tick. Returns whether the simulation goes on."""
    now = now or clock.now()
    route = live_route(vehicle)
    if route is None:
        Vehicle.objects.filter(pk=vehicle.pk).update(sim_active=False, sim_wait_until=None)
        return False
    stops, covered = geometry(route)
    progress, factor = vehicle.sim_progress_m, vehicle.sim_speed_factor
    pending = [i for i, s in enumerate(stops) if s.kind == RouteStop.Kind.DELIVERY and not s.delivered_at and covered[i] >= progress - 0.5]
    state = {"sim_progress_m": progress, "sim_wait_until": vehicle.sim_wait_until}
    going, speed = True, 0.0
    if vehicle.sim_wait_until is not None:
        if now >= vehicle.sim_wait_until and pending:
            routes.deliver_stop(route, stops[pending[0]], actor=None, at=now)
            state["sim_wait_until"] = None
        elif now >= vehicle.sim_wait_until:
            state["sim_wait_until"] = None
    else:
        target = progress + routes.SPEED_KMH / 3.6 * factor * vehicle.sim_interval_s
        if pending and target >= covered[pending[0]]:
            state["sim_progress_m"] = covered[pending[0]]
            state["sim_wait_until"] = now + timedelta(seconds=routes.STOP_MINUTES * 60 / factor)
        elif not pending and target >= covered[-1]:
            state["sim_progress_m"] = covered[-1]
            routes.complete_route(route, actor=None)
            state["sim_active"], going = False, False
        else:
            state["sim_progress_m"], speed = min(target, covered[-1]), float(routes.SPEED_KMH)
    lat, lng, heading = point_at(stops, covered, state["sim_progress_m"])
    Vehicle.objects.filter(pk=vehicle.pk, sim_run=vehicle.sim_run).update(**state)
    record_position(vehicle, lat=lat, lng=lng, heading=heading if heading is not None else vehicle.last_heading, speed_kmh=speed, recorded_at=now, source="simulator")
    return going
