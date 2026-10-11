"""Fleet and per-vehicle delivery planning (ADR 0026 §1-§3, R1): capacity, overflow to
`unassigned`, reschedule and move re-optimise, delivering a stop closes the order, roles."""

from datetime import timedelta

import pytest

from core import clock
from core.models import Brand, Config, Customer, Product
from fleet.models import Vehicle
from operations import routes
from operations.models import Order, OrderItem, Route
from tests.conftest import _client_for

PLANT = (-5.172, -80.658)
POINTS = [(-5.1958, -80.6315), (-5.1981, -80.6189), (-5.1872, -80.6468), (-5.1846, -80.6705), (-5.2052, -80.6118), (-5.1688, -80.6402)]


@pytest.fixture
def fleet(db):
    config = Config.load()
    config.plant_name, config.plant_lat, config.plant_lng = "Planta Corpotex", *PLANT
    config.save()
    brand = Brand.objects.create(name="UNICRACK")
    product = Product.objects.create(code="UNI-POL-01", name="Polo escolar", brand=brand)
    customers = [Customer.objects.create(name=f"Cliente {i}", kind="school", lat=lat, lng=lng, address=f"Calle {i}") for i, (lat, lng) in enumerate(POINTS)]
    van = Vehicle.objects.create(name="Furgón 1", kind="van", capacity_units=1000, color="#0072B2")
    pickup = Vehicle.objects.create(name="Camioneta 2", kind="pickup", capacity_units=500, color="#E69F00")
    return {"brand": brand, "product": product, "customers": customers, "van": van, "pickup": pickup}


def ready(fleet, code, customer, units, *, day=None, promised=None, status="ready"):
    day = day or clock.today()
    order = Order.objects.create(
        code=code, customer=customer, brand=fleet["brand"], status=status, issued_on=day - timedelta(days=15), promised_on=promised or day, estimated_on=day
    )
    OrderItem.objects.create(order=order, product=fleet["product"], quantity=units)
    return order


def carried(route):
    return {s.order.code for s in route.stops.filter(order__isnull=False)}


@pytest.mark.django_db
def test_plan_day_shares_by_capacity_and_overflows_to_unassigned(fleet, production):
    c = fleet["customers"]
    late = ready(fleet, "CP-2026-0201", c[0], 400, day=clock.today() - timedelta(days=1))  # overdue: first in line
    ready(fleet, "CP-2026-0202", c[1], 600)
    ready(fleet, "CP-2026-0203", c[2], 300)
    ready(fleet, "CP-2026-0204", c[3], 150)
    low = ready(fleet, "CP-2026-0205", c[4], 300, promised=clock.today() + timedelta(days=4))  # lowest priority, no room left
    ready(fleet, "CP-2026-0206", c[5], 100, day=clock.today() + timedelta(days=1))  # another day

    plan = routes.plan_day(clock.today(), actor=production)

    assert len(plan.routes) == 2
    for route in plan.routes:
        units = sum(sum(i.quantity for i in s.order.items.all()) for s in route.stops.filter(order__isnull=False))
        assert units <= route.vehicle.capacity_units
        stops = list(route.stops.all())
        assert stops[0].kind == stops[-1].kind == "plant" and route.status == "planned"
        assert all(a.eta <= b.eta for a, b in zip(stops, stops[1:]))
    assert set().union(*(carried(r) for r in plan.routes)) == {"CP-2026-0201", "CP-2026-0202", "CP-2026-0203", "CP-2026-0204"}
    assert plan.unassigned == [{"order_id": low.id, "code": low.code, "reason": "capacity", "reason_display": "No cabe: capacidad"}]
    assert plan.suggested_next_day == [low.id]
    late.refresh_from_db()
    assert late.scheduled_delivery_on == clock.today()  # The overdue order now goes out today.


@pytest.mark.django_db
def test_too_big_or_without_coordinates_or_past_the_shift(fleet, production, monkeypatch):
    c = fleet["customers"]
    huge = ready(fleet, "CP-2026-0211", c[0], 1200)
    nowhere = Customer.objects.create(name="Cliente de Lima", kind="company")
    lost = ready(fleet, "CP-2026-0212", nowhere, 10)
    plan = routes.plan_day(clock.today(), actor=production)
    reasons = {row["code"]: row["reason"] for row in plan.unassigned}
    assert reasons == {huge.code: "capacity", lost.code: "no_coordinates"}
    assert plan.suggested_next_day == [huge.id]

    monkeypatch.setattr(routes, "SHIFT_END_HOUR", routes.START_HOUR)  # A shift with no time at all.
    small = ready(fleet, "CP-2026-0213", c[1], 10)
    plan = routes.plan_day(clock.today(), actor=production)
    assert {row["code"]: row["reason"] for row in plan.unassigned}[small.code] == "shift"


@pytest.mark.django_db
def test_replanning_replaces_planned_routes_and_leaves_the_road_alone(fleet, production):
    c = fleet["customers"]
    for i in range(3):
        ready(fleet, f"CP-2026-022{i}", c[i], 200)
    first = routes.plan_day(clock.today(), actor=production)
    on_road = first.routes[0]
    routes.start_route(on_road, actor=production)
    ready(fleet, "CP-2026-0229", c[4], 100)
    second = routes.plan_day(clock.today(), actor=production)
    on_road.refresh_from_db()
    assert on_road.status == "in_progress"
    assert all(r.vehicle_id != on_road.vehicle_id for r in second.routes)  # That vehicle is out.
    assert not set().union(*(carried(r) for r in second.routes)) & carried(on_road)
    for route in first.routes[1:]:
        route.refresh_from_db()
        assert route.status == "replaced"
    assert Route.objects.filter(status__in=routes.LIVE, vehicle__isnull=False).count() == 1 + len(second.routes)


@pytest.mark.django_db
def test_reschedule_and_move_reoptimise_the_routes(fleet, production):
    c = fleet["customers"]
    a = ready(fleet, "CP-2026-0231", c[0], 100)
    b = ready(fleet, "CP-2026-0232", c[1], 100)
    plan = routes.plan_day(clock.today(), vehicle_ids=[fleet["van"].id], actor=production)
    route = plan.routes[0]
    assert carried(route) == {a.code, b.code}

    tomorrow = clock.today() + timedelta(days=1)
    routes.move_dispatch(a, scheduled_on=tomorrow, actor=production)
    route.refresh_from_db()
    assert carried(route) == {b.code} and route.stops.count() == 3
    assert [o.code for o in routes.dispatch_pool(tomorrow)] == [a.code]

    routes.move_dispatch(b, vehicle=fleet["pickup"], actor=production)
    route.refresh_from_db()
    assert route.status == "replaced"  # Nothing left on the van.
    moved = Route.objects.get(vehicle=fleet["pickup"], status="planned")
    assert carried(moved) == {b.code} and moved.distance_km > 0

    routes.start_route(moved, actor=production)
    with pytest.raises(routes.DispatchError, match="ya salió"):
        routes.move_dispatch(b, scheduled_on=tomorrow, actor=production)


@pytest.mark.django_db
def test_delivering_a_stop_closes_the_order(fleet, production):
    order = ready(fleet, "CP-2026-0241", fleet["customers"][0], 100)
    route = routes.plan_day(clock.today(), actor=production).routes[0]
    stop = route.stops.get(order=order)
    routes.deliver_stop(route, stop, actor=production)  # A planned route starts on its first delivery.
    route.refresh_from_db()
    order.refresh_from_db()
    stop.refresh_from_db()
    assert route.status == "in_progress" and route.started_at and stop.delivered_at
    assert order.status == "delivered"
    change = order.status_changes.last()
    assert change.status == "delivered" and change.note == "Entregada por Furgón 1"
    routes.complete_route(route, actor=production)
    route.refresh_from_db()
    assert route.status == "completed" and route.completed_at


@pytest.mark.django_db
def test_api_roles_and_shapes(fleet, production, sales, manager_client):
    c = fleet["customers"]
    order = ready(fleet, "CP-2026-0251", c[0], 300)
    ready(fleet, "CP-2026-0252", c[1], 2000)  # Does not fit anywhere.
    production_client, sales_client = _client_for(production), _client_for(sales)
    today = clock.today().isoformat()

    assert sales_client.post("/api/routes/plan-day/", {"date": today}, format="json").status_code == 403
    body = production_client.post("/api/routes/plan-day/", {"date": today}, format="json").json()
    assert [r["vehicle"]["name"] for r in body["routes"]] == ["Furgón 1"]
    assert body["routes"][0]["summary"]["text"].startswith("1 entrega · 300 prendas (30 % de capacidad)")
    assert body["unassigned"][0]["code"] == "CP-2026-0252" and body["suggested_next_day"] == [body["unassigned"][0]["order_id"]]

    rows = sales_client.get("/api/dispatches/").json()
    row = next(r for r in rows if r["order"]["code"] == order.code)
    assert row["vehicle"]["name"] == "Furgón 1" and row["stop"]["position"] == 1 and row["on_time"] is True
    assert row["order"]["units"] == 300 and row["status"] == "ready" and row["scheduled_on"] == today
    assert [r["order"]["code"] for r in sales_client.get("/api/dispatches/?unassigned=1").json()] == ["CP-2026-0252"]
    assert [v["name"] for v in sales_client.get("/api/vehicles/").json()] == ["Furgón 1", "Camioneta 2"]

    tomorrow = (clock.today() + timedelta(days=1)).isoformat()
    assert sales_client.patch(f"/api/dispatches/{order.id}/", {"scheduled_on": tomorrow}, format="json").status_code == 403
    moved = production_client.patch(f"/api/dispatches/{order.id}/", {"vehicle_id": fleet["pickup"].id}, format="json").json()
    assert moved["vehicle"]["name"] == "Camioneta 2"

    route_id, stop_id = moved["route_id"], moved["stop"]["id"]
    assert sales_client.post(f"/api/routes/{route_id}/start/").status_code == 403
    started = production_client.post(f"/api/routes/{route_id}/start/").json()
    assert started["status"] == "in_progress" and started["vehicle"]["name"] == "Camioneta 2"
    assert production_client.patch(f"/api/dispatches/{order.id}/", {"scheduled_on": tomorrow}, format="json").status_code == 409
    delivered = manager_client.post(f"/api/routes/{route_id}/stops/{stop_id}/deliver/").json()
    assert next(s for s in delivered["stops"] if s["id"] == stop_id)["delivered_at"]
    assert delivered["summary"]["delivered"] == 1
    assert manager_client.post(f"/api/routes/{route_id}/complete/").json()["status"] == "completed"
    done = sales_client.get(f"/api/dispatches/?status=delivered&from={today}&to={today}").json()
    assert [r["order"]["code"] for r in done] == [order.code] and done[0]["delivered_at"]
    assert [r["vehicle"]["name"] for r in sales_client.get("/api/routes/?fleet=1&status=completed").json()] == ["Camioneta 2"]


@pytest.mark.django_db
def test_projected_routes_ignore_the_fleet(fleet, production):
    """The redistribution's routes have no vehicle (ADR 0024): `current_route` and `plan_route`
    never pick up or replace a vehicle's trip."""
    ready(fleet, "CP-2026-0261", fleet["customers"][0], 100)
    trip = routes.plan_day(clock.today(), actor=production).routes[0]
    assert routes.current_route(clock.today()) is None
    projected = routes.plan_route(clock.today())
    trip.refresh_from_db()
    assert projected.vehicle is None and trip.status == "planned"
    assert routes.current_route(clock.today()) == projected


@pytest.mark.django_db
def test_seed_brings_the_fleet_and_keeps_the_script_alerts():
    from django.core.management import call_command

    from fleet.models import VehiclePosition
    from manager.models import Alert
    from manager.services import run_monitor

    call_command("seed_demo", verbosity=0)
    run_monitor()
    opened = set()
    for alert in Alert.objects.filter(status="open").select_related("order", "purchase_order", "material"):
        ref = alert.material.sku if alert.material_id else alert.order.code if alert.order_id else alert.purchase_order.items.first().requirement.order.code
        opened.add((alert.kind, ref))
    assert opened == {
        ("payment_due", "CP-2026-0118"), ("order_in_danger", "CP-2026-0158"), ("order_in_danger", "CP-2026-0151"),
        ("purchase_suggested", "RIB-CUE-01"), ("purchase_suggested", "HIL-POL-40"),
    }
    assert list(Vehicle.objects.values_list("name", "capacity_units")) == [("Furgón 1", 1500), ("Camioneta 2", 800), ("Moto 3", 150)]
    assert Order.objects.filter(status="ready").count() >= 10
    yesterday = Route.objects.get(status="completed", vehicle__name="Furgón 1")
    assert yesterday.date == clock.today() - timedelta(days=1) and yesterday.started_at < yesterday.completed_at
    stops = yesterday.stops.filter(order__isnull=False)
    assert stops.count() == 3 and all(s.delivered_at and s.order.status == "delivered" for s in stops)
    assert VehiclePosition.objects.filter(route=yesterday).count() >= 5
    today = Route.objects.filter(date=clock.today(), status="planned", vehicle__isnull=False)
    assert today.count() >= 2
    script = ["CP-2026-0142", "CP-2026-0151", "CP-2026-0155", "CP-2026-0158", "CP-2026-0160", "CP-2026-0161"]
    assert not Route.objects.filter(vehicle__isnull=False, stops__order__code__in=script).exists()
