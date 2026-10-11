"""Live positions (ADR 0026 §3-§5): one function records them whoever sends them (a device,
the simulator, a person), the SSE stream reads them, and the simulator advances a vehicle along
its route with short Celery ticks that re-queue themselves."""

import json
import time
from datetime import timedelta

from django.conf import settings
from django.db import close_old_connections, transaction

from core import clock
from operations.models import Route, RouteStop

from .models import Vehicle, VehiclePosition

STREAM_SECONDS = 600
PING_SECONDS = 15


def live_route(vehicle) -> Route | None:
    return Route.objects.filter(vehicle=vehicle, status=Route.Status.IN_PROGRESS).order_by("-id").first()


def next_stop(route: Route | None) -> dict | None:
    if route is None:
        return None
    stop = route.stops.filter(kind=RouteStop.Kind.DELIVERY, delivered_at__isnull=True).order_by("position").first()
    return {"id": stop.id, "position": stop.position, "name": stop.name, "eta": stop.eta.isoformat() if stop.eta else None} if stop else None


def record_position(vehicle: Vehicle, *, lat, lng, heading=None, speed_kmh=None, recorded_at=None, source="device") -> bool:
    """Always moves `Vehicle.last_*`; stores a `VehiclePosition` only when the last sample is
    older than `VEHICLE_SAMPLE_SECONDS`. Returns whether it stored one."""
    at = recorded_at or clock.now()
    with transaction.atomic():
        vehicle = Vehicle.objects.select_for_update().get(pk=vehicle.pk)
        vehicle.last_lat, vehicle.last_lng, vehicle.last_heading, vehicle.last_speed_kmh, vehicle.last_seen_at = lat, lng, heading, speed_kmh, at
        vehicle.save(update_fields=["last_lat", "last_lng", "last_heading", "last_speed_kmh", "last_seen_at", "updated_at"])
        last = vehicle.positions.order_by("-recorded_at").values_list("recorded_at", flat=True).first()
        if last is not None and (at - last).total_seconds() < settings.VEHICLE_SAMPLE_SECONDS:
            return False
        VehiclePosition.objects.create(vehicle=vehicle, route=live_route(vehicle), lat=lat, lng=lng, heading=heading, speed_kmh=speed_kmh, recorded_at=at, source=source)
    return True


def snapshot(vehicle: Vehicle) -> dict:
    route = live_route(vehicle)
    return {
        "vehicle_id": vehicle.id,
        "lat": vehicle.last_lat,
        "lng": vehicle.last_lng,
        "heading": vehicle.last_heading,
        "speed_kmh": vehicle.last_speed_kmh,
        "at": vehicle.last_seen_at.isoformat() if vehicle.last_seen_at else None,
        "route_id": route.id if route else None,
        "next_stop": next_stop(route),
        "simulating": vehicle.sim_active,
    }


def event(name: str, data, event_id: int) -> str:
    return f"id: {event_id}\nevent: {name}\ndata: {json.dumps(data, default=str)}\n\n"


def fleet(vehicle_ids) -> list[Vehicle]:
    qs = Vehicle.objects.filter(is_active=True)
    return list(qs.filter(id__in=vehicle_ids) if vehicle_ids else qs)


def delivered_stops(vehicle_ids, since):
    qs = RouteStop.objects.filter(delivered_at__isnull=False, delivered_at__gte=since, route__vehicle__isnull=False).select_related("order", "route")
    return qs.filter(route__vehicle_id__in=vehicle_ids) if vehicle_ids else qs


def stream(vehicle_ids, *, last_event_id: int = 0, seconds: int = STREAM_SECONDS, poll: float = 1.0, sleep=time.sleep, monotonic=time.monotonic, close=close_old_connections):
    """The SSE body (ADR 0026 §4): a `snapshot` on connect, a `position` whenever a vehicle's
    `last_seen_at` changes, a `stop` when a stop is delivered, a `: ping` every 15 s. Closes after
    `seconds`; the client reconnects with `Last-Event-ID`."""
    event_id = last_event_id
    connected = clock.now()
    vehicles = fleet(vehicle_ids)
    seen = {v.id: v.last_seen_at for v in vehicles}
    announced = set(delivered_stops(vehicle_ids, connected - timedelta(hours=12)).values_list("id", flat=True))
    event_id += 1
    yield "retry: 3000\n" + event("snapshot", [snapshot(v) for v in vehicles], event_id)
    started = last_ping = monotonic()
    while monotonic() - started < seconds:
        sleep(poll)
        close()
        for vehicle in fleet(vehicle_ids):
            if vehicle.last_seen_at != seen.get(vehicle.id):
                seen[vehicle.id] = vehicle.last_seen_at
                event_id += 1
                yield event("position", snapshot(vehicle), event_id)
        for stop in delivered_stops(vehicle_ids, connected - timedelta(hours=12)).exclude(id__in=announced):
            announced.add(stop.id)
            event_id += 1
            yield event("stop", {"route_id": stop.route_id, "stop_id": stop.id, "vehicle_id": stop.route.vehicle_id, "order_code": stop.order.code if stop.order_id else None, "delivered_at": stop.delivered_at}, event_id)
        if monotonic() - last_ping >= PING_SECONDS:
            last_ping = monotonic()
            yield ": ping\n\n"
