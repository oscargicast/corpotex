"""Tools of the dashboard assistant, built per user role (ADR 0017, 0020).

Reads go through the same API views the dashboard uses, as the user: same role
serializers, same permissions, nothing to keep in sync. Writes never run on the model's say-so: the first call (confirmed=false) stores a
pending action and returns a preview; the second (confirmed=true) runs only if the
previous turn proposed exactly the same arguments. A new turn needs a new message
from the user, so the model cannot confirm itself. Services re-check the role.
"""

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from asgiref.sync import sync_to_async
from claude_agent_sdk import tool

from agent.tools import ok, refuse

DECISION_ACTIONS = ("approve", "reject", "change_supplier")
READ_LIMIT = 16000  # characters of JSON per read; the full lists are 9k-12.5k
LIMA = ZoneInfo("America/Lima")


def is_alert_only(batch) -> bool:
    return bool(batch.alert_ids) and not batch.message_ids


def assistant_tools(conversation, batch) -> list:
    if is_alert_only(batch):
        return []  # an alert-only turn informs; it never acts or prepares an action (ADR 0020)
    user = conversation.user
    writes = {
        "manager": [
            _resolve_decision,
            _acknowledge_alert,
            _mark_payment_paid,
            _set_clock,
            _suggest_suppliers,
            _generate_purchase_orders,
            _request_follow_up,
            _revise_order,
        ],
        "production": [
            _confirm_order,
            _record_delivery,
            _record_progress,
            _generate_purchase_orders,
            _request_follow_up,
            _revise_order,
        ],
        # TODO(A3, after B4): sales gets find_client and register_order once their
        # endpoints exist; until then sales only reads and asks for progress.
        "sales": [_request_follow_up],
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


def api_post(user, path: str, data: dict):
    """POST to one of our API views as `user`. Returns (status_code, data)."""
    from django.urls import resolve
    from rest_framework.test import APIRequestFactory, force_authenticate

    request = APIRequestFactory().post(path, data, format="json")
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
            "Alertas abiertas que le corresponden a este usuario.",
            {},
            lambda a: get("/api/alerts/", {"mine": "1"}),
        ),
    ]
    if user.role in ("manager", "production"):
        specs.append(
            (
                "list_materials",
                (
                    "Inventario de insumos: stock, comprometido en órdenes abiertas y disponible. "
                    "Filtra por tipo o por texto en el nombre o el código."
                ),
                {"kind": {"type": "string"}, "query": {"type": "string"}},
                lambda a: get("/api/materials/", {"kind": a.get("kind"), "q": a.get("query")}),
            )
        )
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


NOT_CONFIRMED = (
    "El usuario no confirmó esto en su último mensaje, o los datos cambiaron. "
    "Vuelve a proponerlo con confirmed=false."
)


def _store_pending(conversation, name: str, args: dict, turn, data=None) -> None:
    pending = {"tool": name, "args": args, "turn_id": turn.pk}
    if data is not None:
        pending["data"] = data  # kept for the confirm step; persona only renders `args`
    _conversations(conversation).update(pending_action=pending)


def _take_pending(conversation, name: str, args: dict, turn) -> dict | None:
    """The pending action, if the previous turn proposed exactly this. Always consumes it."""
    pending = _conversations(conversation).values_list("pending_action", flat=True).get()
    _conversations(conversation).update(pending_action=None)
    if (
        pending
        and pending.get("tool") == name
        and pending.get("turn_id") != turn.pk
        and _same(pending.get("args") or {}, args)
    ):
        return pending
    return None


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


def confirmable(
    conversation,
    turn,
    user,
    *,
    name,
    description,
    properties,
    required,
    preview,
    run,
    with_data=False,
):
    """A write tool. `preview(args) -> str` and `run(args) -> action` are sync; `action` is
    the card ({title, summary, links}) that record_assistant_action stores. With `with_data`,
    `preview` returns `(text, data)` and `run(args, data)` gets exactly what was previewed."""
    from django.core.exceptions import ObjectDoesNotExist, PermissionDenied

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
        text, data = preview(args) if with_data else (preview(args), None)
        _store_pending(conversation, name, args, turn, data=data)
        return text

    def execute(args):
        from messaging.services import record_assistant_action

        pending = _take_pending(conversation, name, args, turn)
        if pending is None:
            return refuse(NOT_CONFIRMED)
        try:
            action = run(args, pending.get("data")) if with_data else run(args)
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
    from manager.models import Decision

    def preview(args):
        decision = Decision.objects.get(pk=args["decision_id"])
        verb = {"approve": "Aprobar", "reject": "Rechazar", "change_supplier": "Cambiar proveedor"}
        return f"{verb[args['action']]} la decisión {decision.pk}: {decision.summary}"

    def run(args):
        from manager.services import resolve_decision

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
    from manager.models import Alert

    def preview(args):
        return f"Marcar como vista la alerta {args['alert_id']}: {Alert.objects.get(pk=args['alert_id']).text}"

    def run(args):
        from manager.services import acknowledge_alert

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
    from operations.models import Payment

    def describe(payment):
        po = payment.purchase_order
        return f"{payment.get_kind_display()} de {po.code}: {payment.amount}"

    def preview(args):
        payment = Payment.objects.select_related("purchase_order").get(pk=args["payment_id"])
        return f"Marcar como pagado el {describe(payment)} por {args['method']}"

    def run(args):
        from operations.services import mark_payment_paid

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
        from core.clock import set_clock

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
    from operations.models import Order

    def run(args):
        from operations.services import confirm_order

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
    from operations.models import PurchaseOrder

    def describe(args):
        return (
            f"{args['qty_received']} recibidas de {args['code']}, "
            f"{args['qty_defective']} con defecto, calidad {args['quality']}/5"
        )

    def run(args):
        from operations.services import record_delivery

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
    from operations.models import PurchaseOrder

    def run(args):
        from operations.services import record_progress

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


# --- external suppliers (ADR 0024, manager only) ---------------------------------------

SUGGEST_MAX = 5
CANDIDATES_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "maxItems": SUGGEST_MAX,
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "city": {"type": "string"},
                    "kind": {"type": "string", "enum": ["workshop", "material"]},
                    "specialty": {"type": "string"},
                    "source_url": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": ["name", "city", "kind", "specialty", "source_url", "evidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["candidates"],
    "additionalProperties": False,
}


def clean_candidates(found: dict) -> list[dict]:
    """Web data is untrusted: cap every field, require an http(s) source, drop duplicates."""
    seen, out = set(), []
    for c in found.get("candidates") or []:
        url = str(c.get("source_url", "")).strip()
        name = " ".join(str(c.get("name", "")).split())[:80]
        city = " ".join(str(c.get("city", "")).split())[:40]
        key = (name.lower(), city.lower())
        if not name or not url.startswith(("http://", "https://")) or key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "name": name,
                "city": city,
                "kind": c.get("kind") if c.get("kind") in ("workshop", "material") else "workshop",
                "specialty": " ".join(str(c.get("specialty", "")).split())[:60],
                "source_url": url[:500],
                "evidence": " ".join(str(c.get("evidence", "")).split())[:300],
            }
        )
    return out[:SUGGEST_MAX]


def _domain(url: str) -> str:
    from urllib.parse import urlparse

    host = urlparse(url).netloc.lower()
    return host.removeprefix("www.")


def _suggest_suppliers(conversation, turn, user):
    """Search runs in an isolated WebSearch-only call; the assistant itself never browses.
    The model sees name, city, specialty and the source domain, never the web excerpt."""
    from agent import sdk

    name = "suggest_suppliers"
    schema = {
        "type": "object",
        "properties": {
            "specialty": {
                "type": "string",
                "description": "Ej.: costura de polos, tela algodón 30/1",
            },
            "city": {"type": "string", "enum": ["Piura", "Lima"]},
            "confirmed": {
                "type": "boolean",
                "description": "false para buscar y proponer; true solo cuando el usuario ya confirmó",
            },
        },
        "required": ["specialty", "city", "confirmed"],
    }

    def create(pending):
        from messaging.services import record_assistant_action
        from suppliers.services import create_suggested_suppliers

        result = create_suggested_suppliers(pending["data"], actor=user)
        created, skipped = len(result["created"]), len(result["skipped"])
        card = _card(f"{created} proveedores por revisar", f"{skipped} ya existían")
        record_assistant_action(conversation, turn, {"kind": "tool", "tool": name, **card})
        return ok(f"Hecho: {created} creados como por revisar, {skipped} ya existían.")

    @tool(
        name,
        "Busca en la web talleres o proveedores de insumos en Piura o Lima y, si el usuario "
        "confirma, los agrega como por revisar. No activa números ni escribe por WhatsApp.",
        schema,
    )
    async def handler(args):
        args = dict(args)
        if args.pop("confirmed", False):
            pending = await sync_to_async(_take_pending)(conversation, name, args, turn)
            if pending is None:
                return refuse(NOT_CONFIRMED)
            return await sync_to_async(create)(pending)
        prompt = (
            f"Busca proveedores o talleres de {args['specialty']} en {args['city']}, Perú. "
            f"Máximo {SUGGEST_MAX}, cada uno con la página donde aparece."
        )
        candidates = clean_candidates(await sdk.search(prompt, schema=CANDIDATES_SCHEMA))
        if not candidates:
            return ok("No encontré proveedores con una fuente verificable. Dilo así.")
        await sync_to_async(_store_pending)(conversation, name, args, turn, data=candidates)
        rows = "\n".join(
            f"- {c['name']} | {c['city']} | {c['specialty']} | {_domain(c['source_url'])}"
            for c in candidates
        )
        return ok(
            f"Encontrados:\n{rows}\nMuéstralos en una tabla corta (nombre, ciudad, especialidad, "
            "fuente) y pregunta si los agregas como por revisar, terminando en (sí/no)."
        )

    return handler


# --- consolidated material purchases (ADR 0025, manager and production) -----------------


def _pending_summary(user, material_ids: list[int]) -> str:
    """One line per material from GET /api/requirements/pending/, as the user sees it
    (the reference price only reaches the manager)."""
    params = {"material_ids": ",".join(str(i) for i in material_ids)} if material_ids else None
    status, rows = api_get(user, "/api/requirements/pending/", params)
    if status >= 400:
        raise RuntimeError(f"no se pudo leer lo pendiente (HTTP {status})")
    if material_ids:
        wanted = set(material_ids)
        rows = [r for r in rows if (r.get("material") or {}).get("id") in wanted]
    if not rows:
        raise RuntimeError("no hay requerimientos abiertos para esos insumos")
    lines = []
    for r in rows:
        m = r.get("material") or {}
        orders = ", ".join(
            f"{o.get('code', '')}: {o.get('qty', '')}" for o in r.get("orders") or []
        )
        supplier = (r.get("suggested_supplier") or {}).get("name") or "sin proveedor sugerido"
        total = r.get("total_to_order")
        line = f"{total} {m.get('unit') or ''} {m.get('name')} ({orders}) a {supplier}"
        price = r.get("reference_price")
        if price not in (None, ""):  # only the manager's serializer carries it
            cur = r.get("currency") or "S/"
            try:
                amount = Decimal(str(total)) * Decimal(str(price))
                line += f" a {cur} {price} c/u, total {cur} {amount:.2f}"
            except (InvalidOperation, TypeError):
                line += f" a {cur} {price} c/u"
        lines.append(line)
    ids = ", ".join(
        f"{(r.get('material') or {}).get('id')} {(r.get('material') or {}).get('name')}"
        f" ({(r.get('material') or {}).get('sku')})"
        for r in rows
    )
    # The ids let the model narrow a later call to one material (e.g. after a "sí"
    # to a notice that only named it).
    return "; ".join(lines) + f". ids de insumo: {ids}"


def _generate_purchase_orders(conversation, turn, user):
    def preview(args):
        return "Generar: " + _pending_summary(user, args.get("material_ids") or [])

    def run(args):
        try:
            from operations.services import generate_purchase_orders
        except ImportError as e:  # until backend's B6.1 lands
            raise RuntimeError("generar pedidos consolidados aún no está disponible") from e
        result = generate_purchase_orders(args.get("material_ids") or None, actor=user)
        created = result["created"]
        codes = [po.code for po in created]
        links = [{"kind": "purchase_order", "id": po.pk} for po in created]
        if result.get("decision"):
            links.append({"kind": "decision", "id": result["decision"].pk})
        title = f"{len(created)} pedido(s) generado(s)" + (f": {', '.join(codes)}" if codes else "")
        summary = "El Gerente aprueba la asignación en el Monitor." if created else ""
        if result.get("skipped"):
            reasons = "; ".join(s.get("reason", "") for s in result["skipped"])
            summary += f" Sin pedido para {len(result['skipped'])} insumo(s): {reasons}"
        return _card(title, summary.strip(), links)

    return confirmable(
        conversation,
        turn,
        user,
        name="generate_purchase_orders",
        description=(
            "Genera los pedidos consolidados de insumos por material a partir de los "
            "requerimientos abiertos de todas las órdenes; el Gerente aprueba después la "
            "asignación. Sin material_ids genera todos los pendientes."
        ),
        properties={
            "material_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Ids de insumos; vacío para todos los pendientes",
            }
        },
        required=[],
        preview=preview,
        run=run,
    )


# --- progress asked by a role (ADR 0027 §6, all roles) ----------------------------------


def _follow_up_path(user, args: dict) -> str:
    """`/api/<orders|purchase-orders>/<id>/follow-up/` for the code the model passed."""
    collection, code = (
        ("purchase-orders", args.get("purchase_order_code"))
        if args.get("purchase_order_code")
        else ("orders", args.get("order_code"))
    )
    if not code:
        raise ValueError("indica order_code o purchase_order_code")
    return f"/api/{collection}/{_id_for_code(user, collection, code)}/follow-up/"


def _id_for_code(user, collection: str, code: str) -> int:
    return _row_for_code(user, collection, code)["id"]


def _row_for_code(user, collection: str, code: str) -> dict:
    """The list row behind a code, read as the user (their role decides what exists for them)."""
    from django.core.exceptions import ObjectDoesNotExist, PermissionDenied

    status, rows = api_get(user, f"/api/{collection}/", {"code": code})
    if status == 403:
        raise PermissionDenied
    if status >= 400 or not rows:
        raise ObjectDoesNotExist(code)
    return rows[0]


def _follow_up_requests(user, args: dict, *, dry_run: bool) -> list[dict]:
    from django.core.exceptions import PermissionDenied

    status, data = api_post(user, _follow_up_path(user, args), {"dry_run": dry_run})
    if status == 403:
        raise PermissionDenied
    if status >= 400:
        raise RuntimeError(f"no se pudo pedir avance (HTTP {status})")
    return data.get("requests") or []


def _asked_at(value) -> str:
    moment = datetime.fromisoformat(str(value)).astimezone(LIMA) if value else None
    return f"las {moment:%H:%M}" if moment else "antes"


def _follow_up_text(requests: list[dict]) -> tuple[str, str, str]:
    """(who gets a message, who is already waiting, who cannot be asked), one phrase each."""

    def code(r):
        return (r.get("purchase_order") or {}).get("code")

    def waits(r):
        return r.get("status") == "asked" or r.get("already_asked")

    ask = ", ".join(
        f"{r.get('supplier_name')} ({code(r)})"
        for r in requests
        if r.get("status") == "pending" and not waits(r)
    )
    waiting = ", ".join(
        f"{code(r)} ({r.get('supplier_name')}) desde {_asked_at(r.get('asked_at'))}"
        for r in requests
        if waits(r)
    )
    skipped = ", ".join(
        f"{code(r)} ({r.get('supplier_name')}): {r.get('skip_reason') or 'sin canal'}"
        for r in requests
        if r.get("status") == "skipped"
    )
    return ask, waiting, skipped


def _request_follow_up(conversation, turn, user):
    def preview(args):
        requests = _follow_up_requests(user, args, dry_run=True)
        if not requests:
            raise RuntimeError("no tiene pedidos abiertos: no hay a quién pedirle avance")
        ask, waiting, skipped = _follow_up_text(requests)
        if not ask and not waiting:
            raise RuntimeError(f"no se le puede pedir avance a ninguno: {skipped}")
        parts = []
        if ask:
            parts.append(f"Pedir avance a {ask}")
        if waiting:
            parts.append(f"ya esperan respuesta, no se les escribe otra vez: {waiting}")
        if skipped:
            parts.append(f"no se les puede escribir: {skipped}")
        return "; ".join(parts) + ". La respuesta llega a este chat."

    def run(args):
        requests = _follow_up_requests(user, args, dry_run=False)
        ask, waiting, skipped = _follow_up_text(requests)
        summary = f"Le pregunto a {ask}." if ask else ""
        if waiting:
            summary += f" Ya esperaban respuesta, no se les escribió otra vez: {waiting}."
        if skipped:
            summary += f" Sin pedir: {skipped}."
        summary += " Te aviso aquí cuando contesten."
        links = [
            {"kind": "purchase_order", "id": (r.get("purchase_order") or {}).get("id")}
            for r in requests
        ]
        # The title is all the model reads back: only the orders asked now.
        title = (
            f"Avance pedido a {ask}" if ask else "Ya esperaban respuesta: no se escribió de nuevo"
        )
        return _card(title, summary.strip(), links)

    return confirmable(
        conversation,
        turn,
        user,
        name="request_follow_up",
        description=(
            "Pide avance al proveedor o taller de un pedido, o a todos los de una orden "
            "abierta. El agente le pregunta al proveedor y la respuesta llega a este chat. Los "
            "pedidos que ya esperan respuesta no se repiten."
        ),
        properties={
            "order_code": {
                "type": "string",
                "description": "Código de la orden, p. ej. CP-2026-0142",
            },
            "purchase_order_code": {
                "type": "string",
                "description": "Código del pedido, p. ej. PT-0038",
            },
        },
        required=[],
        preview=preview,
        run=run,
    )


# --- technical sheet changed by an instruction (ADR 0029 §4, manager and production) ----


def _revise(user, code: str, body: dict) -> dict:
    from django.core.exceptions import PermissionDenied

    order = _row_for_code(user, "orders", code)
    status, data = api_post(user, f"/api/orders/{order['id']}/revise/", body)
    if status == 403:
        raise PermissionDenied
    if status >= 400:
        raise RuntimeError(
            (data or {}).get("detail") or f"no se pudo ajustar la ficha técnica (HTTP {status})"
        )
    # backend may send its own fresh `current_estimated_on`; the list row is the fallback
    return {"current_estimated_on": order.get("estimated_on"), **data}


def _revise_text(data: dict) -> str:
    text = (data.get("summary") or "").strip()
    new, old = data.get("estimated_on"), data.get("current_estimated_on")
    if new and old and str(new) == str(old):
        text += f" La fecha estimada no cambia ({new})."
    elif new:
        text += (
            f" La fecha estimada pasa de {old} a {new}."
            if old
            else f" Fecha estimada con el cambio: {new}."
        )
    if data.get("warnings"):
        text += " Avisos: " + "; ".join(data["warnings"])
    return text


def _revise_order(conversation, turn, user):
    def preview(args):
        data = _revise(
            user, args["order_code"], {"instruction": args["instruction"], "dry_run": True}
        )
        return _revise_text(data), data.get("proposal")

    def run(args, proposal):
        # Applies the previewed proposal: the instruction is not interpreted a second time.
        data = _revise(
            user, args["order_code"], {"instruction": args["instruction"], "proposal": proposal}
        )
        links = [{"kind": "order", "id": (data.get("order") or {}).get("id")}]
        return _card(
            f"Ficha técnica de {args['order_code']} actualizada", _revise_text(data), links
        )

    return confirmable(
        conversation,
        turn,
        user,
        name="revise_order",
        description=(
            "Cambia la ficha técnica de una orden con una instrucción: insumos por prenda, "
            'cantidades o días de un paso ("agrega 2 botones por polo", "el corte toma 3 días"). '
            "Solo esa orden; la receta del catálogo no cambia. Los requerimientos ya pedidos no se tocan."
        ),
        properties={
            "order_code": {
                "type": "string",
                "description": "Código de la orden, p. ej. CP-2026-0142",
            },
            "instruction": {
                "type": "string",
                "description": "El cambio, en las palabras del usuario",
            },
        },
        required=["order_code", "instruction"],
        preview=preview,
        run=run,
        with_data=True,
    )
