from datetime import date

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.models import Brand, Customer
from manager.models import Alert
from messaging.models import AllowedNumber, Conversation, Turn
from operations.models import Order
from suppliers.models import Supplier


@pytest.fixture
def conversation(db):
    supplier = Supplier.objects.create(name="Taller Uno", kind="workshop")
    number = AllowedNumber.objects.create(phone="sim-taller-uno", supplier=supplier, active=True, simulated=True)
    return Conversation.objects.create(channel="simulator", allowed_number=number)


@pytest.mark.django_db
def test_second_pending_turn_same_conversation_raises_integrity_error(conversation):
    Turn.objects.create(conversation=conversation, reason="message", available_at=timezone.now())
    with pytest.raises(IntegrityError), transaction.atomic():
        Turn.objects.create(conversation=conversation, reason="follow_up", available_at=timezone.now())
    # A `done` turn does not block a new pending one.
    Turn.objects.filter(conversation=conversation).update(status="done")
    Turn.objects.create(conversation=conversation, reason="message", available_at=timezone.now())


@pytest.mark.django_db
def test_dashboard_conversation_requires_user(manager):
    with pytest.raises(IntegrityError), transaction.atomic():
        Conversation.objects.create(channel="dashboard")
    Conversation.objects.create(channel="dashboard", user=manager)
    with pytest.raises(IntegrityError), transaction.atomic():
        Conversation.objects.create(channel="dashboard", user=manager)


@pytest.mark.django_db
def test_whatsapp_conversation_requires_number(manager):
    with pytest.raises(IntegrityError), transaction.atomic():
        Conversation.objects.create(channel="whatsapp", user=manager)


@pytest.mark.django_db
def test_open_alert_not_duplicated_with_null_fks():
    brand = Brand.objects.create(name="UNICRACK")
    customer = Customer.objects.create(name="Caja Piura", kind="company")
    order = Order.objects.create(
        code="CP-0001", customer=customer, brand=brand, issued_on=date(2026, 10, 1), promised_on=date(2026, 10, 20)
    )
    now = timezone.now()
    Alert.objects.create(kind="order_in_danger", order=order, text="x", detected_at=now)
    with pytest.raises(IntegrityError), transaction.atomic():
        Alert.objects.create(kind="order_in_danger", order=order, text="y", detected_at=now)
    # Resolved alerts do not block a new open one.
    Alert.objects.filter(order=order).update(status="resolved")
    Alert.objects.create(kind="order_in_danger", order=order, text="z", detected_at=now)
