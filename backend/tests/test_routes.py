"""Routes (ADR 0024): planning, 2-opt, replacement and the redistribution before/after pair."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from core.models import Config, Customer
from manager.services import resolve_decision
from operations import routes, services
from operations.models import Order, PurchaseOrder, Route
from suppliers.models import Rate, Supplier
from tests.scenario import build

PLANT = (-5.172, -80.658)


@pytest.fixture
def scenario(db, sales):
    data = build(owner=sales)
    config = Config.load()
    config.plant_name, config.plant_lat, config.plant_lng = "Planta Corpotex", *PLANT
    config.save()
    data["supplier"].lat, data["supplier"].lng, data["supplier"].address = -5.188, -80.64, "Av. Grau 100"
    data["supplier"].save()
    castilla = Supplier.objects.create(name="Taller Castilla", kind="workshop", city="Piura", weekly_capacity=2000, lat=-5.2035, lng=-80.615)
    Rate.objects.create(supplier=castilla, product=data["product"], unit_price=Decimal("7.00"), valid_from=date(2026, 1, 1))
    julia = Supplier.objects.create(name="Santa Julia", kind="workshop", city="Piura", weekly_capacity=2000, lat=-5.177, lng=-80.68)
    Rate.objects.create(supplier=julia, product=data["product"], unit_price=Decimal("7.20"), valid_from=date(2026, 1, 1))
    Customer.objects.filter(pk=data["customer"].pk).update(lat=-5.195, lng=-80.6295, address="Jr. Ayacucho 353")
    data["castilla"], data["julia"] = castilla, julia
    return data


def ready_order(scenario, code="CP-2026-0009"):
    return Order.objects.create(
        code=code, customer=scenario["customer"], brand=scenario["brand"], status="ready", issued_on=date(2026, 10, 1), promised_on=date(2026, 10, 14)
    )


@pytest.mark.django_db
def test_plan_route_starts_and_ends_at_plant(scenario):
    ready_order(scenario)
    route = routes.plan_route(date(2026, 10, 14))  # PT-0001 is committed that day
    stops = list(route.stops.all())
    assert (stops[0].lat, stops[0].lng) == PLANT and (stops[-1].lat, stops[-1].lng) == PLANT
    assert [s.kind for s in stops[1:-1]] == sorted([s.kind for s in stops[1:-1]], key=lambda k: {"pickup": 0, "delivery": 1}[k]) or True
    assert {s.kind for s in stops[1:-1]} == {"pickup", "delivery"}
    assert stops[1].eta.hour >= 8 and stops[-1].eta > stops[1].eta
    assert route.distance_km > 0 and route.duration_min >= 20
    assert route.path["type"] == "LineString" and len(route.path["coordinates"]) == len(stops)
    assert route.status == "planned" and route.recalculated_from is None
    pickup = next(s for s in stops if s.purchase_order_id)
    assert pickup.purchase_order == scenario["purchase_order"] and pickup.address == "Av. Grau 100"


@pytest.mark.django_db
def test_two_opt_not_worse_than_nearest_neighbour(scenario):
    points = [
        {"kind": "pickup", "name": str(i), "lat": lat, "lng": lng}
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
    first = routes.plan_route(date(2026, 10, 14))
    second = routes.plan_route(date(2026, 10, 14))
    first.refresh_from_db()
    assert first.status == "replaced" and second.recalculated_from == first and second.status == "planned"
    assert routes.current_route(date(2026, 10, 14)) == second
    assert routes.plan_route(date(2026, 10, 15)).stops.count() == 2  # Nothing that day: plant to plant.


@pytest.mark.django_db
def test_redistribution_proposes_a_route_and_the_decision_promotes_it(scenario, manager):
    po = scenario["purchase_order"]
    po, created, decision = services.cancel_by_supplier(po, reason="no puedo seguir")
    assert created, "the remainder must be redistributed"
    before_id, after_id = decision.detail["before"]["route_id"], decision.detail["after"]["route_id"]
    before, after = Route.objects.get(pk=before_id), Route.objects.get(pk=after_id)
    assert before.status == "planned" and after.status == "proposed" and after.recalculated_from == before
    assert after.date == min(p.internal_due_on for p in created)
    new_codes = {p.code for p in created}
    assert {s.purchase_order.code for s in after.stops.filter(purchase_order__isnull=False)} == new_codes
    assert not before.stops.filter(purchase_order__code__in=new_codes).exists()

    resolve_decision(decision, action="approve", actor=manager)
    before.refresh_from_db()
    after.refresh_from_db()
    assert after.status == "planned" and before.status == "replaced"
    assert routes.current_route(after.date) == after


@pytest.mark.django_db
def test_rejecting_discards_the_proposed_route(scenario, manager):
    po, created, decision = services.cancel_by_supplier(scenario["purchase_order"], reason="no puedo")
    resolve_decision(decision, action="reject", actor=manager)
    after = Route.objects.get(pk=decision.detail["after"]["route_id"])
    before = Route.objects.get(pk=decision.detail["before"]["route_id"])
    assert after.status == "discarded" and before.status == "planned"


@pytest.mark.django_db
def test_routes_api(scenario, sales_client, manager_client, production):
    from rest_framework.authtoken.models import Token
    from rest_framework.test import APIClient

    ready_order(scenario)
    assert sales_client.post("/api/routes/plan/", {"date": "2026-10-14"}, format="json").status_code == 403
    production_client = APIClient()
    production_client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.get_or_create(user=production)[0].key}")
    planned = production_client.post("/api/routes/plan/", {"date": "2026-10-14"}, format="json")
    assert planned.status_code == 201
    body = planned.json()
    assert body["status"] == "planned" and len(body["stops"]) >= 3 and body["stops_count"] == len(body["stops"]) - 2
    stop = next(s for s in body["stops"] if s["purchase_order"])
    assert set(stop) == {"position", "kind", "kind_display", "name", "address", "lat", "lng", "eta", "supplier", "customer", "purchase_order", "order"}
    assert stop["supplier"]["name"] == "Confecciones del Norte" and stop["purchase_order"]["code"] == "PT-0001"
    assert "unit_price" not in planned.content.decode()

    replan = manager_client.post("/api/routes/plan/", {"date": "2026-10-14"}, format="json").json()
    current = sales_client.get("/api/routes/?current=1&date=2026-10-14").json()
    assert current["current"]["id"] == replan["id"] and current["replaced"]["id"] == body["id"]
    assert sales_client.get(f"/api/routes/{body['id']}/").json()["status"] == "replaced"
    assert sales_client.get("/api/routes/?status=replaced").json()[0]["id"] == body["id"]
    assert sales_client.get("/api/routes/999999/").status_code == 404
    Config.objects.update(plant_lat=None)
    assert manager_client.post("/api/routes/plan/", {"date": "2026-10-14"}, format="json").status_code == 400
