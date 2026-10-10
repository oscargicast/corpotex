"""Suggested suppliers from the assistant's web search (ADR 0024)."""

import pytest
from django.core.exceptions import PermissionDenied

from suppliers.models import Supplier
from suppliers.services import create_suggested_suppliers

CANDIDATES = [
    {"name": "Taller Textil Piura", "city": "Piura", "kind": "workshop", "specialty": "costura de polos", "source_url": "https://example.com/a", "evidence": "Taller con 20 máquinas."},
    {"name": "taller textil  piura", "city": "PIURA", "kind": "workshop", "specialty": "polos", "source_url": "https://example.com/b", "evidence": "dup"},
    {"name": "Hilos del Norte", "city": "Lima", "kind": "material", "specialty": "hilo poliéster", "source_url": "https://example.com/c", "evidence": "Mayorista."},
]


@pytest.mark.django_db
def test_create_suggested_suppliers_dedupes_and_keeps_notes_clean(manager):
    Supplier.objects.create(name="Hilos del Norte", kind="material", city="Lima")
    result = create_suggested_suppliers(CANDIDATES, actor=manager)
    assert [c["name"] for c in result["created"]] == ["Taller Textil Piura"]
    assert [s["name"] for s in result["skipped"]] == ["taller textil piura", "Hilos del Norte"]
    created = Supplier.objects.get(name="Taller Textil Piura")
    assert created.source == "external" and created.status == "pending_review"
    assert created.source_detail == {"url": "https://example.com/a", "evidence": "Taller con 20 máquinas."}
    assert created.notes == "" and created.specialties == ["costura de polos"]
    # Running again creates nothing new.
    assert create_suggested_suppliers(CANDIDATES, actor=manager)["created"] == []


@pytest.mark.django_db
def test_only_the_manager_can_add_suggested_suppliers(sales):
    with pytest.raises(PermissionDenied):
        create_suggested_suppliers(CANDIDATES, actor=sales)
