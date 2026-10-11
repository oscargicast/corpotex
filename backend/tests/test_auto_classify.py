"""ADR 0028, M3 (Oscar, 11/10 03:20): an order that comes in with items without a product
classifies itself in the background, no human confirmation."""

from datetime import date
from unittest import mock

import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import Material, Product
from manager import services as manager_services
from manager.models import Alert, AlertNotification
from operations import classify, jev, tasks
from operations.models import Order
from tests.test_consolidated import catalogue  # noqa: F401


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.get_or_create(user=user)[0].key}")
    return client


@pytest.fixture
def to_classify(catalogue, sales):
    """What the sales system's API sends: a free-text line next to a catalogue product."""
    body = {"customer": "Caja Piura", "brand": "UNICRACK", "promised_on": "2026-11-30",
            "items": [{"product": "UNI-POL-01", "quantity": 100},
                      {"description": "Casaca cortavientos impermeable con forro polar", "quantity": 150}]}
    with mock.patch.object(tasks.auto_classify, "apply_async") as queue:
        response = client_for(sales).post("/api/orders/", body, format="json")
    assert response.status_code == 201, response.content
    return Order.objects.get(pk=response.json()["id"]), queue


NEW_JACKET = {
    "product": {"existing_code": None, "code": "UNI-CAS-01", "name": "Casaca cortavientos", "brand": "UNICRACK"},
    "materials": [
        {"existing_sku": "TEL-20", "sku": "TEL-20", "name": "Jersey 20/1", "kind": "fabric", "unit": "kg", "qty_per_unit": 0.2},
        {"existing_sku": None, "sku": "TEL-IMP-01", "name": "Tela cortavientos impermeable", "kind": "fabric", "unit": "m", "qty_per_unit": 1.6},
    ],
    "confidence": 0.8,
}


@pytest.mark.django_db(transaction=True)
def test_an_order_with_unclassified_items_queues_the_classifier_on_commit(catalogue, sales):
    body = {"customer": "Caja Piura", "brand": "UNICRACK", "promised_on": "2026-11-30",
            "items": [{"description": "Casaca cortavientos impermeable", "quantity": 150}]}
    with mock.patch.object(tasks.auto_classify, "apply_async") as queue:
        order_id = client_for(sales).post("/api/orders/", body, format="json").json()["id"]
        queue.assert_called_once_with((order_id, 1), queue="periodic")
        client_for(sales).post("/api/orders/", {**body, "items": [{"product": "UNI-POL-01", "quantity": 10}]}, format="json")
        assert queue.call_count == 1  # an order with every product classified queues nothing


@pytest.mark.django_db
def test_the_classifier_applies_the_proposal_and_breaks_down(to_classify):
    order, _ = to_classify
    assert order.needs_classification is True
    with mock.patch.object(jev, "choose", return_value=None), mock.patch.object(jev, "choose_many", return_value=None), mock.patch.object(
        classify, "complete_sync", return_value=NEW_JACKET
    ):
        assert tasks.auto_classify(order.id) == {"done": 1, "failed": 0}
    order.refresh_from_db()
    assert order.needs_classification is False and order.status == "broken_down"
    jacket = order.items.get(description__startswith="Casaca").product
    assert jacket.code == "UNI-CAS-01" and Material.objects.get(sku="TEL-IMP-01").stock == 0
    assert order.requirements.filter(kind="material", material__sku="TEL-IMP-01").get().qty_needed == 240
    assert order.requirements.filter(kind="workshop").count() == 2
    assert not Alert.objects.filter(kind="classification_failed").exists()


@pytest.mark.django_db
def test_a_catalogue_product_by_jev_without_claude(to_classify):
    order, _ = to_classify
    with mock.patch.object(jev, "choose", return_value=("UNI-POL-01", 0.93, {})), mock.patch.object(classify, "complete_sync") as complete:
        tasks.auto_classify(order.id)
    complete.assert_not_called()
    order.refresh_from_db()
    assert order.needs_classification is False and set(order.items.values_list("product__code", flat=True)) == {"UNI-POL-01"}
    assert Product.objects.count() == 1


@pytest.mark.django_db
def test_a_failure_retries_once_then_alerts_production(to_classify, manager, production):
    order, _ = to_classify
    with mock.patch.object(jev, "choose", return_value=None), mock.patch.object(classify, "complete_sync", side_effect=RuntimeError("model down")), mock.patch.object(
        tasks.auto_classify, "apply_async"
    ) as retry:
        assert tasks.auto_classify(order.id) == {"done": 0, "failed": 1}
        retry.assert_called_once_with((order.id, 2), countdown=60, queue="periodic")
        assert not Alert.objects.filter(kind="classification_failed").exists()
        tasks.auto_classify(order.id, 2)
        assert retry.call_count == 1  # no third try
    order.refresh_from_db()
    assert order.needs_classification is True
    alert = Alert.objects.get(kind="classification_failed", status="open")
    assert alert.order == order and alert.text == f"No se pudo reconocer 'Casaca cortavientos impermeable con forro polar' en {order.code}"
    assert {n.user.username for n in AlertNotification.objects.filter(alert=alert)} == {"gerente", "produccion"}
    # Classified later (by hand or a new try): the monitor resolves the alert.
    with mock.patch.object(jev, "choose", return_value=("UNI-POL-01", 0.93, {})):
        tasks.auto_classify(order.id, 2)
    manager_services.run_monitor()
    alert.refresh_from_db()
    assert alert.status == "resolved"
