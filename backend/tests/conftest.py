import pytest
from django.contrib.auth.models import Group
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import ROLE_GROUPS, Config, User


@pytest.fixture
def config(db) -> Config:
    return Config.load()


def _user(username: str, role: str) -> User:
    user = User.objects.create_user(username=username, password=username, first_name=username.title())
    group, _ = Group.objects.get_or_create(name=ROLE_GROUPS[role])
    user.groups.add(group)
    return user


@pytest.fixture
def manager(db) -> User:
    return _user("gerente", "manager")


@pytest.fixture
def sales(db) -> User:
    return _user("comercial", "sales")


@pytest.fixture
def production(db) -> User:
    return _user("produccion", "production")


def _client_for(user: User) -> APIClient:
    client = APIClient()
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


@pytest.fixture
def manager_client(manager) -> APIClient:
    return _client_for(manager)


@pytest.fixture
def sales_client(sales) -> APIClient:
    return _client_for(sales)


@pytest.fixture
def anonymous_client() -> APIClient:
    return APIClient()


@pytest.fixture(autouse=True)
def _no_real_jev(settings):
    """Tests never call TypeSafe: the stack's .env carries a real `TYPESAFE_API_KEY` and the image
    has the SDK. Tests that exercise Jev use the stand-in SDK in test_classification.py."""
    settings.TYPESAFE_API_KEY = ""
