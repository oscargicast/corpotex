"""A progress photo from WhatsApp or the simulator shows on the purchase order: the agent's tool
passes only the message, whose image lives in `Message.media` (agente, 11/10 04:30)."""

import base64

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone

from messaging.models import AllowedNumber, Conversation, Message
from operations import services
from operations.models import ProgressReport, PurchaseOrder
from tests.test_consolidated import catalogue  # noqa: F401
from tests.test_magic_order import client_for
from tests.test_revise_order import order  # noqa: F401

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


@pytest.fixture
def workshop_po(order, production, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    services.confirm_order(order, actor=production)
    return PurchaseOrder.objects.get(supplier__kind="workshop")


def supplier_message(name, content):
    number, _ = AllowedNumber.objects.get_or_create(phone="sim-taller-castilla", defaults={"active": True, "simulated": True})
    conversation, _ = Conversation.objects.get_or_create(channel="simulator", allowed_number=number)
    message = Message.objects.create(conversation=conversation, author="supplier", text="va avanzando", status="received", sent_at=timezone.now())
    message.media.save(name, ContentFile(content), save=True)
    return message


@pytest.mark.django_db
def test_the_agents_progress_report_shows_the_message_photo(workshop_po, manager):
    message = supplier_message("avance.png", PNG)
    report = services.record_progress(workshop_po, units_done=200, message_id=message.id, actor=None)  # what the agent's tool does
    assert report.photo.name == message.media.name  # the same file, not a copy
    [shown] = client_for(manager).get(f"/api/purchase-orders/{workshop_po.id}/").json()["progress_reports"]
    assert shown["photo"] == message.media.url and shown["source"] == "whatsapp" and shown["units_done"] == 200


@pytest.mark.django_db
def test_an_earlier_report_without_photo_falls_back_to_its_message(workshop_po, manager):
    message = supplier_message("avance.jpg", PNG)
    ProgressReport.objects.create(purchase_order=workshop_po, units_done=50, message=message, reported_at=timezone.now())
    audio = supplier_message("nota.ogg", b"OggS")
    report = services.record_progress(workshop_po, units_done=80, message_id=audio.id, actor=None)
    assert not report.photo  # a voice note is not a photo
    shown = {r["units_done"]: r["photo"] for r in client_for(manager).get(f"/api/purchase-orders/{workshop_po.id}/").json()["progress_reports"]}
    assert shown == {50: message.media.url, 80: None}
