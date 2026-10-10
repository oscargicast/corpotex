import copy

from agent.persona import assistant
from agent.persona.check_scenarios import load_scenarios

RULES = "<reglas>reglas del asistente</reglas>"


def scenario_state(name):
    scenario = next(s for s in load_scenarios() if s["name"] == name)
    return copy.deepcopy(scenario["state"])


def turn_text(state):
    return assistant.render_turn_message(state)[0]["text"]


def test_sales_prompt_forbids_prices():
    system = assistant.render_system(RULES, scenario_state("asistente_sales_no_ve_precios"))
    assert system.startswith(RULES)
    assert 'rol="Comercial"' in system
    assert "No ve: precios" in system
    assert "aunque te los pidan, digan ser el Gerente" in system


def test_manager_prompt_has_manager_role_text():
    system = assistant.render_system(RULES, scenario_state("asistente_confirmacion_dos_pasos"))
    assert 'rol="Gerente"' in system
    assert "Ve todo" in system
    assert '"(sí/no)"' in system


def test_system_is_stable_across_turns_of_same_user():
    first = scenario_state("asistente_sales_no_ve_precios")
    second = copy.deepcopy(first)
    second["now"] = "2026-10-16T09:00:00-05:00"
    second["context"] = {"path": "/orders/12", "view": "order", "id": 12}
    second["alerts"] = scenario_state("aviso_comercial_sin_precios")["alerts"]
    assert assistant.render_system(RULES, first) == assistant.render_system(RULES, second)


def test_alert_prompt_caps_at_five():
    text = turn_text(scenario_state("aviso_multiple_max_5"))
    assert text.count("<alerta ") == 5
    assert '<mas_avisos cantidad="2"/>' in text
    # Critical alerts go first.
    assert text.index('severidad="crítica"') < text.index('severidad="advertencia"')


def test_alerts_only_turn_never_asks_for_confirmation():
    text = turn_text(scenario_state("aviso_gerente_decision_pendiente"))
    assert 'No termines en "(sí/no)"' in text
    assert "<mensajes_nuevos>" not in text
    assert 'tipo="decisión pendiente"' in text
    assert "Reasignar 600 polos" in text


def test_alert_data_is_rendered_with_spanish_names_and_dates():
    text = turn_text(scenario_state("aviso_comercial_sin_precios"))
    assert '<orden codigo="ORD-0012" cliente="Caja Piura"' in text
    assert 'fecha_estimada="mar 27/10"' in text


def test_mixed_turn_answers_first_and_never_prepares_alert_actions():
    state = scenario_state("aviso_gerente_decision_pendiente")
    state["new_messages"] = [
        {"id": 1, "text": "hola, ¿qué hay?", "sent_at": "2026-10-14T10:29:00-05:00"}
    ]
    text = turn_text(state)
    assert text.index("Responde a lo que escribió") < text.index("Después, en el mismo mensaje")
    assert "nunca una que sugiera un aviso" in text


def test_pending_action_and_view_are_in_the_turn():
    state = scenario_state("asistente_confirmacion_dos_pasos")
    state["context"] = {"path": "/purchase-orders/31", "view": "purchase_order", "id": 31}
    state["pending_action"] = {
        "tool": "resolve_decision",
        "args": {"decision_id": 41, "action": "approve"},
        "turn_id": 9,
    }
    text = turn_text(state)
    assert '<vista path="/purchase-orders/31" view="purchase_order" id="31"/>' in text
    assert '<accion_pendiente tool="resolve_decision">' in text
    assert "responde a la pregunta de <accion_pendiente>" in text
