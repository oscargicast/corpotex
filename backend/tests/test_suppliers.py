"""Supplier registration, self-registration, approval, numbers and CSV import (B4.5, ADR 0016/0024)."""
from decimal import Decimal

from io import BytesIO

import pytest

from messaging.models import AllowedNumber, Conversation
from suppliers.models import Supplier
from tests.scenario import build


@pytest.fixture
def scenario(db, sales):
    return build(owner=sales)


PAYLOAD = {
    "name": "Taller Castilla",
    "kind": "workshop",
    "specialties": ["polos", "buzos"],
    "city": "Piura",
    "weekly_capacity": 900,
    "lead_time_days": 6,
    "phone": "51911111111",
    "contact_name": "Rosa",
}


@pytest.mark.django_db
def test_manager_registers_a_supplier_with_an_inactive_number(manager_client, sales_client):
    assert sales_client.post("/api/suppliers/", PAYLOAD, format="json").status_code == 403
    response = manager_client.post("/api/suppliers/", PAYLOAD, format="json")
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "active" and body["source"] == "registered" and body["follow_up_every_hours"] == 48
    assert body["numbers"] == [{"id": body["numbers"][0]["id"], "phone": "51911111111", "name": "Rosa", "active": False, "simulated": False}]
    assert body["numbers_count"] == 1 and body["active_numbers_count"] == 0
    duplicate = manager_client.post("/api/suppliers/", {**PAYLOAD, "name": "Otro"}, format="json")
    assert duplicate.status_code == 400 and "phone" in duplicate.json()


@pytest.mark.django_db
def test_self_register_is_public_and_lands_in_pending_review(anonymous_client, manager_client, sales_client):
    response = anonymous_client.post("/api/suppliers/self-register/", {**PAYLOAD, "name": "Confecciones Sechura"}, format="json")
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending_review" and body["source"] == "self_registered"
    assert set(body) == {"id", "name", "status", "source"}  # The public answer never echoes internals.
    pending = manager_client.get("/api/suppliers/?status=pending_review").json()
    assert [s["name"] for s in pending] == ["Confecciones Sechura"]
    assert sales_client.get("/api/suppliers/?status=pending_review").status_code == 403
    assert anonymous_client.post("/api/suppliers/self-register/", {"name": "x"}, format="json").status_code == 400


@pytest.mark.django_db
def test_manager_approves_or_discards_and_edits_the_card(manager_client, sales_client):
    supplier = Supplier.objects.create(name="Nuevo", kind="material", source="external", status="pending_review", source_detail={"url": "https://x"})
    assert sales_client.patch(f"/api/suppliers/{supplier.id}/", {"status": "active"}, format="json").status_code == 403
    approved = manager_client.patch(f"/api/suppliers/{supplier.id}/", {"status": "active", "city": "Lima", "specialties": ["hilo"]}, format="json")
    assert approved.status_code == 200
    assert approved.json()["status"] == "active" and approved.json()["city"] == "Lima" and approved.json()["specialties"] == ["hilo"]
    assert manager_client.patch(f"/api/suppliers/{supplier.id}/", {"status": "bogus"}, format="json").status_code == 400
    discarded = manager_client.patch(f"/api/suppliers/{supplier.id}/", {"status": "inactive"}, format="json").json()
    assert discarded["status"] == "inactive" and discarded["source_detail"] == {"url": "https://x"}


@pytest.mark.django_db
def test_numbers_are_added_inactive_activated_and_never_deleted(manager_client, scenario):
    supplier = scenario["supplier"]
    created = manager_client.post(f"/api/suppliers/{supplier.id}/numbers/", {"phone": "51922222222", "name": "Encargado"}, format="json")
    assert created.status_code == 201 and created.json()["active"] is False
    number_id = created.json()["id"]
    assert manager_client.post(f"/api/suppliers/{supplier.id}/numbers/", {"phone": "51922222222"}, format="json").status_code == 400
    activated = manager_client.patch(f"/api/suppliers/{supplier.id}/numbers/{number_id}/", {"active": True, "name": "Jefe"}, format="json")
    assert activated.status_code == 200 and activated.json()["active"] is True and activated.json()["name"] == "Jefe"
    renumbered = manager_client.patch(f"/api/suppliers/{supplier.id}/numbers/{number_id}/", {"phone": "51933333333"}, format="json")
    assert renumbered.status_code == 200 and renumbered.json()["phone"] == "51933333333"
    other = Supplier.objects.create(name="Otro", kind="workshop")
    assert manager_client.patch(f"/api/suppliers/{other.id}/numbers/{number_id}/", {"active": False}, format="json").status_code == 404
    assert manager_client.delete(f"/api/suppliers/{supplier.id}/numbers/{number_id}/").status_code == 405


@pytest.mark.django_db
def test_patch_phone_refused_when_conversation_exists(manager_client, scenario):
    number = scenario["number"]  # has a WhatsApp conversation
    response = manager_client.patch(f"/api/suppliers/{scenario['supplier'].id}/numbers/{number.id}/", {"phone": "51944444444"}, format="json")
    assert response.status_code == 400 and "conversación" in response.json()["phone"]
    number.refresh_from_db()
    assert number.phone == "51906746241"
    # Deactivating is always allowed.
    assert manager_client.patch(f"/api/suppliers/{scenario['supplier'].id}/numbers/{number.id}/", {"active": False}, format="json").json()["active"] is False


@pytest.mark.django_db
def test_import_matches_existing_by_phone_then_name(manager_client, scenario):
    csv_text = (
        "name,kind,specialties,city,weekly_capacity,lead_time_days,currency,phone,lat,lng\n"
        "Confecciones del Norte renombrada,workshop,polos;camisas,Piura,1200,5,PEN,51906746241,-5.19,-80.63\n"
        "Taller Castilla,workshop,polos,Piura,900,6,PEN,51955555555,,\n"
        "taller castilla,workshop,buzos,Piura,,7,PEN,,,\n"
        ",material,,Lima,,,PEN,,,\n"
        "Botones SA,bogus,,Lima,,,PEN,,,\n"
    )
    upload = BytesIO(csv_text.encode("utf-8"))
    upload.name = "suppliers.csv"
    response = manager_client.post("/api/suppliers/import/", {"file": upload}, format="multipart")
    assert response.status_code == 200
    body = response.json()
    assert [u["name"] for u in body["updated"]] == ["Confecciones del Norte renombrada", "Taller Castilla"]
    assert [c["name"] for c in body["created"]] == ["Taller Castilla"]
    assert [e["row"] for e in body["errors"]] == [5, 6]
    original = scenario["supplier"]
    original.refresh_from_db()
    assert original.name == "Confecciones del Norte renombrada" and original.weekly_capacity == 1200 and original.lat == -5.19
    castilla = Supplier.objects.get(name="Taller Castilla")
    assert castilla.specialties == ["buzos"] and castilla.weekly_capacity == 900  # Blank cells keep the value.
    assert AllowedNumber.objects.get(phone="51955555555").supplier == castilla and not AllowedNumber.objects.get(phone="51955555555").active
    assert Supplier.objects.count() == 2


@pytest.mark.django_db
def test_patch_edits_the_card_contact_and_replaces_the_rates(manager_client, scenario):
    from core.models import Material

    supplier = scenario["supplier"]
    fabric = Material.objects.get(sku="TEL-ALG-20-1")
    assert supplier.rates.count() == 1  # the polo at 6.50
    body = {
        "name": "Confecciones del Norte SAC", "city": "Castilla", "weekly_capacity": 900, "lead_time_days": 6, "currency": "PEN",
        "notes": "De usted.", "contact_name": "Valeria", "specialties": ["polos"],
        "rates": [{"product_id": scenario["product"].id, "unit_price": "7.10"}, {"material_id": fabric.id, "unit_price": "12.00", "valid_from": "2026-10-01"}],
    }
    response = manager_client.patch(f"/api/suppliers/{supplier.id}/", body, format="json")
    assert response.status_code == 200, response.content
    data = response.json()
    assert data["name"] == "Confecciones del Norte SAC" and data["weekly_capacity"] == 900 and data["notes"] == "De usted."
    assert {(r["product_id"], r["material_id"], r["unit_price"]) for r in data["rates"]} == {(scenario["product"].id, None, "7.10"), (None, fabric.id, "12.00")}
    assert next(n for n in data["numbers"] if not n["simulated"])["name"] == "Valeria"
    assert scenario["purchase_order"].items.get().unit_price == Decimal("6.50")  # History untouched.
    # The list replaces: an empty list clears the prices.
    assert manager_client.patch(f"/api/suppliers/{supplier.id}/", {"rates": []}, format="json").json()["rates"] == []


@pytest.mark.django_db
def test_rates_are_validated(manager_client, scenario):
    supplier = scenario["supplier"]
    product = scenario["product"].id
    for rates, fragment in (
        ([{"unit_price": "5.00"}], "material_id o product_id"),
        ([{"product_id": product, "material_id": 1, "unit_price": "5.00"}], "no ambos"),
        ([{"product_id": 999999, "unit_price": "5.00"}], "no existe"),
        ([{"product_id": product, "unit_price": "0"}], "rates"),
    ):
        response = manager_client.patch(f"/api/suppliers/{supplier.id}/", {"rates": rates}, format="json")
        assert response.status_code == 400 and fragment in str(response.json()), (rates, response.json())
    assert supplier.rates.count() == 1  # Nothing replaced on a rejected list.


@pytest.mark.django_db
def test_post_accepts_rates(manager_client, scenario):
    body = {**PAYLOAD, "name": "Taller con tarifas", "phone": "51977777777", "rates": [{"product_id": scenario["product"].id, "unit_price": "6.90"}]}
    response = manager_client.post("/api/suppliers/", body, format="json")
    assert response.status_code == 201, response.content
    assert [(r["product_id"], r["unit_price"]) for r in response.json()["rates"]] == [(scenario["product"].id, "6.90")]
