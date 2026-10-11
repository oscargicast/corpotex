"""P6b: simulated numbers from the API (the "Para pruebas" checkbox) and the order list's
`awaiting_reply` for the "Avance pedido" chip."""

from datetime import timedelta

import pytest
from django.utils import timezone

from messaging.models import AllowedNumber
from operations.models import FollowUpRequest, PurchaseOrder
from suppliers.models import Supplier
from tests.scenario import build


@pytest.fixture
def scenario(db, sales):
    return build(owner=sales)


@pytest.mark.django_db
def test_a_simulated_number_takes_the_seeds_format_and_is_active(manager_client, sales_client, scenario):
    supplier = Supplier.objects.create(name="Taller Señor de Sipán E.I.R.L.", kind="workshop")
    assert sales_client.post(f"/api/suppliers/{supplier.id}/numbers/", {"simulated": True}, format="json").status_code == 403
    created = manager_client.post(f"/api/suppliers/{supplier.id}/numbers/", {"simulated": True}, format="json")
    assert created.status_code == 201, created.content
    assert created.json()["phone"] == "sim-taller-senor-de-sipan-e-i-r-l" and created.json()["active"] is True and created.json()["simulated"] is True
    # A second simulated number for the same supplier never collides; a typed phone keeps its slug.
    again = manager_client.post(f"/api/suppliers/{supplier.id}/numbers/", {"simulated": True}, format="json").json()
    assert again["phone"] == "sim-taller-senor-de-sipan-e-i-r-l-2"
    typed = manager_client.post(f"/api/suppliers/{supplier.id}/numbers/", {"phone": "Prueba Juan", "simulated": True}, format="json").json()
    assert typed["phone"] == "sim-prueba-juan"
    # Real numbers are as before: a phone is required and they start inactive.
    assert manager_client.post(f"/api/suppliers/{supplier.id}/numbers/", {"name": "Sin número"}, format="json").status_code == 400
    real = manager_client.post(f"/api/suppliers/{supplier.id}/numbers/", {"phone": "51944444444"}, format="json").json()
    assert real["active"] is False and real["simulated"] is False
    assert AllowedNumber.objects.filter(supplier=supplier).count() == 4


@pytest.mark.django_db
def test_the_order_list_says_when_a_purchase_order_awaits_the_suppliers_answer(sales_client, scenario):
    po = scenario["purchase_order"]  # in_progress, bound to CP-2026-0001

    def listed():
        [row] = [o for o in sales_client.get("/api/orders/").json() if o["code"] == "CP-2026-0001"]
        return row["awaiting_reply"]

    assert listed() is False
    PurchaseOrder.objects.filter(pk=po.pk).update(awaiting_reply_since=timezone.now() - timedelta(hours=1))  # a follow-up went
    assert listed() is True
    PurchaseOrder.objects.filter(pk=po.pk).update(awaiting_reply_since=None)
    request = FollowUpRequest.objects.create(purchase_order=po, requested_at=timezone.now(), status="asked", asked_at=timezone.now())
    assert listed() is True  # a person asked and the supplier has not answered
    request.status = "answered"
    request.save(update_fields=["status"])
    assert listed() is False
    PurchaseOrder.objects.filter(pk=po.pk).update(awaiting_reply_since=timezone.now(), status="delivered")
    assert listed() is False  # a closed purchase order waits for nothing
