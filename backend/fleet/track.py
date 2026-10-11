"""Where a vehicle is along its route at a given time: straight legs at `SPEED_KMH`, a stop of
`STOP_MINUTES` at each delivery (ADR 0026 §5). The seed draws yesterday's trail with it."""

import math
from datetime import datetime, timedelta

from operations.models import Route, RouteStop
from operations.routes import SPEED_KMH, STOP_MINUTES, haversine_km


def bearing(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlng = math.radians(b[1] - a[1])
    x = math.sin(dlng) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlng)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def timeline(route: Route, start: datetime) -> list[dict]:
    """Segments `{kind: move|stop, t0, t1, a, b, stop}` from `start` to the return to the plant."""
    stops = list(route.stops.order_by("position"))
    segments, t = [], start
    for previous, stop in zip(stops, stops[1:]):
        a, b = (previous.lat, previous.lng), (stop.lat, stop.lng)
        duration = timedelta(hours=haversine_km(a, b) / SPEED_KMH)
        segments.append({"kind": "move", "t0": t, "t1": t + duration, "a": a, "b": b, "stop": stop})
        t += duration
        if stop.kind == RouteStop.Kind.DELIVERY:
            segments.append({"kind": "stop", "t0": t, "t1": t + timedelta(minutes=STOP_MINUTES), "a": b, "b": b, "stop": stop})
            t += timedelta(minutes=STOP_MINUTES)
    return segments


def position_at(segments: list[dict], when: datetime) -> dict:
    for segment in segments:
        if when <= segment["t1"]:
            break
    span = (segment["t1"] - segment["t0"]).total_seconds()
    f = 0.0 if span <= 0 else min(max((when - segment["t0"]).total_seconds() / span, 0.0), 1.0)
    a, b = segment["a"], segment["b"]
    moving = segment["kind"] == "move" and a != b
    return {
        "lat": a[0] + (b[0] - a[0]) * f,
        "lng": a[1] + (b[1] - a[1]) * f,
        "heading": round(bearing(a, b), 1) if moving else None,
        "speed_kmh": float(SPEED_KMH) if moving and f < 1 else 0.0,
    }


def samples(route: Route, start: datetime, every_seconds: int = 300) -> list[dict]:
    """One position every `every_seconds` from `start` to the return, the last one included."""
    segments = timeline(route, start)
    if not segments:
        return []
    end = segments[-1]["t1"]
    points, t = [], start
    while t < end:
        points.append({**position_at(segments, t), "recorded_at": t})
        t += timedelta(seconds=every_seconds)
    points.append({**position_at(segments, end), "recorded_at": end, "speed_kmh": 0.0})
    return points
