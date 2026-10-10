"""A tiny but complete scenario for API tests: one order, one workshop purchase order with
progress and payments, one supplier with a number, one pending decision and one open alert."""

from datetime import date
from decimal import Decimal

from django.utils import timezone

from core.models import Brand, Customer, Material, Product, ProductMaterial
from manager.models import Alert, Decision
from messaging.models import AllowedNumber, Conversation
from operations.models import Order, OrderItem, Payment, ProgressReport, PurchaseOrder, PurchaseOrderItem, Requirement
from suppliers.models import Rate, Supplier


def build(owner=None) -> dict:
    now = timezone.now()
    brand = Brand.objects.create(name="UNICRACK", description="Uniformes escolares")
    customer = Customer.objects.create(name="Caja Piura", kind="company", tax_id="20100000001")
    fabric = Material.objects.create(sku="TEL-ALG-20-1", name="Algodón 20/1", kind="fabric", unit="kg", stock=120)
    polo = Product.objects.create(code="POLO-ESC-01", name="Polo escolar")
    ProductMaterial.objects.create(product=polo, material=fabric, qty_per_unit=Decimal("0.25"))

    workshop = Supplier.objects.create(
        name="Confecciones del Norte", kind="workshop", city="Piura", weekly_capacity=800, notes="Trato de usted."
    )
    number = AllowedNumber.objects.create(phone="51906746241", supplier=workshop, active=True)
    AllowedNumber.objects.create(phone="sim-confecciones-norte", name="Simulador", supplier=workshop, active=True, simulated=True)
    Rate.objects.create(supplier=workshop, product=polo, unit_price=Decimal("6.50"), valid_from=date(2026, 1, 1))
    conversation = Conversation.objects.create(channel="whatsapp", allowed_number=number)

    order = Order.objects.create(
        code="CP-2026-0001",
        customer=customer,
        brand=brand,
        owner=owner,
        status="sourcing",
        issued_on=date(2026, 10, 4),
        promised_on=date(2026, 10, 19),
        estimated_on=date(2026, 10, 17),
        risk="in_danger",
        risk_reason="El taller se atrasó",
    )
    OrderItem.objects.create(order=order, product=polo, quantity=1000, sizes={"M": 1000}, unit_price=Decimal("18.00"))
    requirement = Requirement.objects.create(order=order, kind="workshop", product=polo, qty_needed=1000)

    po = PurchaseOrder.objects.create(
        code="PT-0001",
        supplier=workshop,
        conversation=conversation,
        status="in_progress",
        suggested_supplier=workshop,
        rationale="Mejor precio con capacidad libre",
        scores={"on_time": 0.9, "price": 0.85, "load": 0.7, "quality": 0.8},
        internal_due_on=date(2026, 10, 14),
        committed_on=date(2026, 10, 14),
        terms="50% adelanto",
        next_follow_up_at=now,
    )
    PurchaseOrderItem.objects.create(purchase_order=po, requirement=requirement, quantity=1000, unit_price=Decimal("6.50"))
    ProgressReport.objects.create(purchase_order=po, units_done=400, reported_at=now)
    Payment.objects.create(purchase_order=po, kind="advance", amount=Decimal("3250.00"), method="yape", paid_at=now)
    Payment.objects.create(purchase_order=po, kind="balance", amount=Decimal("3250.00"))

    decision = Decision.objects.create(kind="price", summary="Pide subir el precio a 7.00", detail={"proposed_price": "7.00"}, conversation=conversation)
    decision.purchase_orders.add(po)
    alert = Alert.objects.create(kind="order_in_danger", severity="critical", order=order, text="La orden llegaría tarde", detected_at=now)

    return {
        "brand": brand,
        "customer": customer,
        "product": polo,
        "supplier": workshop,
        "number": number,
        "conversation": conversation,
        "order": order,
        "requirement": requirement,
        "purchase_order": po,
        "decision": decision,
        "alert": alert,
    }
