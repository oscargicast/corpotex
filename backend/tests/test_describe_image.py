"""M4 (ADR 0028, photos): `POST /api/orders/describe-image/` turns a garment photo into the line's text."""

from unittest import mock

import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from operations import describe

PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
SENTENCE = "Polo deportivo azul marino de cuello redondo, manga corta, franja amarilla en hombros y escudo sublimado en el pecho"


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {Token.objects.get_or_create(user=user)[0].key}")
    return client


@pytest.mark.django_db
def test_a_photo_becomes_one_sentence_for_the_three_roles(sales, production, manager):
    body = {"image": {"media_type": "image/png", "data": PNG}, "brand": "UNICRACK", "customer": "Caja Piura"}
    with mock.patch("agent.sdk.complete", new=mock.AsyncMock(return_value={"description": f"  {SENTENCE} "})) as complete:
        for user in (sales, production, manager):
            response = client_for(user).post("/api/orders/describe-image/", body, format="json")
            assert response.status_code == 200, response.content
            assert response.json() == {"description": SENTENCE}
    blocks = complete.call_args.args[0]
    assert blocks[0]["type"] == "image" and blocks[0]["source"]["media_type"] == "image/png" and blocks[0]["source"]["data"] == PNG
    assert blocks[1]["type"] == "text" and "marca UNICRACK" in blocks[1]["text"] and "cliente Caja Piura" in blocks[1]["text"]
    kwargs = complete.call_args.kwargs
    assert kwargs["system_prompt"] == describe.SYSTEM_PROMPT and kwargs["effort"] == "low" and kwargs["schema"] == describe.SCHEMA
    assert "sin cantidad ni tallas" in kwargs["system_prompt"]


@pytest.mark.django_db
def test_short_media_types_and_data_urls_are_accepted(sales):
    with mock.patch("agent.sdk.complete", new=mock.AsyncMock(return_value={"description": SENTENCE})) as complete:
        response = client_for(sales).post("/api/orders/describe-image/", {"image": {"media_type": "webp", "data": f"data:image/webp;base64,{PNG}"}}, format="json")
    assert response.status_code == 200 and complete.call_args.args[0][0]["source"]["media_type"] == "image/webp"
    assert "Contexto" not in complete.call_args.args[0][1]["text"]  # no brand nor customer given


@pytest.mark.django_db
def test_bad_images_answer_400_in_spanish_without_calling_the_model(sales):
    client = client_for(sales)
    with mock.patch("agent.sdk.complete", new=mock.AsyncMock()) as complete:
        cases = [
            ({"image": {"media_type": "image/gif", "data": PNG}}, "JPEG, PNG o WebP"),
            ({"image": {"media_type": "image/jpeg", "data": "A" * (describe.MAX_BASE64 + 4)}}, "más de 5 MB"),
            ({"image": {"media_type": "image/jpeg", "data": "esto no es base64!"}}, "base64 inválido"),
            ({"brand": "UNICRACK"}, "Falta la foto"),
        ]
        for body, words in cases:
            response = client.post("/api/orders/describe-image/", body, format="json")
            assert response.status_code == 400, (body.keys(), response.content[:200])
            assert words in response.json()["detail"]
    complete.assert_not_called()


@pytest.mark.django_db
def test_a_model_failure_answers_502_so_the_person_types_it(sales):
    for failure in (RuntimeError("model down"), TimeoutError(), {"description": "   "}):
        complete = mock.AsyncMock(side_effect=failure) if isinstance(failure, BaseException) else mock.AsyncMock(return_value=failure)
        with mock.patch("agent.sdk.complete", new=complete):
            response = client_for(sales).post("/api/orders/describe-image/", {"image": {"media_type": "image/png", "data": PNG}}, format="json")
        assert response.status_code == 502 and response.json() == {"detail": "No se pudo describir la foto. Escribe la prenda a mano."}
