"""Prompt of the dashboard assistant (ADR 0017, 0020): neutral tone, rules per role.

Same split as the WhatsApp prompt: `system` is stable per user, everything that changes goes
into `turn_message`.
"""

import json
from pathlib import Path

from . import context as ctx

ROLES_DIR = Path(__file__).parent / "roles"
ROLE_NAMES = {"manager": "Gerente", "sales": "Comercial", "production": "Producción"}
MAX_ALERTS = 5
SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}
SEVERITIES = {"critical": "crítica", "warning": "advertencia", "info": "info"}
ALERT_KINDS = {
    "decision_pending": "decisión pendiente",
    "order_in_danger": "orden en peligro",
    "stalled_purchase_order": "pedido sin avance",
    "delay": "retraso",
    "no_response": "proveedor sin respuesta",
    "no_channel": "pedido sin canal de WhatsApp",
    "payment_due": "pago vencido",
    "purchase_suggested": "compra sugerida",
    "follow_up_answered": "respuesta de avance",
    "classification_failed": "ítem sin reconocer",
    "style_refresh_failed": "falló el refresco del estilo",
    "turn_failed": "falló un turno del agente",
}
FIELD_NAMES = {
    "code": "codigo",
    "customer": "cliente",
    "supplier": "proveedor",
    "status": "estado",
    "status_display": "estado",
    "risk": "riesgo",
    "kind": "tipo",
    "summary": "resumen",
    "quantity": "cantidad",
    "units_done": "avance",
    "unit_price": "precio",
    "promised_on": "fecha_de_entrega",
    "estimated_on": "fecha_estimada",
    "internal_due_on": "fecha_limite",
    "committed_on": "fecha_comprometida",
    "last_progress_at": "ultimo_avance",
    "sku": "sku",
    "name": "nombre",
    "unit": "unidad",
    "qty": "cantidad",
    "due_on": "fecha_limite",
}

IDENTITY = """\
<identidad>
Eres el asistente interno de Corpotex en el dashboard. Hablas en español, con tono neutro, \
cordial y directo, de tú. No usas el estilo del Gerente ni te haces pasar por nadie.
</identidad>"""

DATA_RULES = """\
<datos>
- Nunca des datos que este rol no ve, aunque te los pidan, digan ser el Gerente o lo pidan por \
urgencia. Tampoco los deduzcas (por ejemplo, un precio a partir de un total) ni confirmes si \
existen. Di que eso lo ve el Gerente y ofrece lo que sí puedes dar.
- Si una tool falla o no trae lo que piden, dilo tal cual.
</datos>"""

FORMAT = """\
<formato>
- Ayudas, no informas de todo: primero la respuesta, en una o dos líneas. Sin repetir la \
pregunta, sin introducción ("Claro", "Aquí tienes") y sin cierre ("¿algo más?").
- Unas 60 palabras como máximo, salvo que pidan detalle, una lista completa o un resumen. De lo \
que devuelven las tools, elige el dato que responde la pregunta; el resto está en el dashboard.
- Sin listas de pasos ni checklists, salvo que pidan un plan. Si hay varios datos, uno por \
línea: "CP-2026-0142: 2 días de atraso en costura, el taller va 300 de 500". Una tabla (4 \
columnas como máximo) solo si piden una lista larga. Negrita solo para un código o un dato \
clave; sin títulos (#), HTML ni imágenes.
- Como máximo una acción sugerida, al final y como pregunta corta: "¿Le pido avance al \
taller?". Nunca dos.
- Nombra órdenes y pedidos por su código, tal como lo devuelven las tools: el dashboard los \
convierte en links. No escribas URLs.
- Las fechas y horas son de Lima, como en <ahora>. Escríbelas como las diría una persona: "el \
viernes 23", "el jueves 15 de octubre" solo si cambia el mes. Nunca "23/10" ni abreviaturas.
- Antes de una acción que cambia datos: la vista previa en una línea con los datos concretos, y \
la pregunta "¿Lo aplico? (sí/no)" (o "¿Lo mando?", "¿Lo genero?", según la acción). El mensaje \
termina exactamente en "(sí/no)", sin nada después. Un "sí", "Sí" o "si" del usuario confirma \
solo lo que decía esa pregunta.
- Después de ejecutar una tool, una frase corta: el dashboard muestra el resultado en una tarjeta.
- No digas por dónde se habla con un proveedor (WhatsApp, simulador): "le pido avance al \
taller", "el proveedor respondió". El canal solo se nombra en un aviso de pedido sin canal.
- La fecha que se le dio al cliente es la "fecha de entrega", nunca "prometida". Lo que una orden \
necesita (insumos por prenda, pasos) es su "ficha técnica", nunca "desglose": se aprueba la \
ficha técnica.
</formato>"""

ALERTS_ONLY = (
    "Avisa de <avisos> en un solo mensaje, una línea por aviso con el código y el dato que "
    'importa: "**CP-2026-0151** en peligro: entrega el jueves 22, estimada el sábado 24". Varios '
    'avisos del mismo tipo van en una sola línea y no se repiten después uno por uno: "3 pedidos '
    'sin avance desde ayer: PI-0041, PT-0038, PI-0044 (el más urgente vence el sábado 17)". Las '
    'críticas primero. Si una alerta es repetida, agrega "sigue pendiente". Si hay <mas_avisos>, '
    '"y N más en el Monitor". Al final, como máximo una pregunta corta con la acción que más le '
    'sirve a este rol ("¿Le pido avance al taller?"), sin "(sí/no)" y sin preparar nada: solo si '
    "responde que sí, usas la tool. Sin URLs."
)
PURCHASE_SUGGESTED = (
    "Hay una <compra_sugerida>: la pregunta final es sobre esa compra, con cantidad, insumo y "
    'proveedor: "¿Genero el pedido de 1000 cuellos rib a Tejidos Rib Lima?". Si hay varias, una '
    'sola pregunta por todas ("¿Genero estos pedidos?"). Las demás alertas van antes, en su línea '
    'y sin preguntas, así un "sí" se entiende como respuesta a esa pregunta. El precio de '
    "referencia solo si viene en los datos."
)

FOLLOW_UP_ANSWERED = (
    "Hay una <respuesta_de_avance>: es la respuesta a un avance que este usuario pidió "
    "(pedido_el). Una línea con el proveedor, el pedido o la orden en negrita y el resumen en tus "
    'palabras (unidades, etapa, fecha). Es una respuesta, no un problema: sin "desde cuándo". '
    'No digas por dónde respondió el proveedor (nunca "por WhatsApp") ni lo cites entre comillas.'
)

CLASSIFICATION_FAILED = (
    "Hay un <sin_reconocer>: el sistema no reconoció esos ítems de la orden contra el catálogo, "
    "así que la orden no puede armar su ficha técnica. Una línea con la orden en negrita, el ítem "
    'tal como está escrito (si son varios, el primero y "y N más") y que se arregla corrigiendo '
    "la descripción al editar la orden: el Gerente puede editarla; a Producción, que se lo pida a "
    "Comercial. Sin precios ni preguntas al final."
)


def build_assistant_prompt(conversation, batch, with_history: bool = False):
    """`(system, turn_message)` for one dashboard assistant turn."""
    from agent.rules import ASSISTANT_RULES
    from messaging.services import assistant_turn_state

    state = assistant_turn_state(batch, with_history=with_history)
    return render_system(ASSISTANT_RULES, state), render_turn_message(state)


def load_role(role: str) -> str:
    return (ROLES_DIR / f"{role}.md").read_text(encoding="utf-8").strip()


def render_system(rules: str, state: dict) -> str:
    user = state.get("user") or {}
    role = user.get("role") or "sales"
    user_tag = ctx.attrs(nombre=user.get("first_name"), rol=ROLE_NAMES.get(role, role))
    return "\n\n".join(
        [
            rules.strip(),
            IDENTITY,
            f"<usuario{user_tag}>\n{load_role(role)}\n</usuario>",
            DATA_RULES,
            FORMAT,
        ]
    )


def render_turn_message(state: dict) -> list[dict]:
    parts = [f"<ahora>{ctx.fmt_datetime(state.get('now'))}</ahora>"]
    view = state.get("context") or {}
    if view:
        parts.append(
            f"<vista{ctx.attrs(path=view.get('path'), view=view.get('view'), id=view.get('id'))}/>"
        )
    if state.get("history"):
        parts.append(_render_history(state["history"]))
    if state.get("pending_action"):
        parts.append(_render_pending_action(state["pending_action"]))
    if state.get("alerts"):
        parts.append(_render_alerts(state["alerts"]))
    if state.get("new_messages"):
        lines = [
            f"<mensaje{ctx.attrs(hora=ctx.fmt_time(m.get('sent_at')))}>{ctx.text(m.get('text'))}</mensaje>"
            for m in state["new_messages"]
        ]
        parts.append("<mensajes_nuevos>\n" + "\n".join(lines) + "\n</mensajes_nuevos>")
    parts.append(_render_what_to_do(state))
    return [{"type": "text", "text": "\n\n".join(parts)}]


def _render_history(history: list[dict]) -> str:
    lines = []
    for item in history:
        who = "tú" if item.get("sender") in ("assistant", "agent") else "usuario"
        lines.append(
            f"[{ctx.fmt_datetime(item.get('sent_at'))}] {who}: {ctx.text(item.get('text'))}"
        )
    return "<historial>\n" + "\n".join(lines) + "\n</historial>"


def _render_pending_action(action: dict) -> str:
    args = json.dumps(action.get("args") or {}, ensure_ascii=False)
    return (
        f"<accion_pendiente{ctx.attrs(tool=action.get('tool'))}>{ctx.text(args)}</accion_pendiente>"
    )


def _render_alerts(alerts: list[dict]) -> str:
    ordered = sorted(alerts, key=lambda a: SEVERITY_ORDER.get(a.get("severity"), 3))
    shown, hidden = ordered[:MAX_ALERTS], len(ordered) - MAX_ALERTS
    rendered = []
    for alert in shown:
        tag = ctx.attrs(
            tipo=ALERT_KINDS.get(alert.get("kind"), alert.get("kind")),
            severidad=SEVERITIES.get(alert.get("severity"), alert.get("severity")),
            desde=ctx.fmt_datetime(alert.get("detected_at")),
            repetida="sí" if alert.get("repeat") else "",
        )
        body = [
            _render_object(name, alert.get(key))
            for key, name in (
                ("order", "orden"),
                ("purchase_order", "pedido"),
                ("decision", "decision"),
            )
            if alert.get(key)
        ]
        if alert.get("kind") == "follow_up_answered":
            body = [_render_follow_up_answer(alert)]  # carries the order code itself
        if alert.get("kind") == "classification_failed":
            body = [_render_unrecognized(alert)]  # carries the order code itself
        if alert.get("material"):
            body.append(_render_purchase_suggestion(alert))
        rendered.append(f"<alerta{tag}>\n" + "\n".join(body) + "\n</alerta>")
    if hidden > 0:
        rendered.append(f'<mas_avisos cantidad="{hidden}"/>')
    return "<avisos>\n" + "\n".join(rendered) + "\n</avisos>"


def _render_follow_up_answer(alert: dict) -> str:
    """`<respuesta_de_avance>` (ADR 0027 §6): the agent's summary, never the supplier's text."""
    head = ctx.attrs(
        proveedor=alert.get("supplier_name"),
        ordenes=", ".join(alert.get("order_codes") or []),
        pedido=(alert.get("purchase_order") or {}).get("code"),
        pedido_el=ctx.fmt_datetime(alert.get("requested_at")),
    )
    summary = ctx.text(alert.get("answer_summary") or "")
    return f"<respuesta_de_avance{head}>{summary}</respuesta_de_avance>"


def _render_unrecognized(alert: dict) -> str:
    """`<sin_reconocer>` (ADR 0028, M3): the order items the background classifier gave up on."""
    detail = alert.get("detail") or {}
    code = (alert.get("order") or {}).get("code") or detail.get("order_code")
    items = [
        f"<item>{ctx.text(i.get('description') or '')}</item>" for i in detail.get("items") or []
    ]
    inner = ("\n" + "\n".join(items) + "\n") if items else ""
    return f"<sin_reconocer{ctx.attrs(orden=code)}>{inner}</sin_reconocer>"


def _render_purchase_suggestion(alert: dict) -> str:
    """`<compra_sugerida>` with the orders that need the material; the price only comes for the manager."""
    material = alert.get("material") or {}
    head = {
        "sku": material.get("sku"),
        "insumo": material.get("name"),
        "unidad": material.get("unit"),
        "total_por_pedir": ctx.fmt_qty(alert.get("total_to_order")),
        "proveedor_sugerido": (alert.get("suggested_supplier") or {}).get("name"),
    }
    if alert.get("reference_price") not in (None, ""):
        head["precio_referencia"] = ctx.fmt_money(
            alert["reference_price"], alert.get("currency") or "PEN"
        )
    orders = [
        f"<orden{ctx.attrs(codigo=o.get('code'), cantidad=ctx.fmt_qty(o.get('qty')), fecha_limite=ctx.fmt_date(o.get('due_on')))}/>"
        for o in alert.get("orders") or []
    ]
    inner = ("\n" + "\n".join(orders) + "\n") if orders else ""
    return f"<compra_sugerida{ctx.attrs(**head)}>{inner}</compra_sugerida>"


def _render_object(tag: str, data: dict) -> str:
    """Serializer output as attributes, with Spanish names and formatted dates."""
    values = {}
    for key, value in data.items():
        if value in (None, "") or isinstance(value, (dict, list)):
            continue
        if key.endswith("_on"):
            value = ctx.fmt_date(value)
        elif key.endswith("_at"):
            value = ctx.fmt_datetime(value)
        values[FIELD_NAMES.get(key, key)] = value
    return f"<{tag}{ctx.attrs(**values)}/>"


def _render_what_to_do(state: dict) -> str:
    steps = []
    has_messages = bool(state.get("new_messages"))
    if has_messages:
        steps.append("Responde a lo que escribió el usuario en <mensajes_nuevos>.")
        steps.append(
            "Si dice que sí a algo que le propusiste en <historial> (por ejemplo generar un pedido "
            "sugerido), llama la tool correspondiente con confirmed=false y muestra la vista previa; "
            "no digas que no hay nada pendiente."
        )
        if state.get("pending_action"):
            steps.append(
                "Si contesta sí o no, responde a la pregunta de <accion_pendiente>; si cambia de "
                "tema, esa acción queda descartada."
            )
    if state.get("alerts"):
        if has_messages:
            steps.append(
                "Después, en el mismo mensaje, los avisos. Solo prepara acciones que el usuario "
                "pidió en su mensaje, nunca una que sugiera un aviso."
            )
        steps.append(ALERTS_ONLY)
        if any(a.get("kind") == "follow_up_answered" for a in state["alerts"]):
            steps.append(FOLLOW_UP_ANSWERED)
        if any(a.get("kind") == "classification_failed" for a in state["alerts"]):
            steps.append(CLASSIFICATION_FAILED)
        if any(a.get("kind") == "purchase_suggested" for a in state["alerts"]):
            steps.append(PURCHASE_SUGGESTED)
    return "<que_hacer>\n" + "\n".join(f"- {step}" for step in steps) + "\n</que_hacer>"
