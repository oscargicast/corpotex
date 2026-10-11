"""Consolidated material purchase orders (ADR 0025 A): materials wait as open requirements
after confirmation; production generates one purchase order per material across orders."""

from datetime import date
from decimal import Decimal

import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import Brand, Customer, Material, Product, ProductMaterial
from manager.models import Decision
from operations import services
from operations.models import PurchaseOrder, Requirement
from suppliers.models import Rate, Supplier


@pytest.fixture
def catalogue(db):
    Customer.objects.create(name="Caja Piura", kind="company")
    Customer.objects.create(name="AIDER", kind="company")
    Brand.objects.create(name="UNICRACK")
    buttons = Material.objects.create(sku="BOT-NX", name="Botón NX", kind="button", unit="unit", stock=Decimal("100"))
    fabric = Material.objects.create(sku="TEL-20", name="Jersey 20/1", kind="fabric", unit="kg", stock=Decimal("0"))
    polo = Product.objects.create(code="UNI-POL-01", name="Polo")
    ProductMaterial.objects.create(product=polo, material=buttons, qty_per_unit=Decimal("3"))
    ProductMaterial.objects.create(product=polo, material=fabric, qty_per_unit=Decimal("0.25"))
    gamarra = Supplier.objects.create(name="Avíos Gamarra", kind="material", city="Lima", lead_time_days=5)
    Rate.objects.create(supplier=gamarra, material=buttons, unit_price=Decimal("0.18"), valid_from=date(2026, 1, 1))
    textil = Supplier.objects.create(name="Textiles Lima", kind="material", city="Lima", currency="USD", lead_time_days=7)
    Rate.objects.create(supplier=textil, material=fabric, unit_price=Decimal("8.00"), valid_from=date(2026, 1, 1))
    workshop = Supplier.objects.create(name="Taller Castilla", kind="workshop", city="Piura", weekly_capacity=5000)
    Rate.objects.create(supplier=workshop, product=polo, unit_price=Decimal("6.00"), valid_from=date(2026, 1, 1))
    return {"buttons": buttons, "fabric": fabric, "gamarra": gamarra, "textil": textil, "workshop": workshop}


def order(code, customer, quantity, promised, sales):
    payload = {"code": code, "customer": customer, "brand": "UNICRACK", "promised_on": promised, "items": [{"product": "UNI-POL-01", "quantity": quantity, "unit_price": "28.00"}]}
    return services.register_order(payload, actor=sales)[0]


@pytest.fixture
def two_orders(catalogue, sales, production):
    a = order("CP-2026-0301", "Caja Piura", 400, date(2026, 11, 10), sales)  # 1200 buttons, 100 from stock → 1100
    b = order("CP-2026-0302", "AIDER", 500, date(2026, 11, 2), sales)  # 1500 buttons (stock already taken by A)
    services.confirm_order(a, actor=production)
    services.confirm_order(b, actor=production)
    return a, b


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.get_or_create(user=user)[0].key}")
    return client


@pytest.mark.django_db
def test_confirming_leaves_materials_open_and_orders_only_the_workshop(two_orders, catalogue):
    a, b = two_orders
    assert not PurchaseOrder.objects.filter(supplier__kind="material").exists()
    assert PurchaseOrder.objects.filter(supplier__kind="workshop").count() == 2
    assert set(Requirement.objects.filter(kind="material").values_list("status", flat=True)) == {"open"}
    assert set(Requirement.objects.filter(kind="workshop").values_list("status", flat=True)) == {"ordered"}
    decision = Decision.objects.get(kind="approve_assignment", purchase_orders__items__requirement__order=a)
    assert {p["supplier"]["name"] for p in decision.detail["proposal"]} == {"Taller Castilla"}


@pytest.mark.django_db
def test_pending_purchases_groups_by_material_with_the_suggestion(two_orders, catalogue, manager_client, production, sales_client):
    production_client = client_for(production)
    assert sales_client.get("/api/requirements/pending/").status_code == 403
    body = production_client.get("/api/requirements/pending/").json()
    buttons = next(g for g in body if g["material"]["sku"] == "BOT-NX")
    assert buttons["total_to_order"] == "2600.00"
    assert [(o["code"], o["qty"], o["due_on"]) for o in buttons["orders"]] == [("CP-2026-0302", "1500.00", "2026-10-28"), ("CP-2026-0301", "1100.00", "2026-11-05")]
    assert buttons["due_on"] == "2026-10-28" and buttons["suggested_supplier"]["name"] == "Avíos Gamarra" and buttons["lead_time_days"] == 5
    assert buttons["reference_price"] is None  # Production never sees prices.
    manager_view = next(g for g in manager_client.get("/api/requirements/pending/").json() if g["material"]["sku"] == "BOT-NX")
    assert manager_view["reference_price"] == "0.18" and manager_view["currency"] == "PEN" and buttons["currency"] is None
    assert manager_view["candidates"] == [{"supplier": {"id": catalogue["gamarra"].id, "name": "Avíos Gamarra"}, "unit_price": "0.18", "currency": "PEN", "score": manager_view["candidates"][0]["score"]}]
    assert buttons["candidates"] == [] and buttons["alert_id"] is None and set(buttons["material"]) == {"id", "sku", "name", "kind", "unit", "image"}
    only = production_client.get(f"/api/requirements/pending/?material_ids={catalogue['fabric'].id}").json()
    assert [g["material"]["sku"] for g in only] == ["TEL-20"]
    assert {g["material"]["sku"] for g in body} == {"BOT-NX", "TEL-20"}


@pytest.mark.django_db
def test_generate_makes_one_purchase_order_per_material_across_orders(two_orders, catalogue, production, sales_client, manager_client):
    a, b = two_orders
    production_client = client_for(production)
    assert sales_client.post("/api/purchase-orders/generate/", {}, format="json").status_code == 403
    response = production_client.post("/api/purchase-orders/generate/", {"material_ids": [catalogue["buttons"].id]}, format="json")
    assert response.status_code == 201, response.content
    body = response.json()
    assert len(body["created"]) == 1 and body["skipped"] == []
    po = PurchaseOrder.objects.get(pk=body["created"][0]["id"])
    assert po.code.startswith("PI-") and po.supplier == catalogue["gamarra"] and po.status == "suggested"
    assert body["created"][0]["material"] == {"id": catalogue["buttons"].id, "sku": "BOT-NX", "name": "Botón NX"} and body["created"][0]["supplier"]["name"] == "Avíos Gamarra"
    assert [(i.requirement.order.code, i.quantity) for i in po.items.order_by("requirement__order__promised_on")] == [("CP-2026-0302", Decimal("1500.00")), ("CP-2026-0301", Decimal("1100.00"))]
    assert po.internal_due_on == date(2026, 10, 28)  # The earliest order's deadline.
    assert "unit_price" not in str(body)  # Production's payload carries no prices.
    assert {o["code"] for o in body["created"][0]["orders"]} == {"CP-2026-0301", "CP-2026-0302"}
    assert set(Requirement.objects.filter(material=catalogue["buttons"]).values_list("status", flat=True)) == {"ordered"}
    assert Requirement.objects.filter(material=catalogue["fabric"], status="open").count() == 2
    decision = Decision.objects.get(pk=body["decision_id"])
    assert decision.kind == "approve_assignment" and decision.status == "pending"
    assert decision.detail["proposal"][0]["quantity"] == "2600.00" and {o["code"] for o in decision.detail["proposal"][0]["orders"]} == {"CP-2026-0301", "CP-2026-0302"}
    assert decision.detail["proposal"][0]["candidates"][0]["supplier"]["name"] == "Avíos Gamarra"
    # The buttons are no longer pending; a second generate for them creates nothing.
    assert {g["material"]["sku"] for g in production_client.get("/api/requirements/pending/").json()} == {"TEL-20"}
    again = production_client.post("/api/purchase-orders/generate/", {"material_ids": [catalogue["buttons"].id]}, format="json").json()
    assert again["created"] == [] and again["skipped"] == [{"material_id": catalogue["buttons"].id, "reason": "sin requerimientos abiertos"}] and again["decision_id"] is None
    # Generate everything left: the fabric in USD.
    rest = manager_client.post("/api/purchase-orders/generate/", {}, format="json").json()
    assert len(rest["created"]) == 1 and rest["created"][0]["currency"] == "USD"
    assert production_client.get("/api/requirements/pending/").json() == []
    # Each order's detail lists the shared purchase order.
    detail = manager_client.get(f"/api/orders/{a.id}/").json()
    assert po.code in {p["code"] for r in detail["requirements"] for p in r["purchase_orders"]}


@pytest.mark.django_db
def test_rejecting_the_assignment_reopens_the_requirements(two_orders, catalogue, manager):
    from manager.services import resolve_decision

    result = services.generate_purchase_orders([catalogue["buttons"].id], actor=manager)
    created, decision = result["created"], result["decision"]
    resolve_decision(decision, action="reject", note="muy caro", actor=manager)
    assert set(Requirement.objects.filter(material=catalogue["buttons"]).values_list("status", flat=True)) == {"open"}
    assert PurchaseOrder.objects.get(pk=created[0].pk).status == "cancelled"


@pytest.mark.django_db
def test_sales_cannot_generate(two_orders, sales):
    from django.core.exceptions import PermissionDenied

    with pytest.raises(PermissionDenied):
        services.generate_purchase_orders(None, actor=sales)


@pytest.mark.django_db
def test_supplier_override_forces_the_supplier_or_answers_400(two_orders, catalogue, manager_client):
    other = Supplier.objects.create(name="Botones Lima", kind="material", city="Lima", lead_time_days=9)
    Rate.objects.create(supplier=other, material=catalogue["buttons"], unit_price=Decimal("0.25"), valid_from=date(2026, 1, 1))
    bad = manager_client.post("/api/purchase-orders/generate/", {"material_ids": [catalogue["buttons"].id], "supplier_overrides": {str(catalogue["buttons"].id): catalogue["textil"].id}}, format="json")
    assert bad.status_code == 400 and "no tiene tarifa" in bad.json()["detail"]
    assert not PurchaseOrder.objects.filter(supplier__kind="material").exists()
    response = manager_client.post("/api/purchase-orders/generate/", {"material_ids": [catalogue["buttons"].id], "supplier_overrides": {str(catalogue["buttons"].id): other.id}}, format="json")
    assert response.status_code == 201, response.content
    created = response.json()["created"][0]
    assert created["supplier"]["name"] == "Botones Lima" and created["items"][0]["unit_price"] == "0.25"
    assert created["suggested_supplier"]["name"] == "Botones Lima"  # The override is the suggestion of record; the ranking stays in the decision.


@pytest.mark.django_db
def test_a_delivered_partial_purchase_order_leaves_only_the_remainder_to_buy(two_orders, catalogue, production):
    """Finding of 10/10 22:10 (seed PI-0032): 600 of the 1000 collars were already delivered, yet
    "Por pedir" and the alert said 1000 while the generated purchase order said 400."""
    from operations.models import PurchaseOrderItem

    a, _ = two_orders
    requirement = a.requirements.get(kind="material", material=catalogue["buttons"])  # 1100 to order
    delivered = PurchaseOrder.objects.create(code="PI-0900", supplier=catalogue["gamarra"], status="delivered")
    PurchaseOrderItem.objects.create(purchase_order=delivered, requirement=requirement, quantity=Decimal("600"), unit_price=Decimal("0.18"), qty_delivered=Decimal("600"))
    assert services.sync_requirement_status(requirement).status == "open"  # partly covered: still to buy
    buttons = next(g for g in client_for(production).get("/api/requirements/pending/").json() if g["material"]["sku"] == "BOT-NX")
    assert buttons["total_to_order"] == "2000.00"
    assert {o["code"]: o["qty"] for o in buttons["orders"]} == {"CP-2026-0301": "500.00", "CP-2026-0302": "1500.00"}
    po = services.generate_purchase_orders([catalogue["buttons"].id], actor=production)["created"][0]
    assert {(i.requirement.order.code, str(i.quantity)) for i in po.items.select_related("requirement__order")} == {("CP-2026-0301", "500.00"), ("CP-2026-0302", "1500.00")}
    # Delivered in full, a requirement leaves "Por pedir" and is covered.
    other = Requirement.objects.get(order__code="CP-2026-0302", kind="material", material=catalogue["fabric"])
    full = PurchaseOrder.objects.create(code="PI-0901", supplier=catalogue["textil"], status="delivered")
    PurchaseOrderItem.objects.create(purchase_order=full, requirement=other, quantity=other.qty_to_order, unit_price=Decimal("8.00"), qty_delivered=other.qty_to_order)
    assert services.sync_requirement_status(other).status == "covered"
    fabric = next(g for g in client_for(production).get("/api/requirements/pending/").json() if g["material"]["sku"] == "TEL-20")
    assert [o["code"] for o in fabric["orders"]] == ["CP-2026-0301"]
