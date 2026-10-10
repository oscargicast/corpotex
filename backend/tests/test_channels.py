from types import SimpleNamespace

import pytest
from agent_fakes import install

from agent import channels


def conversation(channel="whatsapp", active=True, simulated=False, has_number=True):
    number = SimpleNamespace(active=active, simulated=simulated) if has_number else None
    return SimpleNamespace(pk=1, channel=channel, allowed_number=number)


def test_sends_through_send_text(monkeypatch):
    calls = install(monkeypatch)
    conv = conversation()
    channels.send(conv, "hola", "turno")
    assert calls.sent == [(conv, "hola", "turno")]


@pytest.mark.parametrize(
    "conv",
    [
        conversation(active=False),
        conversation(has_number=False),
        conversation(simulated=True),
    ],
    ids=["inactive", "no-number", "simulated-on-whatsapp"],
)
def test_channel_refuses_number_outside_allowlist(monkeypatch, conv):
    calls = install(monkeypatch)
    with pytest.raises(calls.NumberNotAllowed):
        channels.send(conv, "hola", None)
    assert calls.sent == []


def test_simulator_accepts_simulated_number(monkeypatch):
    calls = install(monkeypatch)
    channels.send(conversation(channel="simulator", simulated=True), "hola", None)
    assert len(calls.sent) == 1
