"""Prompt of the WhatsApp agent: the manager's style plus fresh turn state.

`system` must be identical across turns of the same conversation (prompt cache and resumed
session), so everything that changes goes into `turn_message` (ADR 0010).
"""

from . import context as ctx

SUPPLIER_KINDS = {"workshop": "taller", "material": "insumos", "finished": "terminado"}
DECISION_KINDS = {
    "approve_assignment": "asignación",
    "price": "precio",
    "terms": "términos",
    "other": "otro",
}
DECISION_STATUSES = {
    "approved": "aprobada",
    "rejected": "rechazada",
    "supplier_changed": "cambió de proveedor",
    "cancelled": "cancelada",
}

HOW_TO_WRITE = """\
<como_escribir>
- Escribes por WhatsApp desde el número del Gerente y con el estilo de <estilo>. Escribe de 1 a 3 \
mensajes cortos, según la sección Forma; cada mensaje es una llamada a send_message. Sin markdown, \
listas ni firma.
- Trato: el que digan las notas de <proveedor>. Si no dicen nada, de usted.
- Las fechas como las diría una persona: "el jueves 15", "para el martes 20". Nombra el mes solo si \
es otro mes. Nunca escribas "15/10" ni abreviaturas.
- Nombre: usa solo el atributo contacto de <proveedor>. Si está vacío, saluda sin nombre ("buenas", \
"buenos días, ¿cómo está?"). Nunca saques un nombre del nombre del proveedor, de las notas ni del estilo.
- Los marcadores del estilo (<CONTACTO>, <PROVEEDOR>, <PERSONA>, <MONTO>, <FECHA>, <HORA>, <CANTIDAD>, \
<PEDIDO> y cualquier otro entre < >) son \
huecos: complétalos con los datos del turno o no uses esa frase. Nunca los copies tal cual.
- Cuando algo lo decide el Gerente, di que lo revisas y confirmas ("déjeme revisarlo y le confirmo", \
con el trato que toque). Nunca digas que vas a consultar al Gerente: escribes desde su número.
- Si te preguntan en serio si eres un bot o una persona, responde en una frase corta y en este estilo \
que eres el asistente del Gerente para los pedidos y que él ve todo. Sin disculpas de más.
- Saluda (y pregunta por la familia) solo al abrir la conversación del día. Si ya vienen \
conversando, ve directo al tema.
- Si las notas dicen que no le gusta que le insistan, el seguimiento es un solo mensaje corto, \
con el saludo y la pregunta juntos.
- Para mandar el link de reporte usa send_report_link con una intro de una línea en este estilo y \
sin URL (el link lo agrega el sistema). Solo si ese pedido no lo tiene enviado, y en el primer \
contacto o cuando pregunten cómo reportar.
</como_escribir>"""


def build_prompt(conversation, batch, with_history: bool = False):
    """`(system, turn_message)` for one WhatsApp turn; `turn_message` is a list of blocks."""
    from agent.rules import RULES
    from messaging.services import turn_state

    state = turn_state(batch, with_history=with_history)
    images = ctx.load_message_images(state.get("new_messages") or [])
    return render_system(RULES, state), render_turn_message(state, images)


def render_system(rules: str, state: dict) -> str:
    supplier = state.get("supplier") or {}
    manager = state.get("manager_name") or "el Gerente"
    supplier_tag = ctx.attrs(
        nombre=supplier.get("name"),
        tipo=SUPPLIER_KINDS.get(supplier.get("kind"), supplier.get("kind")),
        ciudad=supplier.get("city"),
        moneda=supplier.get("currency"),
        contacto=supplier.get("contact_name") or "",
    )
    notes = ctx.text(supplier.get("notes") or "Sin notas.")
    style = (state.get("style_md") or "").strip()
    return "\n\n".join(
        [
            rules.strip(),
            f"<estilo>\nAsí escribe {ctx.text(manager)}, el Gerente de Corpotex.\n\n{style}\n</estilo>",
            f"<proveedor{supplier_tag}>\n{notes}\n</proveedor>",
            HOW_TO_WRITE,
        ]
    )


def render_turn_message(state: dict, images: list[tuple[str, dict]] = ()) -> list[dict]:
    currency = (state.get("supplier") or {}).get("currency") or "PEN"
    orders = state.get("purchase_orders") or []
    parts = [f"<ahora>{ctx.fmt_datetime(state.get('now'))}</ahora>"]
    parts.append(_render_orders(orders, currency))

    if state.get("history"):
        parts.append(_render_history(state["history"]))
    if state.get("decisions"):
        parts.append(_render_decisions(state["decisions"]))
    follow_ups = [o["code"] for o in orders if o.get("is_follow_up")]
    if follow_ups:
        parts.append(f"<seguimientos>{', '.join(follow_ups)}</seguimientos>")
    new_orders = [o["code"] for o in orders if o.get("is_new")]
    if new_orders:
        parts.append(f"<pedidos_nuevos>{', '.join(new_orders)}</pedidos_nuevos>")
    if state.get("web_reports"):
        parts.append(_render_web_reports(state["web_reports"]))
    if state.get("new_messages"):
        parts.append(_render_new_messages(state["new_messages"]))
    parts.append(_render_what_to_do(state, follow_ups, new_orders))

    blocks = [{"type": "text", "text": "\n\n".join(parts)}]
    for label, block in images:
        blocks.append({"type": "text", "text": label})
        blocks.append(block)
    return blocks


def _render_orders(orders: list[dict], currency: str) -> str:
    if not orders:
        return "<pedidos>Sin pedidos abiertos con este proveedor.</pedidos>"
    rendered = []
    for order in orders:
        tag = ctx.attrs(
            codigo=order.get("code"),
            estado=order.get("status_display") or order.get("status"),
            fecha_limite=ctx.fmt_date(order.get("internal_due_on")),
            fecha_comprometida=ctx.fmt_date(order.get("committed_on")),
            avance=order.get("units_done"),
            link_de_reporte="enviado" if order.get("report_link_sent_at") else "no enviado",
        )
        lines = []
        for item in order.get("items") or []:
            price = ctx.fmt_money(item.get("unit_price"), currency)
            suffix = f" a {price} c/u" if price else ""
            lines.append(f"- {ctx.text(item.get('quantity'))} {ctx.text(item.get('name'))}{suffix}")
        reference = ctx.fmt_money(order.get("rate_unit_price"), currency)
        if reference:
            lines.append(f"precio de referencia: {reference}")
        if order.get("terms"):
            lines.append(f"condiciones acordadas: {ctx.text(order['terms'])}")
        rendered.append(f"<pedido{tag}>\n" + "\n".join(lines) + "\n</pedido>")
    return "<pedidos>\n" + "\n".join(rendered) + "\n</pedidos>"


def _render_history(history: list[dict]) -> str:
    lines = []
    for item in history:
        who = {"manager": "Gerente", "agent": "tú", "supplier": "proveedor"}.get(
            item.get("sender"), item.get("sender")
        )
        lines.append(
            f"[{ctx.fmt_datetime(item.get('sent_at'))}] {who}: {ctx.text(item.get('text'))}"
        )
    return "<historial>\n" + "\n".join(lines) + "\n</historial>"


def _render_decisions(decisions: list[dict]) -> str:
    rendered = []
    for decision in decisions:
        tag = ctx.attrs(
            tipo=DECISION_KINDS.get(decision.get("kind"), decision.get("kind")),
            resultado=DECISION_STATUSES.get(decision.get("status"), decision.get("status")),
            pedidos=", ".join(decision.get("purchase_order_codes") or []),
        )
        body = ctx.text(decision.get("summary"))
        if decision.get("note"):
            body += f"\nnota del Gerente: {ctx.text(decision['note'])}"
        rendered.append(f"<decision{tag}>\n{body}\n</decision>")
    return "<decisiones_resueltas>\n" + "\n".join(rendered) + "\n</decisiones_resueltas>"


def _render_web_reports(reports: list[dict]) -> str:
    lines = [
        f"<avance{ctx.attrs(pedido=r.get('purchase_order_code'), unidades=r.get('units_done'))}"
        f"{ctx.attrs(hora=ctx.fmt_datetime(r.get('reported_at')))}/>"
        for r in reports
    ]
    return "<avances_web>\n" + "\n".join(lines) + "\n</avances_web>"


def _render_new_messages(messages: list[dict]) -> str:
    lines = []
    for message in messages:
        tag = ctx.attrs(
            hora=ctx.fmt_time(message.get("sent_at")),
            media=ctx.media_kind(message.get("media_url")),
        )
        lines.append(f"<mensaje{tag}>{ctx.text(message.get('text'))}</mensaje>")
    return "<mensajes_nuevos>\n" + "\n".join(lines) + "\n</mensajes_nuevos>"


def _render_what_to_do(state: dict, follow_ups: list[str], new_orders: list[str]) -> str:
    steps = []
    if state.get("new_messages"):
        steps.append("Responde a lo que escribió el proveedor en <mensajes_nuevos>.")
    if state.get("decisions"):
        steps.append(
            "Comunica lo que decidió el Gerente en <decisiones_resueltas> como si la decisión "
            "fuera tuya, con tus palabras y sin copiar su nota. Si aprobó un precio o términos, "
            "cierra el pedido con confirm_purchase_order con esos datos; si los rechazó, díselo "
            "con amabilidad."
        )
    if new_orders:
        steps.append(
            "Primer contacto por los pedidos de <pedidos_nuevos>: propón el pedido con el precio "
            "de referencia y la fecha límite en un solo mensaje. No pidas cotización."
        )
    if follow_ups:
        steps.append(
            "Toca seguimiento de los pedidos de <seguimientos>: pregunta por el avance en "
            "unidades, sin insistir y según las notas del proveedor."
        )
    if state.get("web_reports"):
        steps.append(
            "Acusa recibo, en un solo mensaje corto, de los avances de <avances_web> que el "
            "proveedor reportó por la web."
        )
    steps.append(
        "Solo vale este estado: lo anterior del hilo puede estar desactualizado. "
        "Si no hay nada que decir, no envíes nada."
    )
    return "<que_hacer>\n" + "\n".join(f"- {step}" for step in steps) + "\n</que_hacer>"
