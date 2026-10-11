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
    assert '<orden codigo="CP-2026-0012" cliente="Caja Piura"' in text
    assert 'fecha_estimada="martes 27 de octubre"' in text
    assert "fecha_de_entrega=" in text and "prometida" not in text  # ADR 0029 §1


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


def test_purchase_suggested_alert_carries_the_material_and_the_price_only_for_the_manager():
    manager_text = turn_text(scenario_state("sugerencia_de_compra_gerente"))
    assert 'tipo="compra sugerida"' in manager_text
    assert (
        '<compra_sugerida sku="BTN-NX-15" insumo="botón NX 15 mm" unidad="unidad" total_por_pedir="900"'
        in manager_text
    )
    assert 'proveedor_sugerido="Avíos Gamarra" precio_referencia="S/ 0.18"' in manager_text
    assert (
        '<orden codigo="CP-2026-0142" cantidad="400" fecha_limite="martes 20 de octubre"/>'
        in manager_text
    )
    assert "¿Genero el pedido de 1000 cuellos rib" in manager_text

    production_text = turn_text(scenario_state("sugerencia_de_compra_produccion"))
    assert "precio_referencia" not in production_text and "0.18" not in production_text
    assert 'proveedor_sugerido="Avíos Gamarra"' in production_text


def test_roles_describe_how_to_preview_a_consolidated_purchase():
    for role, price in (("manager", "S/ 0.18"), ("production", "sin precios")):
        text = assistant.load_role(role)
        assert "generate_purchase_orders" in text and price in text
    assert "generate_purchase_orders" not in assistant.load_role("sales")


def test_purchase_quantities_arrive_as_decimal_strings():
    state = scenario_state("sugerencia_de_compra_gerente")
    state["alerts"][0]["total_to_order"] = "900.00"
    state["alerts"][0]["orders"][0]["qty"] = "400.00"
    text = turn_text(state)
    assert 'total_por_pedir="900"' in text and 'cantidad="400"' in text


def test_a_yes_to_a_suggestion_in_history_asks_for_the_preview():
    state = scenario_state("generar_pedido_confirmacion_produccion")
    state["history"] = [
        {
            "sender": "assistant",
            "text": "**Compra sugerida: cuello rib** ¿Genero el pedido?",
            "sent_at": "2026-10-14T08:00:00-05:00",
        }
    ]
    state["new_messages"] = [{"id": 1, "text": "sí", "sent_at": "2026-10-14T08:05:00-05:00"}]
    text = turn_text(state)
    assert "<historial>" in text
    assert "llama la tool correspondiente con confirmed=false" in text
    assert "no digas que no hay nada pendiente" in text


def test_assistant_format_asks_for_human_dates():
    system = assistant.render_system(RULES, scenario_state("asistente_confirmacion_dos_pasos"))
    assert 'Nunca "23/10" ni abreviaturas' in system
    assert "No digas por dónde se habla con un proveedor (WhatsApp, simulador)" in system


def test_mixed_batch_asks_a_single_question_about_the_purchase():
    text = turn_text(scenario_state("avisos_mixtos_con_compra"))
    assert text.index('tipo="orden en peligro"') < text.index(
        'tipo="compra sugerida"'
    )  # critical first
    assert "UNA sola pregunta, sobre esa compra" in text
    assert "van antes, como contexto, sin preguntas" in text
    assert 'total_por_pedir="1000"' in text


def test_follow_up_answer_renders_the_summary_and_who_answered():
    text = turn_text(scenario_state("aviso_respuesta_de_avance"))
    assert '<alerta tipo="respuesta de avance" severidad="info"' in text
    assert (
        '<respuesta_de_avance proveedor="Avíos Gamarra" ordenes="CP-2026-0158" pedido="PI-0044" '
        'pedido_el="miércoles 14 de octubre, 09:40">500 de 3430 conos listos' in text
    )
    assert "<pedido " not in text  # the answer carries the code; no duplicate object
    assert 'nunca "por WhatsApp"' in text


def test_every_role_knows_it_can_ask_for_progress():
    for role in ("manager", "production", "sales"):
        state = scenario_state("asistente_confirmacion_dos_pasos")
        state["user"]["role"] = role
        assert "(request_follow_up)" in assistant.render_system(RULES, state), role


def test_classification_failed_names_the_item_and_who_fixes_it():
    text = turn_text(scenario_state("aviso_item_sin_reconocer"))
    assert '<alerta tipo="ítem sin reconocer" severidad="advertencia"' in text
    assert (
        '<sin_reconocer orden="CP-2026-0160">\n'
        "<item>Casaca cortavientos impermeable con forro polar</item>\n</sin_reconocer>"
    ) in text
    assert "si hablas con Producción, que se lo pida a Comercial" in text


def test_technical_sheet_names_and_revise_order_by_role():
    state = scenario_state("asistente_confirmacion_dos_pasos")
    for role in ("manager", "production", "sales"):
        state["user"]["role"] = role
        system = assistant.render_system(RULES, state)
        assert '"ficha técnica", nunca "desglose"' in system
        assert "desglose de" not in system and "fecha prometida" not in system
        assert ("(revise_order)" in system) == (role != "sales"), role
        if role != "sales":
            assert '"¿Aplico? (sí/no)"' in system
