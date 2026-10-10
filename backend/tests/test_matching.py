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
    assert Customer.objects.filter(name="Caja Piura").exists() and Brand.objects.filter(name="UNICRACK").exists()
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
    assert decision.detail["proposal"][0]["candidates"][0]["supplier_name"] == "Taller Barato"


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
