"""Live positions, SSE and the simulator (ADR 0026 §3-§5, R2)."""

from datetime import timedelta
from itertools import count
from unittest import mock

import pytest

from core import clock
from fleet import live, simulator
from fleet.models import Vehicle
from fleet.tasks import simulate_tick
from operations import routes
from tests.conftest import _client_for
from tests.test_fleet import PLANT, fleet, ready  # noqa: F401 (fixture)


def on_the_road(fleet, production, *codes):  # noqa: F811
    for i, code in enumerate(codes):
        ready(fleet, code, fleet["customers"][i], 100)
    route = routes.plan_day(clock.today(), vehicle_ids=[fleet["van"].id], actor=production).routes[0]
    routes.start_route(route, actor=production)
    route.refresh_from_db()
    return route


@pytest.mark.django_db
def test_positions_move_the_vehicle_and_keep_one_sample_every_five_minutes(fleet, production, sales):  # noqa: F811
    van, client = fleet["van"], _client_for(production)
    t0 = clock.now().replace(microsecond=0)
    url = f"/api/vehicles/{van.id}/positions/"
    first = client.post(url, {"lat": -5.18, "lng": -80.64, "heading": 90, "speed_kmh": 25, "recorded_at": t0.isoformat()}, format="json")
    assert first.status_code == 202 and first.json() == {"stored": True}
    second = client.post(url, {"lat": -5.181, "lng": -80.641, "recorded_at": (t0 + timedelta(seconds=60)).isoformat()}, format="json")
    assert second.json() == {"stored": False}
    van.refresh_from_db()
    assert (van.last_lat, van.last_lng, van.last_seen_at) == (-5.181, -80.641, t0 + timedelta(seconds=60))
    assert client.post(url, {"lat": -5.19, "lng": -80.65, "recorded_at": (t0 + timedelta(seconds=301)).isoformat()}, format="json").json() == {"stored": True}
    assert _client_for(sales).post(url, {"lat": -5.19, "lng": -80.65}, format="json").status_code == 403

    trail = _client_for(sales).get(f"{url}?from={clock.today().isoformat()}").json()
    assert [p["lat"] for p in trail] == [-5.18, -5.19] and trail[0]["source"] == "device"
    live_rows = _client_for(sales).get(f"/api/vehicles/live/?ids={van.id}").json()
    assert live_rows == [
        {"vehicle_id": van.id, "lat": -5.19, "lng": -80.65, "heading": None, "speed_kmh": None, "at": live_rows[0]["at"], "route_id": None, "next_stop": None, "simulating": False}
    ]


@pytest.mark.django_db
def test_stream_sends_snapshot_position_stop_and_ping(fleet, production):  # noqa: F811
    route = on_the_road(fleet, production, "CP-2026-0301", "CP-2026-0302")
    van = fleet["van"]
    ticks = count(0, 20)  # Every loop is 20 "seconds" later: a ping is due each time.
    body = live.stream([van.id], sleep=lambda s: None, monotonic=lambda: next(ticks), close=lambda: None)

    first = next(body)
    assert first.startswith("retry: 3000\nid: 1\nevent: snapshot\n") and f'"vehicle_id": {van.id}' in first
    live.record_position(van, lat=-5.18, lng=-80.64, speed_kmh=25, source="simulator")
    position = next(body)
    assert "event: position" in position and f'"route_id": {route.id}' in position
    first_stop = route.stops.get(position=1)
    assert f'"name": "{first_stop.name}"' in position
    assert next(body) == ": ping\n\n"
    routes.deliver_stop(route, first_stop, actor=production)
    stop = next(body)
    assert "event: stop" in stop and first_stop.order.code in stop and f'"stop_id": {first_stop.id}' in stop


@pytest.mark.django_db
def test_stream_view_headers_and_auth(fleet, production, anonymous_client):  # noqa: F811
    response = _client_for(production).get(f"/api/vehicles/stream/?ids={fleet['van'].id}", HTTP_ACCEPT="text/event-stream")
    assert response.status_code == 200 and response["Content-Type"] == "text/event-stream"
    assert response["Cache-Control"] == "no-cache, no-transform" and response["X-Accel-Buffering"] == "no"
    assert b"event: snapshot" in next(iter(response.streaming_content))
    response.close()
    assert anonymous_client.get("/api/vehicles/stream/", HTTP_ACCEPT="text/event-stream").status_code == 401


@pytest.mark.django_db
def test_simulator_drives_the_route_to_the_end(fleet, production, django_capture_on_commit_callbacks):  # noqa: F811
    van, client = fleet["van"], _client_for(production)
    ready(fleet, "CP-2026-0311", fleet["customers"][0], 100)
    planned = routes.plan_day(clock.today(), vehicle_ids=[van.id], actor=production).routes[0]
    assert client.post(f"/api/vehicles/{van.id}/simulate/", {}, format="json").status_code == 409  # Not started yet.
    routes.start_route(planned, actor=production)

    with mock.patch.object(simulate_tick, "apply_async") as queued, django_capture_on_commit_callbacks(execute=True):
        body = client.post(f"/api/vehicles/{van.id}/simulate/", {"speed_factor": 60, "interval_s": 5}, format="json").json()
    assert body["sim_active"] is True
    van.refresh_from_db()
    queued.assert_called_once_with((van.id, van.sim_run), queue="periodic")

    now, going, steps = clock.now(), True, 0
    while going and steps < 500:
        van.refresh_from_db()
        going = simulator.step(van, now=now)
        now += timedelta(seconds=van.sim_interval_s)
        steps += 1
    planned.refresh_from_db()
    van.refresh_from_db()
    stop = planned.stops.get(position=1)
    assert planned.status == "completed" and stop.delivered_at and stop.order.status == "delivered"
    assert not van.sim_active and (round(van.last_lat, 4), round(van.last_lng, 4)) == PLANT and van.last_speed_kmh == 0
    assert van.positions.filter(source="simulator").exists()


@pytest.mark.django_db
def test_tick_requeues_itself_and_a_stopped_run_ends(fleet, production):  # noqa: F811
    on_the_road(fleet, production, "CP-2026-0321")
    van = fleet["van"]
    Vehicle.objects.filter(pk=van.pk).update(sim_active=True, sim_run=4, sim_interval_s=3)
    with mock.patch.object(simulate_tick, "apply_async") as queued:
        assert simulate_tick(van.id, 4) is True
        queued.assert_called_once_with((van.id, 4), countdown=3, queue="periodic")
        assert simulate_tick(van.id, 3) is False  # An older chain stops by itself.
        _client_for(production).delete(f"/api/vehicles/{van.id}/simulate/")
        assert simulate_tick(van.id, 4) is False
        assert queued.call_count == 1
    van.refresh_from_db()
    assert not van.sim_active and van.last_seen_at is not None
