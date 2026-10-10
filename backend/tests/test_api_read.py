import pytest

from tests.scenario import build

SENSITIVE = {"unit_price", "total_amount", "terms", "rationale", "scores", "candidates", "payments", "paid_amount", "pending_amount", "numbers", "notes"}


@pytest.fixture
def scenario(db, sales):
    return build(owner=sales)


def _flat_keys(payload, acc=None):
    acc = set() if acc is None else acc
    if isinstance(payload, dict):
        for key, value in payload.items():
            acc.add(key)
            _flat_keys(value, acc)
    elif isinstance(payload, list):
        for value in payload:
            _flat_keys(value, acc)
    return acc


@pytest.mark.django_db
def test_sales_purchase_order_has_no_prices_terms_or_numbers(sales_client, scenario):
    response = sales_client.get(f"/api/purchase-orders/{scenario['purchase_order'].id}/")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == "PT-0001"
    assert body["units_done"] == 400
    assert body["progress_pct"] == 40.0
    assert body["kind"] == "workshop"
    assert body["supplier"] == {"id": scenario["supplier"].id, "name": "Confecciones del Norte", "kind": "workshop"}
    assert body["waiting_manager"] is True
    assert not (_flat_keys(body) & SENSITIVE)


@pytest.mark.django_db
def test_manager_purchase_order_has_prices_and_payments(manager_client, scenario):
    body = manager_client.get(f"/api/purchase-orders/{scenario['purchase_order'].id}/").json()
    assert body["total_amount"] == "6500.00"
    assert body["currency"] == "PEN"
    assert body["paid_amount"] == "3250.00"
    assert body["pending_amount"] == "3250.00"
    assert body["payments"][0]["status"] == "paid"
    assert body["payments"][1]["status"] == "pending"
    assert body["pending_decision"]["summary"] == "Pide subir el precio a 7.00"
    assert body["status_display"] == "En proceso"


@pytest.mark.django_db
def test_manager_supplier_detail_has_numbers_and_sales_cannot_list(manager_client, sales_client, scenario):
    assert sales_client.get("/api/suppliers/").status_code == 403
    body = manager_client.get(f"/api/suppliers/{scenario['supplier'].id}/").json()
    assert {n["phone"] for n in body["numbers"]} == {"51906746241", "sim-confecciones-norte"}
    assert body["numbers_count"] == 2 and body["active_numbers_count"] == 2
    assert body["open_purchase_orders"] == 1
    assert body["load_pct"] == 125.0
    assert body["payments_summary"] == [
        {"currency": "PEN", "paid": "3250.00", "pending": "3250.00", "overdue_count": 0}
    ]
    assert body["rates"][0]["item_name"] == "Polo escolar"


@pytest.mark.django_db
def test_order_list_and_detail(sales_client, scenario):
    rows = sales_client.get("/api/orders/?risk=in_danger").json()
    assert [r["code"] for r in rows] == ["CP-2026-0001"]
    row = rows[0]
    assert row["slack_days"] == 2
    assert row["total_units"] == 1000
    assert row["purchase_orders_summary"] == {"total": 1, "confirmed": 1, "waiting_manager": 1}
    assert "total_amount" not in row

    detail = sales_client.get(f"/api/orders/{scenario['order'].id}/").json()
    assert detail["items"][0]["product"]["code"] == "POLO-ESC-01"
    assert "unit_price" not in detail["items"][0]
    req = detail["requirements"][0]
    assert req["qty_to_order"] == "1000.00" and req["status"] == "ordered"
    assert req["purchase_orders"][0]["code"] == "PT-0001"
    assert detail["alerts"][0]["kind"] == "order_in_danger"


@pytest.mark.django_db
def test_code_filter_is_exact(manager_client, scenario):
    assert len(manager_client.get("/api/orders/?code=CP-2026-0001").json()) == 1
    assert manager_client.get("/api/orders/?code=CP-2026").json() == []
    assert len(manager_client.get("/api/purchase-orders/?code=PT-0001").json()) == 1
    assert len(manager_client.get("/api/purchase-orders/?waiting_manager=1").json()) == 1


@pytest.mark.django_db
def test_monitor_shape_by_role(manager_client, sales_client, scenario):
    body = manager_client.get("/api/monitor/").json()
    assert set(body) == {"clock", "kpis", "alerts", "decisions", "redistributions", "orders_in_danger", "payments_by_supplier"}
    assert body["kpis"] == {
        "orders_in_danger": 1,
        "orders_at_risk": 0,
        "stalled_purchase_orders": 0,
        "pending_decisions": 1,
        "open_alerts": 1,
    }
    assert body["alerts"][0]["order"] == {"id": scenario["order"].id, "code": "CP-2026-0001"}
    assert body["decisions"][0]["purchase_orders"][0]["supplier_name"] == "Confecciones del Norte"
    assert body["decisions"][0]["orders"][0]["customer_name"] == "Caja Piura"
    assert body["payments_by_supplier"][0]["currency"] == "PEN"

    body = sales_client.get("/api/monitor/").json()
    assert body["kpis"]["pending_decisions"] is None
    assert body["decisions"] == []
    assert body["payments_by_supplier"] is None
    assert body["orders_in_danger"][0]["code"] == "CP-2026-0001"


@pytest.mark.django_db
def test_payments_list_is_manager_only(manager_client, sales_client, scenario):
    assert sales_client.get("/api/payments/").status_code == 403
    rows = manager_client.get("/api/payments/?status=pending").json()
    assert len(rows) == 1 and rows[0]["kind"] == "balance" and rows[0]["due_on"] == "2026-10-14"
