"""Delivery routes (ADR 0024, corrected 10/10 23:35): planning, 2-opt, replacement and the
redistribution before/after pair when the affected order's delivery day moves."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from core import clock
from core.models import Config, Customer
from manager.services import resolve_decision
from operations import routes, services
from operations.models import Order, Route
from suppliers.models import Rate, Supplier
from tests.scenario import build

PLANT = (-5.172, -80.658)


@pytest.fixture
def scenario(db, sales):
    data = build(owner=sales)
    config = Config.load()
    config.plant_name, config.plant_lat, config.plant_lng = "Planta Corpotex", *PLANT
    config.save()
    Customer.objects.filter(pk=data["customer"].pk).update(lat=-5.195, lng=-80.6295, address="Jr. Ayacucho 353")
    for name, lat, lng, capacity in (("Taller Castilla", -5.2035, -80.615, 2000), ("Santa Julia", -5.177, -80.68, 2000)):
        workshop = Supplier.objects.create(name=name, kind="workshop", city="Piura", weekly_capacity=capacity, lat=lat, lng=lng)
        Rate.objects.create(supplier=workshop, product=data["product"], unit_price=Decimal("7.00"), valid_from=date(2026, 1, 1))
    data["aider"] = Customer.objects.create(name="AIDER", kind="company", lat=-5.212, lng=-80.625, address="Av. Loreto 123")
    data["lima"] = Customer.objects.create(name="Cliente de Lima", kind="company")  # No coordinates: never a stop.
    return data


def order_for(scenario, customer, code, day, status="in_production"):
    return Order.objects.create(
        code=code, customer=customer, brand=scenario["brand"], status=status, issued_on=day - timedelta(days=10), promised_on=day, estimated_on=day
    )


@pytest.mark.django_db
def test_plan_route_delivers_from_the_plant_and_back(scenario):
    day = date(2026, 10, 17)
    order_for(scenario, scenario["aider"], "CP-2026-0101", day)
    order_for(scenario, scenario["lima"], "CP-2026-0102", day)  # no coordinates
    order_for(scenario, scenario["aider"], "CP-2026-0103", day + timedelta(days=1))  # another day
    Order.objects.filter(pk=scenario["order"].pk).update(estimated_on=day)  # Caja Piura goes out that day too
    route = routes.plan_route(day)
    stops = list(route.stops.all())
    assert (stops[0].lat, stops[0].lng) == PLANT and (stops[-1].lat, stops[-1].lng) == PLANT
    assert stops[0].kind == "plant" and stops[-1].kind == "plant"
    assert [s.kind for s in stops[1:-1]] == ["delivery", "delivery"]
    assert {s.order.code for s in stops[1:-1]} == {"CP-2026-0001", "CP-2026-0101"}
    assert all(s.customer_id and s.address for s in stops[1:-1])
    assert stops[1].eta.hour >= 8 and stops[-1].eta > stops[1].eta
    assert route.distance_km > 0 and route.duration_min >= 20
    assert route.path["type"] == "LineString" and len(route.path["coordinates"]) == len(stops)
    assert route.status == "planned" and route.recalculated_from is None
    assert not route.stops.filter(kind="pickup").exists()


@pytest.mark.django_db
def test_two_opt_not_worse_than_nearest_neighbour(scenario):
    points = [
        {"kind": "delivery", "name": str(i), "lat": lat, "lng": lng}
        for i, (lat, lng) in enumerate([(-5.19, -80.64), (-5.21, -80.61), (-5.16, -80.67), (-5.20, -80.63), (-5.18, -80.69), (-5.17, -80.62)])
    ]
    remaining, here, nn = list(points), PLANT, []
    while remaining:
        nearest = min(remaining, key=lambda s: routes.haversine_km(here, (s["lat"], s["lng"])))
        remaining.remove(nearest)
        nn.append(nearest)
        here = (nearest["lat"], nearest["lng"])
    optimised = routes.order_stops(PLANT, points)
    assert routes.tour_length(PLANT, optimised) <= routes.tour_length(PLANT, nn) + 1e-9
    assert sorted(s["name"] for s in optimised) == sorted(s["name"] for s in points)


@pytest.mark.django_db
def test_replan_marks_previous_replaced(scenario):
    day = scenario["order"].estimated_on
    first = routes.plan_route(day)
    second = routes.plan_route(day)
    first.refresh_from_db()
    assert first.status == "replaced" and second.recalculated_from == first and second.status == "planned"
    assert routes.current_route(day) == second
    assert routes.plan_route(day + timedelta(days=20)).stops.count() == 2  # Nothing that day: plant to plant.


@pytest.mark.django_db
def test_redistribution_moves_the_delivery_to_the_new_day(scenario, manager):
    order = scenario["order"]  # Caja Piura, estimated 2026-10-17, promised 2026-10-19
    old_day = order.estimated_on
    other = order_for(scenario, scenario["aider"], "CP-2026-0101", old_day)  # stays on the old day
    planned = routes.plan_route(old_day)
    assert {s.order.code for s in planned.stops.filter(kind="delivery")} == {order.code, other.code}

    po, created, decision = services.cancel_by_supplier(scenario["purchase_order"], reason="no puedo seguir")
    assert created
    order.refresh_from_db()
    new_day = order.estimated_on
    assert new_day > old_day, "the replacements need their lead time: the delivery moves"
    before = Route.objects.get(pk=decision.detail["before"]["route_id"])
    after = Route.objects.get(pk=decision.detail["after"]["route_id"])
    assert before == planned and before.status == "planned"
    assert after.status == "proposed" and after.date == new_day and after.recalculated_from == before
    assert after.stops.filter(order=order).exists() and not after.stops.filter(order=other).exists()
    assert decision.detail["after"]["estimated_on"] == new_day.isoformat()

    resolve_decision(decision, action="approve", actor=manager)
    before.refresh_from_db()
    after.refresh_from_db()
    assert after.status == "planned" and before.status == "replaced"
    assert routes.current_route() == after and routes.current_route(new_day) == after
    replanned = routes.current_route(old_day)  # The old day keeps AIDER, without Caja Piura.
    assert replanned is not None and replanned != before and replanned.recalculated_from == before
    assert {s.order.code for s in replanned.stops.filter(kind="delivery")} == {other.code}


@pytest.mark.django_db
def test_rejecting_discards_the_proposed_route(scenario, manager):
    po, created, decision = services.cancel_by_supplier(scenario["purchase_order"], reason="no puedo")
    resolve_decision(decision, action="reject", actor=manager)
    after = Route.objects.get(pk=decision.detail["after"]["route_id"])
    before = Route.objects.get(pk=decision.detail["before"]["route_id"])
    assert after.status == "discarded" and before.status == "planned"
    assert before.stops.filter(order=scenario["order"]).exists()  # Planned on the fly, as it was.


@pytest.mark.django_db
def test_routes_api(scenario, sales_client, manager_client, production):
    from rest_framework.authtoken.models import Token
    from rest_framework.test import APIClient

    day = scenario["order"].estimated_on
    assert sales_client.post("/api/routes/plan/", {"date": day.isoformat()}, format="json").status_code == 403
    production_client = APIClient()
    production_client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.get_or_create(user=production)[0].key}")
    planned = production_client.post("/api/routes/plan/", {"date": day.isoformat()}, format="json")
    assert planned.status_code == 201
    body = planned.json()
    assert body["status"] == "planned" and body["name"] == f"Entregas del {day:%d/%m}" and body["stops_count"] == len(body["stops"]) - 2
    stop = next(s for s in body["stops"] if s["order"])
    assert set(stop) == {
        "id", "position", "kind", "kind_display", "name", "address", "lat", "lng", "eta", "delivered_at",
        "supplier", "customer", "purchase_order", "order", "units", "on_time",
    }
    assert stop["kind"] == "delivery" and stop["customer"]["name"] == "Caja Piura" and stop["order"]["code"] == "CP-2026-0001"
    assert body["stops"][0]["kind"] == "plant" and "unit_price" not in planned.content.decode()

    replan = manager_client.post("/api/routes/plan/", {"date": day.isoformat()}, format="json").json()
    assert replan["name"].endswith("(recalculada)")
    current = sales_client.get(f"/api/routes/?current=1&date={day.isoformat()}").json()
    assert current["current"]["id"] == replan["id"] and current["replaced"]["id"] == body["id"]
    assert sales_client.get(f"/api/routes/{body['id']}/").json()["status"] == "replaced"
    assert sales_client.get("/api/routes/?status=replaced").json()[0]["id"] == body["id"]
    assert sales_client.get("/api/routes/999999/").status_code == 404
    Config.objects.update(plant_lat=None)
    assert manager_client.post("/api/routes/plan/", {"date": day.isoformat()}, format="json").status_code == 400
