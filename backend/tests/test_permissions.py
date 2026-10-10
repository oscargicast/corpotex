import pytest
from django.core.exceptions import PermissionDenied

from core.permissions import require_role


@pytest.mark.django_db
def test_require_role_raises_for_other_role(sales, manager):
    require_role(manager, "manager")
    require_role(None, "manager")  # the system itself
    with pytest.raises(PermissionDenied):
        require_role(sales, "manager")


def test_require_role_actor_is_mandatory():
    with pytest.raises(TypeError):
        require_role()  # type: ignore[call-arg]


@pytest.mark.django_db
def test_login_returns_token_and_role(anonymous_client, manager):
    response = anonymous_client.post("/api/auth/login/", {"username": "gerente", "password": "gerente"})
    assert response.status_code == 200
    body = response.json()
    assert body["token"]
    assert body["user"]["role"] == "manager"

    anonymous_client.credentials(HTTP_AUTHORIZATION=f"Token {body['token']}")
    assert anonymous_client.get("/api/auth/me/").json()["username"] == "gerente"
    # Logout does not revoke the token (two demo windows share it); the client forgets it.
    assert anonymous_client.post("/api/auth/logout/").status_code == 200
    assert anonymous_client.get("/api/auth/me/").status_code == 200


@pytest.mark.django_db
def test_login_rejects_bad_password(anonymous_client, manager):
    response = anonymous_client.post("/api/auth/login/", {"username": "gerente", "password": "nope"})
    assert response.status_code == 400
