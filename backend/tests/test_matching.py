"""Order breakdown, critical path and multicriteria matching with split."""

from datetime import date
from decimal import Decimal

import pytest

from core.models import Brand, Config, Customer, Material, Product, ProductMaterial
from manager.models import Decision
from operations import services
from operations.models import Order, PurchaseOrder, Requirement
from suppliers.models import Rate, Supplier


@pytest.fixture
def catalogue(db):
    Customer.objects.create(name="Caja Piura", kind="company")
    Brand.objects.create(name="UNICRACK")
    polo = Product.objects.create(code="UNI-POL-01", name="Polo escolar")
    fabric = Material.objects.create(sku="TEL-ALG-20", name="Jersey 20/1", kind="fabric", unit="kg", stock=Decimal("50"))
    ProductMaterial.objects.create(product=polo, material=fabric, qty_per_unit=Decimal("0.25"))
    fabric_supplier = Supplier.objects.create(name="Textiles Lima", kind="material", city="Lima", currency="USD")
    Rate.objects.create(supplier=fabric_supplier, material=fabric, unit_price=Decimal("8.00"), valid_from=date(2026, 1, 1))
    cheap = Supplier.objects.create(name="Taller Barato", kind="workshop", city="Piura", weekly_capacity=600)
    Rate.objects.create(supplier=cheap, product=polo, unit_price=Decimal("5.00"), valid_from=date(2026, 1, 1))
    big = Supplier.objects.create(name="Taller Grande", kind="workshop", city="Piura", weekly_capacity=5000)
    Rate.objects.create(supplier=big, product=polo, unit_price=Decimal("6.00"), valid_from=date(2026, 1, 1))
    Supplier.objects.create(name="Taller Inactivo", kind="workshop", status="inactive")
    return {"polo": polo, "fabric": fabric, "fabric_supplier": fabric_supplier, "cheap": cheap, "big": big}


def order_payload(code="CP-2026-0100", quantity=1000):
    return {
        "code": code,
        "customer": "Caja Piura",
        "brand": "UNICRACK",
        "promised_on": date(2026, 10, 30),
        "items": [{"product": "UNI-POL-01", "quantity": quantity, "sizes": {"M": quantity}, "unit_price": "18.00"}],
    }


@pytest.mark.django_db
def test_register_order_breaks_down_against_stock(catalogue, sales):
    order, created = services.register_order(order_payload(), actor=sales)
    assert created and order.status == "broken_down"
    fabric = order.requirements.get(kind="material")
    assert fabric.qty_needed == Decimal("250.00") and fabric.qty_from_stock == Decimal("50")
    assert fabric.qty_to_order == Decimal("200.00")
    workshop = order.requirements.get(kind="workshop")
    assert workshop.product == catalogue["polo"] and workshop.qty_needed == 1000
    assert order.estimated_on is not None

    again, created = services.register_order(order_payload(), actor=sales)
    assert not created and again.id == order.id and Order.objects.count() == 1


@pytest.mark.django_db
def test_production_cannot_register_but_can_confirm(catalogue, sales, production):
    from django.core.exceptions import PermissionDenied

    with pytest.raises(PermissionDenied):
        services.register_order(order_payload(), actor=production)
    order, _ = services.register_order(order_payload(), actor=sales)
    with pytest.raises(PermissionDenied):
        services.confirm_order(order, actor=sales)
    order = services.confirm_order(order, actor=production)
    assert order.status == "confirmed"
    assert PurchaseOrder.objects.filter(status="suggested").count() >= 2
    decision = Decision.objects.get(kind="approve_assignment", status="pending")
    assert decision.purchase_orders.count() == PurchaseOrder.objects.count()
    assert {p["supplier"]["name"] for p in decision.detail["proposal"]} >= {"Textiles Lima"}
    assert decision.detail["after"]["estimated_on"]


@pytest.mark.django_db
def test_rank_candidates_scores_and_orders_by_weighted_total(catalogue, sales):
    order, _ = services.register_order(order_payload(), actor=sales)
    requirement = order.requirements.get(kind="workshop")
    ranked = services.rank_candidates(requirement)
    assert [c["supplier_name"] for c in ranked] == ["Taller Barato", "Taller Grande"]
    assert ranked[0]["scores"]["price"] == 1.0 and ranked[1]["scores"]["price"] == 0.83
    assert set(ranked[0]["scores"]) == {"price", "on_time", "quality", "load"}
    assert ranked[0]["score"] > ranked[1]["score"]
    assert "mejor precio" in ranked[0]["rationale"].lower()
    assert ranked[0]["free_capacity"] == "600"
    assert services.rank_candidates(requirement, exclude=catalogue["cheap"])[0]["supplier_name"] == "Taller Grande"


@pytest.mark.django_db
def test_large_workshop_requirement_is_split_by_free_capacity(catalogue, sales):
    order, _ = services.register_order(order_payload(quantity=1000), actor=sales)
    requirement = order.requirements.get(kind="workshop")
    created, decision = services.match_requirements([requirement])
    workshop_pos = [po for po in created if po.supplier.kind == "workshop"]
    assert [(po.supplier.name, po.items.get().quantity) for po in workshop_pos] == [("Taller Barato", Decimal("600")), ("Taller Grande", Decimal("400"))]
    assert {po.code[:3] for po in workshop_pos} == {"PT-"}
    assert all(po.internal_due_on == date(2026, 10, 30) - __import__("datetime").timedelta(days=Config.load().buffer_days) for po in created)
    assert len(decision.detail["proposal"]) == len(created)
    first = decision.detail["proposal"][0]["candidates"][0]
    assert first["supplier_name"] == "Taller Barato" and first["supplier"] == {"id": catalogue["cheap"].id, "name": "Taller Barato"}


@pytest.mark.django_db
def test_matching_is_idempotent_for_covered_requirements(catalogue, sales):
    order, _ = services.register_order(order_payload(), actor=sales)
    requirements = list(order.requirements.all())
    created, decision = services.match_requirements(requirements)
    again, decision_again = services.match_requirements(requirements)
    assert again == [] and decision_again is None
    assert PurchaseOrder.objects.count() == len(created)


@pytest.mark.django_db
def test_critical_path_flags_the_order_in_danger(catalogue, sales):
    order, _ = services.register_order(order_payload(), actor=sales)
    Order.objects.filter(pk=order.pk).update(promised_on=date(2026, 10, 11))
    order.refresh_from_db()
    services.compute_critical_path(order)
    assert order.risk == "in_danger"
    assert order.estimated_on > order.promised_on
    assert order.risk_reason


@pytest.mark.django_db
def test_decision_detail_carries_the_currency(catalogue, sales, production):
    order, _ = services.register_order(order_payload(), actor=sales)
    services.confirm_order(order, actor=production)
    decision = Decision.objects.get(kind="approve_assignment")
    assert decision.detail["after"]["currency"] in ("PEN", "USD")
    assert {p["currency"] for p in decision.detail["proposal"]} == {"PEN", "USD"}  # fabric in USD, workshops in PEN


@pytest.mark.django_db
def test_stock_reserved_by_an_open_order_is_not_available_to_the_next(catalogue, sales):
    """RIB-PUN-01 showed stock 900, reserved 1700 (P0 of 10/10): the breakdown must subtract
    what other open orders already took."""
    from core.models import Material

    Material.objects.filter(sku="TEL-ALG-20").update(stock=Decimal("200"))
    first, _ = services.register_order(order_payload("CP-2026-0101", quantity=800), actor=sales)  # needs 200 kg
    second, _ = services.register_order(order_payload("CP-2026-0102", quantity=400), actor=sales)  # needs 100 kg
    first_req = first.requirements.get(kind="material")
    second_req = second.requirements.get(kind="material")
    assert first_req.qty_from_stock == Decimal("200") and first_req.qty_to_order == Decimal("0")
    assert second_req.qty_from_stock == Decimal("0") and second_req.qty_to_order == Decimal("100")
    assert services.committed_stock(Material.objects.get(sku="TEL-ALG-20")) == Decimal("200")
    # A re-breakdown of the first order keeps its own reservation (its rows are rebuilt, not double counted).
    services.break_down_order(first)
    assert first.requirements.get(kind="material").qty_from_stock == Decimal("200")
    # Once the first order closes, the stock frees up for the next breakdown.
    Order.objects.filter(pk=first.pk).update(status="delivered")
    services.break_down_order(second)
    assert second.requirements.get(kind="material").qty_from_stock == Decimal("100")


@pytest.mark.django_db
def test_ready_orders_are_never_in_danger_and_unconfirmed_suppliers_need_their_lead_time(catalogue, sales, production):
    from datetime import timedelta

    from core import clock

    order, _ = services.register_order(order_payload(), actor=sales)
    Order.objects.filter(pk=order.pk).update(status="ready", promised_on=clock.today() - timedelta(days=2))
    order.refresh_from_db()
    services.compute_critical_path(order)
    assert order.risk == "ok" and order.estimated_on <= clock.today()

    # A suggested workshop found today cannot deliver before tomorrow + its lead time, whatever the deadline says.
    tight, _ = services.register_order(order_payload("CP-2026-0101"), actor=sales)
    Order.objects.filter(pk=tight.pk).update(promised_on=clock.today() + timedelta(days=6))
    tight.refresh_from_db()
    services.confirm_order(tight, actor=production)  # suggested POs, workshops with lead_time_days=7 by default
    tight.refresh_from_db()
    assert tight.risk == "in_danger" and tight.estimated_on >= clock.today() + timedelta(days=8)


@pytest.mark.django_db
def test_register_order_rejects_unknown_references_with_400(catalogue, sales_client, sales):
    base = {"code": "CP-2026-0300", "customer": "Caja Piura", "brand": "UNICRACK", "promised_on": "2026-11-10", "items": [{"product": "UNI-POL-01", "quantity": 10, "unit_price": "28.00"}]}
    assert sales_client.post("/api/orders/", {**base, "items": [{**base["items"][0], "product": "POLO-ESC-01"}]}, format="json").json() == {"detail": "El producto POLO-ESC-01 no existe"}
    assert sales_client.post("/api/orders/", {**base, "customer": "Cliente Fantasma"}, format="json").status_code == 400
    assert sales_client.post("/api/orders/", {**base, "brand": "ACME"}, format="json").json() == {"detail": "La marca ACME no existe"}
    assert not Order.objects.filter(code="CP-2026-0300").exists()  # Nothing half-written.
    assert sales_client.post("/api/orders/", {**base, "customer": "caja piura", "items": [{**base["items"][0], "product": "uni-pol-01"}]}, format="json").status_code == 201


@pytest.mark.django_db
def test_order_examples_match_the_seed(sales_client, manager):
    """`docs/api/examples/order-*.json` must register against the real seed (D1 step 3)."""
    import json
    from pathlib import Path

    from django.core.management import call_command

    from seed.loader import DATA_DIR

    if not (DATA_DIR / "suppliers.json").exists():
        pytest.skip("seed data not present")
    call_command("seed_demo", verbosity=0)
    for path in sorted(Path(__file__).resolve().parents[2].joinpath("docs", "api", "examples").glob("order-*.json")):
        response = sales_client.post("/api/orders/", json.loads(path.read_text()), format="json")
        assert response.status_code == 201, (path.name, response.content)
        assert response.json()["requirements"], path.name
