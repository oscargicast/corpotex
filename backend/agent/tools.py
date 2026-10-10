"""Tools of the WhatsApp agent, bound to the conversation of the turn (ADR 0010, 0024).

The model never sees phone numbers or report tokens and can only touch purchase
orders of this conversation's supplier. Boss rules live in the services: when
they refuse, the tool tells the model to escalate. What the model reads is Spanish.
"""

from datetime import date
from decimal import Decimal

from asgiref.sync import sync_to_async
from claude_agent_sdk import tool

from agent import channels

INTRO_MAX = 200
# Neutral on purpose (no tú/usted): used when the model's intro is missing or unsafe.
REPORT_LINK_FALLBACK = "Para reportar avance y fotos del pedido {code}:\n{url}"


def ok(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def refuse(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}], "is_error": True}


def whatsapp_tools(conversation, batch) -> list:
    from django.core.exceptions import ObjectDoesNotExist
    from manager.services import create_decision
    from messaging.exceptions import ForeignPurchaseOrder, NumberNotAllowed, SendFailed
    from messaging.services import latest_photo_id, message_history, purchase_order_for_conversation
    from operations.exceptions import ManagerApprovalRequired
    from operations.services import (
        cancel_by_supplier,
        confirm_purchase_order,
        mark_report_link_sent,
        record_progress,
        report_url,
    )

    turn = batch.turn

    @sync_to_async
    def order(code: str):
        return purchase_order_for_conversation(conversation, code)

    async def guarded(action, code: str):
        """Run `action(po)` on this supplier's order, turning domain refusals into text."""
        try:
            return await action(await order(code))
        except ForeignPurchaseOrder:
            return refuse(f"El pedido {code} no es de este proveedor. No lo menciones.")
        except ObjectDoesNotExist:
            return refuse(f"No existe el pedido {code}. Revisa el código en <pedidos>.")

    @tool(
        "send_message",
        "Envía un mensaje de WhatsApp a este proveedor. Es lo único que el proveedor lee.",
        {
            "type": "object",
            "properties": {"text": {"type": "string", "minLength": 1}},
            "required": ["text"],
        },
    )
    async def send_message(args):
        try:
            await sync_to_async(channels.send)(conversation, args["text"], turn)
        except NumberNotAllowed:
            return refuse("Este número ya no está habilitado. No envíes nada más en este turno.")
        except SendFailed:
            return refuse("WhatsApp no aceptó el mensaje. No lo reintentes en este turno.")
        return ok("Enviado.")

    @tool(
        "confirm_purchase_order",
        "Cierra un pedido con el precio unitario, la fecha comprometida y los términos acordados. "
        "Si pasan la tarifa o la fecha límite, se rechaza y debes escalar al Gerente.",
        {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "unit_price": {"type": "number", "exclusiveMinimum": 0},
                "committed_on": {"type": "string", "format": "date", "description": "AAAA-MM-DD"},
                "terms": {"type": "string", "description": "Términos acordados, en una línea"},
            },
            "required": ["code", "unit_price", "committed_on", "terms"],
        },
    )
    async def confirm_purchase_order_tool(args):
        @sync_to_async
        def confirm(po):
            try:
                confirm_purchase_order(
                    po,
                    unit_price=Decimal(str(args["unit_price"])),
                    committed_on=date.fromisoformat(args["committed_on"]),
                    terms=args["terms"],
                )
            except ManagerApprovalRequired as e:
                return refuse(
                    f"No se puede cerrar solo: {e}. Usa escalate_to_manager y dile al "
                    "proveedor que lo revisas y le confirmas. No prometas nada."
                )
            return ok(f"Pedido {po.code} confirmado.")

        return await guarded(confirm, args["code"])

    @tool(
        "record_progress",
        "Registra el avance que reporta el proveedor: unidades terminadas del pedido. "
        "Si mandó una foto en este turno, queda adjunta.",
        {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "units_done": {"type": "integer", "minimum": 0},
                "note": {"type": "string"},
            },
            "required": ["code", "units_done"],
        },
    )
    async def record_progress_tool(args):
        @sync_to_async
        def record(po):
            record_progress(
                po,
                units_done=args["units_done"],
                note=args.get("note", ""),
                message_id=latest_photo_id(batch.message_ids),
                actor=None,
            )
            return ok(f"Avance de {po.code} registrado.")

        return await guarded(record, args["code"])

    @tool(
        "report_cancellation",
        "Registra que el proveedor no puede seguir con un pedido. El sistema redistribuye lo que "
        "falta y el Gerente aprueba. No le prometas nada al proveedor.",
        {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "reason": {"type": "string"},
                "units_done": {"type": "integer", "minimum": 0},
            },
            "required": ["code", "reason"],
        },
    )
    async def report_cancellation(args):
        @sync_to_async
        def cancel(po):
            cancel_by_supplier(po, reason=args["reason"], units_done=args.get("units_done"))
            return ok(f"Cancelación de {po.code} registrada. El Gerente decide la redistribución.")

        return await guarded(cancel, args["code"])

    @tool(
        "escalate_to_manager",
        "Deja una decisión pendiente para el Gerente: precio, términos u otro (por ejemplo, si "
        "preguntan en serio si eres un bot). Tú no decides eso.",
        {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["price", "terms", "other"]},
                "codes": {"type": "array", "items": {"type": "string"}},
                "summary": {"type": "string", "description": "Lo que lee el Gerente, una línea"},
                "detail": {"type": "string", "description": "Qué pide el proveedor y qué había"},
            },
            "required": ["kind", "codes", "summary"],
        },
    )
    async def escalate_to_manager(args):
        @sync_to_async
        def escalate():
            orders = [purchase_order_for_conversation(conversation, c) for c in args["codes"]]
            create_decision(
                kind=args["kind"],
                purchase_orders=orders,
                summary=args["summary"],
                detail={"agent_note": args.get("detail", "")},
                conversation=conversation,
            )

        try:
            await escalate()
        except ForeignPurchaseOrder:
            return refuse("Uno de los pedidos no es de este proveedor.")
        except ObjectDoesNotExist:
            return refuse("Uno de los códigos no existe. Revisa <pedidos>.")
        return ok("Decisión creada; el Gerente fue avisado.")

    @tool(
        "read_history",
        "Lee los últimos mensajes de este chat, por si necesitas contexto que no tienes.",
        {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}},
        },
    )
    async def read_history(args):
        rows = await sync_to_async(message_history)(conversation, args.get("limit", 20))
        lines = [f"[{m.sent_at:%d/%m %H:%M}] {m.author}: {m.text}" for m in rows]
        return ok("\n".join(lines) or "No hay mensajes.")

    @tool(
        "send_report_link",
        "Envía al taller el link para reportar avance con fotos desde el celular, una sola vez "
        "por pedido. Escribe solo la frase de introducción, sin URL: el link lo agrega el sistema.",
        {
            "type": "object",
            "properties": {"code": {"type": "string"}, "intro": {"type": "string"}},
            "required": ["code"],
        },
    )
    async def send_report_link(args):
        intro = " ".join(args.get("intro", "").split())

        @sync_to_async
        def send(po):
            url = report_url(po)
            use_intro = (
                intro and len(intro) <= INTRO_MAX and "http" not in intro and "www." not in intro
            )
            text = (
                f"{intro}\n{url}"
                if use_intro
                else REPORT_LINK_FALLBACK.format(code=po.code, url=url)
            )
            channels.send(conversation, text, turn)
            mark_report_link_sent(po)
            return ok(f"Link de {po.code} enviado.")

        try:
            return await guarded(send, args["code"])
        except (NumberNotAllowed, SendFailed):
            return refuse("No se pudo enviar el link en este turno.")

    return [
        send_message,
        confirm_purchase_order_tool,
        record_progress_tool,
        report_cancellation,
        escalate_to_manager,
        read_history,
        send_report_link,
    ]
