"""Tools of the dashboard assistant, built per user role (ADR 0017, 0020).

Reads go through the same API views the dashboard uses, as the user: same role
serializers, same permissions, nothing to keep in sync. Writes never run on the model's say-so: the first call (confirmed=false) stores a
pending action and returns a preview; the second (confirmed=true) runs only if the
previous turn proposed exactly the same arguments. A new turn needs a new message
from the user, so the model cannot confirm itself. Services re-check the role.
"""

import json

from asgiref.sync import sync_to_async
from claude_agent_sdk import tool

from agent.tools import ok, refuse

DECISION_ACTIONS = ("approve", "reject", "change_supplier")
READ_LIMIT = 8000  # characters of JSON the model reads per call


def is_alert_only(batch) -> bool:
    return bool(batch.alert_ids) and not batch.message_ids


def assistant_tools(conversation, batch) -> list:
    if is_alert_only(batch):
        return []  # an alert-only turn informs; it never acts or prepares an action (ADR 0020)
    user = conversation.user
    writes = {
        "manager": [_resolve_decision, _acknowledge_alert, _mark_payment_paid, _set_clock],
        "production": [_confirm_order, _record_delivery, _record_progress],
        # TODO(A3, after B4): sales gets find_client and register_order once their
        # endpoints exist; until then sales only reads.
    }.get(user.role, [])
    return _reads(user) + [build(conversation, batch.turn, user) for build in writes]


# --- reads ------------------------------------------------------------------------------


def api_get(user, path: str, params: dict | None = None):
    """GET one of our API views as `user`. Returns (status_code, data)."""
    from django.urls import resolve
    from rest_framework.test import APIRequestFactory, force_authenticate

    query = {k: v for k, v in (params or {}).items() if v not in (None, "")}
    request = APIRequestFactory().get(path, query)
    force_authenticate(request, user=user)
    match = resolve(path)
    response = match.func(request, *match.args, **match.kwargs)
    return response.status_code, response.data


def _reads(user) -> list:
    def answer(status: int, data) -> dict:
        if status == 403:
            return refuse("Tu rol no ve eso.")
        if status >= 400:
            return refuse(f"No se pudo leer (HTTP {status}).")
        text = json.dumps(data, ensure_ascii=False, default=str)
        if len(text) > READ_LIMIT:
            text = text[:READ_LIMIT] + " …(recortado: filtra más)"
        return ok(text)

    def get(path, params=None):
        return answer(*api_get(user, path, params))

    def by_code(collection: str, code: str):
        status, rows = api_get(user, f"/api/{collection}/", {"code": code})
        if status >= 400 or not rows:
            return refuse(f"No existe {code}.") if status < 400 else answer(status, rows)
        return get(f"/api/{collection}/{rows[0]['id']}/")

    def purchase_orders(args):
        params = {"status": args.get("status")}
        if args.get("order_code"):
            status, rows = api_get(user, "/api/orders/", {"code": args["order_code"]})
            if status >= 400 or not rows:
                return refuse(f"No existe {args['order_code']}.")
            params["order"] = rows[0]["id"]
        if args.get("waiting_manager"):
            params["waiting_manager"] = 1
        return get("/api/purchase-orders/", params)

    def monitor_part(*keys):
        def read(args):
            status, data = api_get(user, "/api/monitor/")
            return answer(status, {k: data.get(k) for k in keys} if status < 400 else data)

        return read

    specs = [
        (
            "list_orders",
            "Lista órdenes de clientes con estado, fecha estimada y riesgo.",
            {"status": {"type": "string"}, "risk": {"type": "string"}},
            lambda a: get("/api/orders/", {"status": a.get("status"), "risk": a.get("risk")}),
        ),
        (
            "get_order",
            "Detalle de una orden por su código: ítems, fechas, riesgo y ruta crítica.",
            {"code": {"type": "string"}},
            lambda a: by_code("orders", a["code"]),
        ),
        (
            "list_purchase_orders",
            "Lista pedidos a proveedores y talleres: proveedor, estado, fechas y avance.",
            {
                "order_code": {"type": "string"},
                "status": {"type": "string"},
                "waiting_manager": {"type": "boolean"},
            },
            purchase_orders,
        ),
        (
            "get_purchase_order",
            "Detalle de un pedido por su código: ítems, fechas, avance y entregas.",
            {"code": {"type": "string"}},
            lambda a: by_code("purchase-orders", a["code"]),
        ),
        (
            "list_alerts",
            "Alertas abiertas que ve este usuario.",
            {},
            monitor_part("alerts"),
        ),
    ]
    if user.role == "manager":
        specs += [
            (
                "list_pending",
                "Pendientes del Gerente: decisiones por tomar, órdenes en peligro y alertas.",
                {},
                monitor_part("decisions", "orders_in_danger", "alerts"),
            ),
            (
                "list_suppliers",
                "Proveedores y talleres con números, tarifas y puntajes.",
                {"kind": {"type": "string"}, "status": {"type": "string"}},
                lambda a: get(
                    "/api/suppliers/", {"kind": a.get("kind"), "status": a.get("status")}
                ),
            ),
            (
                "get_supplier",
                "Detalle de un proveedor por su id.",
                {"supplier_id": {"type": "integer"}},
                lambda a: get(f"/api/suppliers/{int(a['supplier_id'])}/"),
            ),
        ]
    return [
        _read_tool(name, description, properties, run)
        for name, description, properties, run in specs
    ]


def _read_tool(name, description, properties, run):
    required = [k for k in ("code", "supplier_id") if k in properties]
    schema = {"type": "object", "properties": properties, "required": required}

    @tool(name, description, schema)
    async def handler(args):
        return await sync_to_async(run)(dict(args))

    return handler


# --- pending action -----------------------------------------------------------------


def _conversations(conversation):
    return type(conversation).objects.filter(pk=conversation.pk)


def _same(a: dict, b: dict) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def clear_stale_pending_action(conversation, turn_id: int) -> None:
    """End of a dashboard turn: a pending action is only valid for the next turn."""
    pending = _conversations(conversation).values_list("pending_action", flat=True).get()
    if pending and pending.get("turn_id") != turn_id:
        _conversations(conversation).update(pending_action=None)


def finish_dashboard_turn(conversation, batch, result) -> None:
    """The assistant answers with its final text; an alert-only turn becomes an alert card."""
    from messaging.services import post_assistant_message

    clear_stale_pending_action(conversation, batch.turn.pk)
    if result.error or not result.text.strip():
        return
    action = {"kind": "alert", "alert_ids": list(batch.alert_ids)} if is_alert_only(batch) else None
    post_assistant_message(conversation, batch.turn, result.text.strip(), action=action)


def confirmable(conversation, turn, user, *, name, description, properties, required, preview, run):
    """A write tool. `preview(args) -> str` and `run(args) -> action` are sync; `action` is
    the card ({title, summary, links}) that record_assistant_action stores."""
    from django.core.exceptions import ObjectDoesNotExist, PermissionDenied

    from messaging.services import record_assistant_action

    schema = {
        "type": "object",
        "properties": {
            **properties,
            "confirmed": {
                "type": "boolean",
                "description": "false para proponer; true solo cuando el usuario ya confirmó",
            },
        },
        "required": [*required, "confirmed"],
    }

    def propose(args):
        text = preview(args)
        pending = {"tool": name, "args": args, "turn_id": turn.pk}
        _conversations(conversation).update(pending_action=pending)
        return text

    def execute(args):
        pending = _conversations(conversation).values_list("pending_action", flat=True).get()
        _conversations(conversation).update(pending_action=None)
        valid = (
            pending
            and pending.get("tool") == name
            and pending.get("turn_id") != turn.pk
            and _same(pending.get("args") or {}, args)
        )
        if not valid:
            return refuse(
                "El usuario no confirmó esto en su último mensaje, o los datos cambiaron. "
                "Vuelve a proponerlo con confirmed=false."
            )
        try:
            action = run(args)
        except PermissionDenied:
            return refuse("Tu rol no puede hacer eso.")
        except Exception as e:  # noqa: BLE001 - a domain refusal (e.g. already resolved) goes on the card
            failed = _card(f"No se pudo: {name}", str(e)[:300], status="failed")
            record_assistant_action(conversation, turn, {"kind": "tool", "tool": name, **failed})
            return refuse(f"No se pudo: {e}")
        record_assistant_action(conversation, turn, {"kind": "tool", "tool": name, **action})
        return ok(f"Hecho: {action['title']}. El dashboard muestra la tarjeta.")

    @tool(name, description, schema)
    async def handler(args):
        args = dict(args)
        confirmed = args.pop("confirmed", False)
        try:
            if confirmed:
                return await sync_to_async(execute)(args)
            text = await sync_to_async(propose)(args)
        except ObjectDoesNotExist:
            return refuse("No existe. Revisa el id o el código.")
        except PermissionDenied:
            return refuse("Tu rol no puede hacer eso.")
        return ok(
            f"Vista previa: {text}\nResúmelo al usuario en una línea que termine en (sí/no) y "
            "espera su respuesta."
        )

    return handler


def _card(title: str, summary: str = "", links=(), status: str = "done") -> dict:
    return {"status": status, "title": title, "summary": summary, "links": list(links)}


# --- manager --------------------------------------------------------------------------


def _resolve_decision(conversation, turn, user):
    from manager.services import resolve_decision

    from manager.models import Decision

    def preview(args):
        decision = Decision.objects.get(pk=args["decision_id"])
        verb = {"approve": "Aprobar", "reject": "Rechazar", "change_supplier": "Cambiar proveedor"}
        return f"{verb[args['action']]} la decisión {decision.pk}: {decision.summary}"

    def run(args):
        decision = Decision.objects.get(pk=args["decision_id"])
        resolve_decision(
            decision,
            action=args["action"],
            supplier_id=args.get("supplier_id"),
            note=args.get("note", ""),
            actor=user,
        )
        title = f"Decisión {decision.pk}: {args['action']}"
        return _card(title, decision.summary, [{"kind": "decision", "id": decision.pk}])

    return confirmable(
        conversation,
        turn,
        user,
        name="resolve_decision",
        description="Aprueba, rechaza o cambia el proveedor de una decisión pendiente.",
        properties={
            "decision_id": {"type": "integer"},
            "action": {"type": "string", "enum": list(DECISION_ACTIONS)},
            "supplier_id": {"type": "integer", "description": "Solo para change_supplier"},
            "note": {"type": "string"},
        },
        required=["decision_id", "action"],
        preview=preview,
        run=run,
    )


def _acknowledge_alert(conversation, turn, user):
    from manager.services import acknowledge_alert

    from manager.models import Alert

    def preview(args):
        return f"Marcar como vista la alerta {args['alert_id']}: {Alert.objects.get(pk=args['alert_id']).text}"

    def run(args):
        alert = Alert.objects.get(pk=args["alert_id"])
        acknowledge_alert(alert, actor=user)
        return _card(f"Alerta {alert.pk} vista", alert.text)

    return confirmable(
        conversation,
        turn,
        user,
        name="acknowledge_alert",
        description="Marca una alerta como vista.",
        properties={"alert_id": {"type": "integer"}},
        required=["alert_id"],
        preview=preview,
        run=run,
    )


def _mark_payment_paid(conversation, turn, user):
    from operations.services import mark_payment_paid

    from operations.models import Payment

    def describe(payment):
        po = payment.purchase_order
        return f"{payment.get_kind_display()} de {po.code}: {payment.amount}"

    def preview(args):
        payment = Payment.objects.select_related("purchase_order").get(pk=args["payment_id"])
        return f"Marcar como pagado el {describe(payment)} por {args['method']}"

    def run(args):
        payment = Payment.objects.select_related("purchase_order").get(pk=args["payment_id"])
        mark_payment_paid(payment, method=args["method"], actor=user)
        links = [{"kind": "purchase_order", "id": payment.purchase_order_id}]
        return _card(f"Pagado: {describe(payment)}", args["method"], links)

    return confirmable(
        conversation,
        turn,
        user,
        name="mark_payment_paid",
        description="Registra un pago (adelanto o saldo) como pagado.",
        properties={
            "payment_id": {"type": "integer"},
            "method": {"type": "string", "enum": ["yape", "transfer", "cash"]},
        },
        required=["payment_id", "method"],
        preview=preview,
        run=run,
    )


def _set_clock(conversation, turn, user):
    from core.clock import set_clock

    def describe(args):
        parts = []
        if args.get("advance_hours"):
            parts.append(f"adelantar {args['advance_hours']} h")
        if args.get("factor"):
            parts.append(f"velocidad x{args['factor']}")
        if "paused" in args:
            parts.append("pausar" if args["paused"] else "reanudar")
        return ", ".join(parts) or "sin cambios"

    def run(args):
        set_clock(
            factor=args.get("factor"),
            paused=args.get("paused"),
            advance_hours=args.get("advance_hours"),
            actor=user,
        )
        return _card(f"Reloj: {describe(args)}")

    return confirmable(
        conversation,
        turn,
        user,
        name="set_clock",
        description="Adelanta, pausa o cambia la velocidad del reloj de la demo.",
        properties={
            "advance_hours": {"type": "number", "exclusiveMinimum": 0},
            "factor": {"type": "number", "exclusiveMinimum": 0},
            "paused": {"type": "boolean"},
        },
        required=[],
        preview=lambda args: f"Reloj: {describe(args)}",
        run=run,
    )


# --- production -----------------------------------------------------------------------


def _confirm_order(conversation, turn, user):
    from operations.services import confirm_order

    from operations.models import Order

    def run(args):
        order = Order.objects.get(code=args["code"])
        confirm_order(order, actor=user)
        return _card(
            f"Desglose de {order.code} confirmado", links=[{"kind": "order", "id": order.pk}]
        )

    return confirmable(
        conversation,
        turn,
        user,
        name="confirm_order",
        description="Confirma el desglose de una orden.",
        properties={"code": {"type": "string"}},
        required=["code"],
        preview=lambda args: (
            f"Confirmar el desglose de {Order.objects.get(code=args['code']).code}"
        ),
        run=run,
    )


def _record_delivery(conversation, turn, user):
    from operations.services import record_delivery

    from operations.models import PurchaseOrder

    def describe(args):
        return (
            f"{args['qty_received']} recibidas de {args['code']}, "
            f"{args['qty_defective']} con defecto, calidad {args['quality']}/5"
        )

    def run(args):
        po = PurchaseOrder.objects.get(code=args["code"])
        record_delivery(
            po,
            qty_received=args["qty_received"],
            qty_defective=args["qty_defective"],
            quality=args["quality"],
            note=args.get("note", ""),
            actor=user,
        )
        return _card(f"Entrega: {describe(args)}", links=[{"kind": "purchase_order", "id": po.pk}])

    def preview(args):
        PurchaseOrder.objects.get(code=args["code"])
        return f"Registrar entrega: {describe(args)}"

    return confirmable(
        conversation,
        turn,
        user,
        name="record_delivery",
        description="Registra una entrega recibida: cantidad, defectuosas y calidad de 1 a 5.",
        properties={
            "code": {"type": "string"},
            "qty_received": {"type": "number", "minimum": 0},
            "qty_defective": {"type": "number", "minimum": 0},
            "quality": {"type": "integer", "minimum": 1, "maximum": 5},
            "note": {"type": "string"},
        },
        required=["code", "qty_received", "qty_defective", "quality"],
        preview=preview,
        run=run,
    )


def _record_progress(conversation, turn, user):
    from operations.services import record_progress

    from operations.models import PurchaseOrder

    def run(args):
        po = PurchaseOrder.objects.get(code=args["code"])
        record_progress(po, units_done=args["units_done"], note=args.get("note", ""), actor=user)
        title = f"Avance de {po.code}: {args['units_done']} unidades"
        return _card(title, links=[{"kind": "purchase_order", "id": po.pk}])

    def preview(args):
        PurchaseOrder.objects.get(code=args["code"])
        return f"Registrar avance de {args['code']}: {args['units_done']} unidades"

    return confirmable(
        conversation,
        turn,
        user,
        name="record_progress",
        description="Registra el avance de un pedido en unidades terminadas.",
        properties={
            "code": {"type": "string"},
            "units_done": {"type": "integer", "minimum": 0},
            "note": {"type": "string"},
        },
        required=["code", "units_done"],
        preview=preview,
        run=run,
    )
