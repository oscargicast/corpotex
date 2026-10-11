"""ADR 0029 N1: an order item carries the garment's photo from the form."""

import base64
import io
from pathlib import Path

import pytest
from PIL import Image

from operations.models import Order
from tests.test_consolidated import catalogue  # noqa: F401
from tests.test_magic_order import classified_payload, client_for


def png_base64() -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (20, 40, 160)).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def plain_payload(catalogue):
    return {k: v for k, v in classified_payload(catalogue).items() if k != "classification"}


@pytest.fixture
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.mark.django_db
def test_an_order_with_a_photo_stores_the_file_and_exposes_its_url(catalogue, sales, media):
    client = client_for(sales)
    payload = plain_payload(catalogue)
    payload["items"][0]["photo"] = {"media_type": "image/png", "data": png_base64()}
    response = client.post("/api/orders/", payload, format="json")
    assert response.status_code == 201, response.content
    photo_url, no_photo = (item["photo_url"] for item in response.json()["items"])
    assert photo_url.startswith("/media/items/") and photo_url.endswith(".png") and no_photo is None
    assert (media / photo_url.removeprefix("/media/")).is_file()
    detail = client.get(f"/api/orders/{response.json()['id']}/").json()
    assert [item["photo_url"] for item in detail["items"]] == [photo_url, None]


@pytest.mark.django_db
def test_an_edit_keeps_a_resent_photo_url_and_rejects_a_bad_photo(catalogue, sales, media):
    client = client_for(sales)
    payload = plain_payload(catalogue)
    payload["items"][0]["photo"] = {"media_type": "png", "data": f"data:image/png;base64,{png_base64()}"}
    order_id = client.post("/api/orders/", payload, format="json").json()["id"]
    photo_url = Order.objects.get(pk=order_id).items.exclude(photo="").get().photo.url

    items = [{k: v for k, v in item.items() if k != "photo"} for item in payload["items"]]
    kept = client.patch(f"/api/orders/{order_id}/", {"items": [{**items[0], "photo_url": photo_url}, items[1]]}, format="json")
    assert kept.status_code == 200, kept.content
    assert [item["photo_url"] for item in kept.json()["items"]] == [photo_url, None]

    for photo, detail in (
        ({"media_type": "image/gif", "data": png_base64()}, "JPEG, PNG o WebP"),
        ({"media_type": "image/jpeg", "data": base64.b64encode(b"not an image").decode()}, "no se pudo abrir"),
    ):
        bad = client.patch(f"/api/orders/{order_id}/", {"items": [{**items[0], "photo": photo}, items[1]]}, format="json")
        assert bad.status_code == 400 and detail in bad.json()["detail"]
    foreign = client.patch(f"/api/orders/{order_id}/", {"items": [{**items[0], "photo_url": "/media/products/x.png"}]}, format="json")
    assert foreign.status_code == 400
    assert Order.objects.get(pk=order_id).items.exclude(photo="").get().photo.url == photo_url  # nothing changed

    dropped = client.patch(f"/api/orders/{order_id}/", {"items": items}, format="json")
    assert [item["photo_url"] for item in dropped.json()["items"]] == [None, None]
    assert Path(media / photo_url.removeprefix("/media/")).is_file()  # the old file stays on disk
