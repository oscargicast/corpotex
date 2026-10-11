"""Purchase order lifecycle: approve, confirm (boss rules), progress, delivery, cancellation
with redistribution, payments and the public report page."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied

from manager.models import Alert, Decision
from messaging.models import Turn
from operations import services
from operations.exceptions import ManagerApprovalRequired
from operations.models import Payment, PurchaseOrder
from suppliers.models import Rate, Supplier
from tests.scenario import build


@pytest.fixture
def scenario(db, sales):
    data = build(owner=sales)
    other = Supplier.objects.create(name="Taller Castilla", kind="workshop", city="Piura", weekly_capacity=2000)
    Rate.objects.create(supplier=other, product=data["product"], unit_price=Decimal("7.00"), valid_from=date(2026, 1, 1))
    data["other"] = other
    return data


def suggested(scenario, code="PT-0002", quantity=500):
    po = PurchaseOrder.objects.create(
        code=code, supplier=scenario["supplier"], suggested_supplier=scenario["supplier"], status="suggested", internal_due_on=date(2026, 10, 14)
    )
    po.items.create(requirement=scenario["requirement"], quantity=quantity, unit_price=Decimal("6.50"))
    return po


@pytest.mark.django_db
def test_approve_sets_the_conversation_and_queues_the_first_contact(scenario, manager, sales):
    po = suggested(scenario)
    with pytest.raises(PermissionDenied):
        services.approve_purchase_orders([po], actor=sales)
    approved = services.approve_purchase_orders([po], actor=manager)
    po.refresh_from_db()
    assert approved == [po] and po.status == "approved"
    assert po.conversation == scenario["conversation"]
    assert Turn.objects.filter(conversation=po.conversation, reason="purchase_order_approved", status="pending").exists()
    scenario["order"].refresh_from_db()
    assert scenario["order"].status == "sourcing"


@pytest.mark.django_db
def test_approve_without_channel_opens_an_alert(scenario, manager):
    scenario["supplier"].numbers.update(active=False)
    po = suggested(scenario)
    services.approve_purchase_orders([po], actor=manager)
    assert Alert.objects.filter(kind="no_channel", purchase_order=po, status="open").exists()


@pytest.mark.django_db
def test_in_house_plant_needs_no_negotiation(scenario, manager):
    plant = Supplier.objects.create(name="Planta", kind="workshop", is_in_house=True)
    po = PurchaseOrder.objects.create(code="PT-0003", supplier=plant, suggested_supplier=plant, status="suggested", internal_due_on=date(2026, 10, 14))
    po.items.create(requirement=scenario["requirement"], quantity=100, unit_price=Decimal("3.20"))
    services.approve_purchase_orders([po], actor=manager)
    po.refresh_from_db()
    assert po.status == "confirmed" and po.committed_on == date(2026, 10, 14)
    assert po.payments.count() == 2


@pytest.mark.django_db
def test_confirm_applies_the_boss_rules_in_code(scenario):
    po = suggested(scenario)
    po.status = "negotiating"
    po.save()
    with pytest.raises(ManagerApprovalRequired):
        services.confirm_purchase_order(po, unit_price="7.00", committed_on=date(2026, 10, 13))
    with pytest.raises(ManagerApprovalRequired):
        services.confirm_purchase_order(po, unit_price="6.50", committed_on=date(2026, 10, 15))
    services.confirm_purchase_order(po, unit_price="6.00", committed_on=date(2026, 10, 13), terms="50% adelanto")
    po.refresh_from_db()
    assert po.status == "confirmed" and po.committed_on == date(2026, 10, 13) and po.terms == "50% adelanto"
    assert po.items.get().unit_price == Decimal("6.00")
    assert [(p.kind, p.amount) for p in po.payments.order_by("id")] == [("advance", Decimal("1500.00")), ("balance", Decimal("1500.00"))]
    assert po.last_follow_up_on is None and po.awaiting_reply_since is None  # follow-ups: the tick plans them (ADR 0027)
    # Idempotent for the same terms.
    services.confirm_purchase_order(po, unit_price="6.00", committed_on=date(2026, 10, 13))
    assert po.payments.count() == 2


@pytest.mark.django_db
def test_progress_delivery_and_rating(scenario, production, sales):
    po = scenario["purchase_order"]
    with pytest.raises(PermissionDenied):
        services.record_progress(po, units_done=500, actor=sales)
    report = services.record_progress(po, units_done=500, note="va bien", actor=production)
    assert report.source == "web"  # No WhatsApp message behind it.
    po.refresh_from_db()
    assert po.progress_reports.order_by("-reported_at").first() == report

    services.record_delivery(po, qty_received=600, actor=production)
    po.refresh_from_db()
    assert po.status == "in_progress" and po.items.get().qty_delivered == Decimal("600")
    services.record_delivery(po, qty_received=400, qty_defective=10, quality=4, actor=production)
    po.refresh_from_db()
    assert po.status == "delivered"
    assert po.rating["quality"] == 4.5 and po.rating["defect_pct"] == "1.00"  # 10 of 1000 received
    assert po.rating["delay_days"] == (date.today() - date(2026, 10, 14)).days or po.rating["delay_days"] <= 0
    scenario["order"].refresh_from_db()
    assert scenario["order"].status == "in_production"


@pytest.mark.django_db
def test_cancel_by_supplier_redistributes_the_remainder(scenario):
    po = scenario["purchase_order"]  # 1000 units, 400 reported
    po, created, decision = services.cancel_by_supplier(po, reason="se me enfermó la gente")
    assert po.status == "cancelled_by_supplier" and "Cancelado por el proveedor" in po.terms
    assert po.items.get().qty_delivered == Decimal("400")
    assert po.deliveries.count() == 1
    assert len(created) == 1
    new = created[0]
    assert new.supplier == scenario["other"] and new.redistributed_from == po
    assert new.items.get().quantity == Decimal("600")
    assert decision.kind == "approve_assignment"
    assert decision.detail["cancelled"] == {"code": "PT-0001", "supplier_name": "Confecciones del Norte", "quantity": "1000.00", "units_done": 400}
    assert decision.detail["before"]["estimated_on"] and decision.detail["after"]["estimated_on"]
    # Idempotent.
    assert services.cancel_by_supplier(po, reason="otra vez") == (po, [], None)
    assert PurchaseOrder.objects.count() == 2


@pytest.mark.django_db
def test_paying_the_advance_moves_the_purchase_order_to_in_progress(scenario, manager, sales):
    po = suggested(scenario)
    po.status = "confirmed"
    po.save()
    advance = Payment.objects.create(purchase_order=po, kind="advance", amount=Decimal("100"))
    with pytest.raises(PermissionDenied):
        services.mark_payment_paid(advance, method="yape", actor=sales)
    services.mark_payment_paid(advance, method="yape", actor=manager)
    advance.refresh_from_db()
    po.refresh_from_db()
    assert advance.paid_at and advance.method == "yape" and advance.status == "paid"
    assert po.status == "in_progress"


# --- API ------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_orders_api_is_idempotent_and_role_checked(scenario, sales_client, manager_client, production, settings):
    from rest_framework.authtoken.models import Token
    from rest_framework.test import APIClient

    payload = {
        "code": "CP-2026-0002",
        "customer": "Caja Piura",
        "brand": "UNICRACK",
        "promised_on": "2026-11-05",
        "items": [{"product": "POLO-ESC-01", "quantity": 200, "unit_price": "20.00"}],
    }
    first = sales_client.post("/api/orders/", payload, format="json")
    assert first.status_code == 201 and first.json()["status"] == "broken_down"
    assert "unit_price" not in str(first.json()["requirements"])
    second = sales_client.post("/api/orders/", payload, format="json")
    assert second.status_code == 200 and second.json()["id"] == first.json()["id"]

    production_client = APIClient()
    production_client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.get_or_create(user=production)[0].key}")
    assert production_client.post("/api/orders/", payload, format="json").status_code == 403
    assert sales_client.post(f"/api/orders/{first.json()['id']}/confirm/").status_code == 403
    confirmed = production_client.post(f"/api/orders/{first.json()['id']}/confirm/")
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "confirmed"
    assert manager_client.get("/api/purchase-orders/?waiting_manager=1").json()


@pytest.mark.django_db
def test_progress_and_pay_endpoints(scenario, manager_client, sales_client):
    po = scenario["purchase_order"]
    assert sales_client.post(f"/api/purchase-orders/{po.id}/progress/", {"units_done": 500}).status_code == 403
    response = manager_client.post(f"/api/purchase-orders/{po.id}/progress/", {"units_done": 500, "note": "ok"})
    assert response.status_code == 201 and response.json()["units_done"] == 500
    balance = po.payments.get(kind="balance")
    paid = manager_client.post(f"/api/payments/{balance.id}/pay/", {"method": "transfer"})
    assert paid.status_code == 200 and paid.json()["status"] == "paid"
    assert sales_client.get("/api/payments/").status_code == 403


@pytest.mark.django_db
def test_public_report_page_uses_the_token_as_the_secret(scenario, anonymous_client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    po = scenario["purchase_order"]
    assert anonymous_client.get("/api/report/00000000-0000-0000-0000-000000000000/").status_code == 404
    page = anonymous_client.get(f"/api/report/{po.report_token}/")
    assert page.status_code == 200
    body = page.json()
    assert body["code"] == "PT-0001" and body["units_done"] == 400 and body["quantity"] == "1000.00"
    assert "supplier" not in body and "unit_price" not in body
    posted = anonymous_client.post(f"/api/report/{po.report_token}/", {"units_done": 700, "note": "casi"})
    assert posted.status_code == 201 and posted.json()["units_done"] == 700
    assert po.progress_reports.filter(units_done=700, acknowledged_at__isnull=True).exists()
    assert Turn.objects.filter(conversation=po.conversation, reason="web_report").exists()
    url = services.report_url(po)
    assert url.endswith(f"/report/{po.report_token}") and url.startswith(settings.PUBLIC_BASE_URL)
