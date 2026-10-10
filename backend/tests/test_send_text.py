"""Outgoing messages: Evolution is mocked; the allowlist is re-checked on every send."""

from unittest import mock

import pytest

from messaging import services
from messaging.models import Conversation, Message
from tests.scenario import build


@pytest.fixture
def scenario(db, sales):
    return build(owner=sales)


@pytest.fixture
def evolution():
    client = mock.Mock()
    client.send_text.return_value = {"key": {"id": "WAMID1"}, "status": "PENDING"}
    with mock.patch("messaging.evolution.EvolutionClient.from_settings", return_value=client):
        yield client


@pytest.mark.django_db
def test_whatsapp_send_goes_through_evolution(scenario, evolution):
    message = services.send_text(scenario["conversation"], "buenos días 🙏", None)
    evolution.send_text.assert_called_once_with("51906746241", "buenos días 🙏")
    assert message.author == "agent"
    assert message.status == "sent"
    assert message.external_id == "WAMID1"


@pytest.mark.django_db
def test_failed_send_is_kept_as_failed_and_raised(scenario, evolution):
    evolution.send_text.side_effect = RuntimeError("instance closed")
    with pytest.raises(services.SendFailed):
        services.send_text(scenario["conversation"], "hola", None)
    message = Message.objects.get(author="agent")
    assert message.status == "failed"
    assert "instance closed" in message.error


@pytest.mark.django_db
def test_simulator_conversation_never_calls_evolution(scenario, evolution):
    simulated = scenario["supplier"].numbers.get(simulated=True)
    conversation = services.conversation_for_number(simulated, Conversation.Channel.SIMULATOR)
    message = services.send_text(conversation, "hola", None)
    evolution.send_text.assert_not_called()
    assert message.status == "sent"


@pytest.mark.django_db
def test_inactive_or_simulated_numbers_are_refused_on_whatsapp(scenario, evolution):
    simulated = scenario["supplier"].numbers.get(simulated=True)
    conversation = Conversation.objects.create(channel="whatsapp", allowed_number=simulated)
    with pytest.raises(services.NumberNotAllowed):
        services.send_text(conversation, "hola", None)
    scenario["number"].active = False
    scenario["number"].save()
    with pytest.raises(services.NumberNotAllowed):
        services.send_text(scenario["conversation"], "hola", None)
    evolution.send_text.assert_not_called()
