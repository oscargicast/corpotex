import re

from agent.persona.check_scenarios import check, load_scenarios, parse_output

KNOWN_KEYS = {
    "name",
    "agent",
    "priority",
    "description",
    "state",
    "must",
    "must_not",
    "expect_tools",
    "forbid_tools",
    "max_messages",
    "ends_with",
    "max_chars",
}


def test_scenarios_are_well_formed():
    scenarios = load_scenarios()
    names = [s["name"] for s in scenarios]
    assert len(names) == len(set(names))
    assert len(scenarios) >= 20
    for scenario in scenarios:
        assert scenario["agent"] in {"whatsapp", "assistant"}, scenario["name"]
        assert set(scenario) <= KNOWN_KEYS, scenario["name"]
        for pattern in (scenario.get("must") or []) + (scenario.get("must_not") or []):
            re.compile(pattern)


def test_template_is_loaded_into_whatsapp_states():
    whatsapp = [s for s in load_scenarios() if s["agent"] == "whatsapp"]
    assert all(s["state"]["style_md"].startswith("# Estilo del Gerente") for s in whatsapp)


def test_parse_output_and_check():
    output = (
        'TOOL: escalate_to_manager {"reason": "precio"}\nMENSAJE: déjeme revisarlo y le confirmo'
    )
    messages, tools = parse_output(output, "whatsapp")
    scenario = {
        "must": ["revis"],
        "must_not": ["cerramos"],
        "expect_tools": ["escalate_to_manager"],
        "forbid_tools": ["confirm_purchase_order"],
        "max_messages": 1,
    }
    assert check(scenario, messages, tools) == []
    assert tools == ["escalate_to_manager", "send_message"]  # each MENSAJE counts as the tool
    assert check({"forbid_tools": ["send_message"]}, messages, tools) == ["usó send_message"]


def test_parse_output_assistant_answer_is_multiline():
    output = (
        "TOOL: resolve_decision {}\nRESPUESTA: ¿Apruebo la reasignación?\nSon 600 polos. (sí/no)"
    )
    messages, tools = parse_output(output, "assistant")
    assert tools == ["resolve_decision"]
    assert check({"ends_with": "(sí/no)"}, messages, tools) == []


def test_max_chars_limit():
    assert check({"max_chars": 10}, ["corto"], []) == []
    assert check({"max_chars": 10}, ["esto es bastante largo"], []) == [
        "un mensaje pasa de 10 caracteres"
    ]
