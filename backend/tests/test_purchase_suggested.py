"""B6.2: the tick suggests purchases for materials whose open requirements cannot wait."""

from datetime import date, timedelta

import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core import clock
from manager import services as manager_services
from manager.models import Alert, AlertNotification
from messaging import services as messaging_services
from messaging.models import Turn
from operations import services
from operations.models import Order
from tests.test_consolidated import catalogue, order  # noqa: F401


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.get_or_create(user=user)[0].key}")
    return client


@pytest.fixture
def urgent(catalogue, sales, production):
    """Two confirmed orders sharing the buttons, the earliest due in 9 days: Gamarra needs 5 + buffer 5."""
    today = clock.today()
    a = order("CP-2026-0301", "Caja Piura", 400, today + timedelta(days=14), sales)
    b = order("CP-2026-0302", "AIDER", 500, today + timedelta(days=40), sales)
    services.confirm_order(a, actor=production)
    services.confirm_order(b, actor=production)
    return a, b


@pytest.mark.django_db
def test_tick_opens_purchase_suggested_once(urgent, catalogue, manager, production, sales):
    alerts = manager_services.suggest_purchases()
    assert [a.material.sku for a in alerts] == ["BOT-NX", "TEL-20"]  # both are due in 9 days for CP-2026-0301
    alert = alerts[0]
    assert alert.kind == "purchase_suggested" and alert.detail["total_to_order"] == "2600.00"
    assert {o["code"] for o in alert.detail["orders"]} == {"CP-2026-0301", "CP-2026-0302"} and alert.detail["suggested_supplier"]["name"] == "Avíos Gamarra"
    assert "Avíos Gamarra" in alert.text and "0.18" not in alert.text  # The text never carries prices.
    assert {n.user.username for n in alert.notifications.all()} == {"gerente", "produccion"}
    manager_services.run_monitor()
    manager_services.run_monitor()
    assert Alert.objects.filter(kind="purchase_suggested", status="open").count() == 2
    assert AlertNotification.objects.filter(alert=alert).count() == 2  # no duplicate notices
    # An order that can wait does not trigger it: AIDER alone (due in 40 days) would not.
    Order.objects.filter(code="CP-2026-0301").update(status="cancelled")
    manager_services.suggest_purchases()
    assert Alert.objects.filter(kind="purchase_suggested", status="open").count() == 0


@pytest.mark.django_db
def test_suggestion_resolves_when_the_purchase_order_is_generated(urgent, catalogue, production):
    manager_services.suggest_purchases()
    rows = client_for(production).get("/api/requirements/pending/").json()
    buttons = next(r for r in rows if r["material"]["sku"] == "BOT-NX")
    assert buttons["alert_id"] == Alert.objects.get(kind="purchase_suggested", status="open", material=catalogue["buttons"]).id
    services.generate_purchase_orders([catalogue["buttons"].id], actor=production)
    manager_services.suggest_purchases()
    assert Alert.objects.get(kind="purchase_suggested", material=catalogue["buttons"]).status == "resolved"
    assert Alert.objects.get(kind="purchase_suggested", material=catalogue["fabric"]).status == "open"


@pytest.mark.django_db
def test_alert_payloads_by_role(urgent, catalogue, manager, production, sales, manager_client, sales_client):
    manager_services.suggest_purchases()
    alert = Alert.objects.get(kind="purchase_suggested", status="open", material=catalogue["buttons"])
    production_client = client_for(production)
    mine = production_client.get("/api/alerts/?mine=1").json()
    row = next(a for a in mine if a["id"] == alert.id)
    assert row["material"] == {"id": catalogue["buttons"].id, "sku": "BOT-NX", "name": "Botón NX"}
    assert "reference_price" not in row["detail"]  # stripped for production
    assert "0.18" not in str(row)
    manager_row = next(a for a in manager_client.get("/api/alerts/?mine=1").json() if a["id"] == alert.id)
    assert manager_row["detail"]["reference_price"] == "0.18"
    assert alert.id not in {a["id"] for a in sales_client.get("/api/alerts/?mine=1").json()}

    # The assistant's turn state: flat keys, prices only for the manager.
    for user, with_prices in ((production, False), (manager, True)):
        conversation = messaging_services.dashboard_conversation(user)
        turn = Turn.objects.filter(conversation=conversation, status="pending").first()
        batch = messaging_services.TurnBatch(turn=turn, alert_ids=[alert.id])
        state = messaging_services.assistant_turn_state(batch)
        payload = state["alerts"][0]
        assert payload["kind"] == "purchase_suggested" and payload["material"]["sku"] == "BOT-NX" and payload["total_to_order"] == "2600.00"
        assert [set(o) for o in payload["orders"]] == [{"code", "qty", "due_on"}] * 2
        assert payload["suggested_supplier"]["name"] == "Avíos Gamarra"
        assert (payload["reference_price"], payload["currency"]) == (("0.18", "PEN") if with_prices else (None, None))
        assert "detail" not in payload and "text" not in payload


@pytest.mark.django_db
def test_generating_the_purchase_order_closes_the_suggestion_at_once(urgent, catalogue, production, manager):
    """Finding of 10/10 22:00: the thread's suggestion stayed open after PI-0010 and the
    assistant announced a purchase already made."""
    manager_services.suggest_purchases()
    alert = Alert.objects.get(kind="purchase_suggested", status="open", material=catalogue["buttons"])
    services.generate_purchase_orders([catalogue["buttons"].id], actor=production)
    alert.refresh_from_db()
    assert alert.status == "resolved"  # Closed inside generate, before any tick.
    # A requirement that stops being open for any other reason also closes it on the next tick.
    fabric_alert = Alert.objects.get(kind="purchase_suggested", status="open", material=catalogue["fabric"])
    from operations.models import Requirement

    Requirement.objects.filter(material=catalogue["fabric"]).update(status="ordered")
    manager_services.suggest_purchases()
    fabric_alert.refresh_from_db()
    assert fabric_alert.status == "resolved"
