"""ADR 0029 §4 (N2): the technical sheet edited by an instruction. Claude turns "agrega 2 botones
por polo" or "el corte toma 3 días" into a structured change (the full new recipe of each item
that changes, and the days of each plant stage that changes); Jev checks the SKUs the classifier's
way. The change lives on the order (`OrderItem.bom_override`, `Order.stage_overrides`): the
catalogue never changes. A dry run applies it inside a transaction that is rolled back, so its
estimate and warnings are the real ones."""

import logging
import re
import time
from decimal import Decimal, InvalidOperation

from django.db import transaction

from core.models import Material
from core.permissions import require_role

from . import classify, jev
from .exceptions import UnknownReference
from .models import Order, OrderItem
from .services import break_down_order, compute_critical_path, customization_stages, effective_recipe, rebreak_down_order, stage_durations

logger = logging.getLogger(__name__)

# The names the critical path gives each plant stage, so the dashboard can match them.
STAGE_LABELS = {
    "cutting": "Corte",
    "sublimation": "Sublimado",
    "embroidery": "Bordado",
    "sewing": "Costura en planta",
    "finishing": "Acabado y entrega",
}
MAX_STAGE_DAYS = 60
REVISABLE = (
    Order.Status.REGISTERED,
    Order.Status.BROKEN_DOWN,
    Order.Status.CONFIRMED,
    Order.Status.SOURCING,
    Order.Status.IN_PRODUCTION,
)

SYSTEM_PROMPT = (
    "Eres el jefe de producción de Corpotex. Ajustas la ficha técnica de una orden de confección: la receta "
    "de insumos por prenda de cada ítem y los días de cada paso en planta, según la instrucción de Producción "
    "o del Gerente. Cambias solo lo que pide la instrucción y dejas igual todo lo demás. Nunca inventas precios."
)
SCHEMA = {
    "type": "object",
    "properties": {
        "understood": {"type": "boolean"},
        "summary": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer"},
                    "materials": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "existing_sku": {"type": "string"},
                                "sku": {"type": "string"},
                                "name": {"type": "string"},
                                "kind": {"type": "string"},
                                "unit": {"type": "string"},
                                "qty_per_unit": {"type": "number"},
                            },
                            "required": ["name", "qty_per_unit"],
                        },
                    },
                },
                "required": ["item_id", "materials"],
            },
        },
        "stages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"stage": {"type": "string", "enum": list(STAGE_LABELS)}, "days": {"type": "integer", "minimum": 0}},
                "required": ["stage", "days"],
            },
        },
    },
    "required": ["understood", "summary", "items", "stages"],
}


class NotUnderstood(ValueError):
    """The instruction cannot be read or changes nothing (HTTP 400); the message is Spanish."""


class ModelFailed(RuntimeError):
    """Claude did not answer (HTTP 502)."""


def revise_order(order: Order, instruction: str | None = None, *, actor, dry_run: bool = False, proposal: dict | None = None) -> dict:
    """`POST /api/orders/<id>/revise/`. With `proposal` it is applied exactly, without Claude (it
    wins over `instruction`); otherwise Claude proposes from `instruction`. `dry_run` saves nothing.
    Returns `{proposal, summary, warnings, estimated_on, current_estimated_on}`: both dates come
    from `compute_critical_path` in the same transaction, without and with the change, so the
    difference is the change's and never a stale stored date's."""
    require_role(actor, "production", "manager")
    if order.status not in REVISABLE:
        raise UnknownReference(f"La orden {order.code} ya está en estado «{order.get_status_display()}»: su ficha técnica ya no se ajusta")
    if proposal is None:
        if not (instruction or "").strip():
            raise NotUnderstood("Escribe qué cambiar en la ficha técnica.")
        proposal, summary = propose(order, instruction.strip())
    else:
        proposal = normalize(order, proposal)
        summary = describe_changes(proposal)
    with transaction.atomic():
        current_estimated_on = compute_critical_path(order).estimated_on
        warnings = apply(order, proposal)
        estimated_on = order.estimated_on
        if dry_run:
            transaction.set_rollback(True)
    if dry_run:
        order.refresh_from_db()
    return {
        "proposal": proposal,
        "summary": summary,
        "warnings": warnings,
        "estimated_on": estimated_on,
        "current_estimated_on": current_estimated_on,
    }


# --- the current sheet --------------------------------------------------------------------


def _items(order: Order) -> list[OrderItem]:
    return list(order.items.filter(product__isnull=False).select_related("product").prefetch_related("product__materials__material").order_by("id"))


def current_recipe(item: OrderItem) -> list[dict]:
    return [
        {"material_id": m.id, "sku": m.sku, "name": m.name, "qty_per_unit": _qty(qty), "unit": m.unit}
        for m, qty in effective_recipe(item)
    ]


def _qty(value) -> str:
    """`0.30` → "0.3", `3.00` → "3": the same number reads the same in the current and the proposal."""
    text = format(Decimal(str(value)).normalize(), "f")
    return text


def _stages_in_use(order: Order) -> list[str]:
    return ["cutting", *sorted(customization_stages(order)), "sewing", "finishing"]


# --- proposing ----------------------------------------------------------------------------


def propose(order: Order, instruction: str) -> tuple[dict, str]:
    items = _items(order)
    if not items:
        raise NotUnderstood("La orden no tiene prendas con producto: clasifícalas antes de ajustar la ficha técnica.")
    durations = stage_durations(order)
    materials = list(Material.objects.order_by("sku"))
    customer = order.customer.name if order.customer_id else "sin cliente"
    state = f"Orden {order.code} de {customer}, marca {order.brand.name}"
    lines = [f"{state}.", "", "Ítems de la ficha técnica (receta por prenda):"]
    for item in items:
        lines.append(f"- ítem {item.id}: {item.quantity} × {item.product.code} {item.product.name}" + (f" ({item.description})" if item.description else ""))
        for m in current_recipe(item):
            lines.append(f"    · {m['sku']} {m['name']}: {m['qty_per_unit']} {m['unit']}")
    lines += ["", "Pasos en planta (días):"]
    for stage in _stages_in_use(order):
        note = " (solo cuenta si se cose en planta)" if stage == "sewing" else ""
        lines.append(f"- {stage} ({STAGE_LABELS[stage]}): {int(durations.get(stage, 3 if stage == 'sewing' else 1))}{note}")
    lines += ["", "Insumos del inventario (SKU: nombre, tipo, unidad):"]
    lines += [f"- {m.sku}: {m.name}, {m.kind}, {m.unit}" for m in materials]
    lines += [
        "",
        f"Instrucción: {instruction}",
        "",
        "Devuelve en items solo los ítems cuya receta cambia, cada uno con su receta COMPLETA nueva: los insumos que "
        "siguen igual (con existing_sku y su cantidad), los que cambian y los nuevos (sku, nombre, tipo y unidad; "
        "existing_sku cuando un insumo del inventario sirve). Un insumo que se quita no va en la lista. "
        "Cantidades por prenda, en la unidad del insumo. En stages solo los pasos cuyos días cambian. "
        "summary: una o dos frases en español con lo que cambia, nombrando cada prenda por su producto "
        "(\"en los polos escolares\"), nunca por el número de ítem. Si la instrucción no se entiende o no cambia "
        "nada, understood=false y summary dice por qué.",
    ]
    started = time.monotonic()
    try:
        answer = classify.complete_sync("\n".join(lines), schema=SCHEMA, system_prompt=SYSTEM_PROMPT)
    except Exception as exc:
        logger.exception("revise_order %s: the model failed", order.code)
        raise ModelFailed("No se pudo preparar el ajuste. Prueba de nuevo en un momento.") from exc
    claude_seconds = time.monotonic() - started
    summary = readable(answer.get("summary") or "", items)
    if not answer.get("understood"):
        raise NotUnderstood(summary or "No entendí qué cambiar en la ficha técnica.")

    by_id = {item.id: item for item in items}
    budget = jev.Budget()
    timings: dict[str, float] = {}
    proposed_items = []
    for entry in answer.get("items") or []:
        item = by_id.get(entry.get("item_id"))
        if item is None:
            continue
        resolved = classify.resolve_materials(f"{state}: {item.product.name}", entry.get("materials") or [], materials, base=0.8, timings=timings, budget=budget)
        proposed_items.append({"item_id": item.id, "materials": [_clean(m) for m in resolved]})
    stages = {s["stage"]: s["days"] for s in answer.get("stages") or [] if s.get("stage") in STAGE_LABELS}
    proposal = normalize(order, {"items": proposed_items, "stage_overrides": stages})
    logger.info("revise_order %s: claude=%.2fs jev=%.2fs", order.code, claude_seconds, timings.get("jev_materials", 0.0))
    return proposal, summary or describe_changes(proposal)


ITEM_REF = re.compile(r"\b(?:(en|de|del|para) )?(?:el |los )?[íi]tems? (?:n\.?º ?|#)?(\d+)\b", re.IGNORECASE)


def readable(summary: str, items: list[OrderItem]) -> str:
    """The person reads the garment, never an internal id: "en el ítem 394" becomes "en Polo
    escolar UNICRACK" when the model slips (agente, 11/10 04:00)."""
    names = {str(item.id): item.product.name for item in items}

    def name(match):
        product = names.get(match.group(2))
        if product is None:
            return match.group(0)
        return f"{match.group(1)} {product}" if match.group(1) else product

    return ITEM_REF.sub(name, summary.strip())


def _clean(material: dict) -> dict:
    out = {k: v for k, v in material.items() if k != "confidence"}
    out["qty_per_unit"] = _qty(material.get("qty_per_unit") or 0)
    return out


# --- checking a proposal --------------------------------------------------------------------


def normalize(order: Order, proposal: dict) -> dict:
    """Checks every reference and keeps only what really changes, with the current recipe and the
    current days beside it (the dashboard's diff). Raises `UnknownReference` or `NotUnderstood`."""
    by_id = {item.id: item for item in _items(order)}
    durations = stage_durations(order)
    items = []
    for entry in proposal.get("items") or []:
        try:
            item = by_id.get(int(entry.get("item_id")))
        except (TypeError, ValueError):
            item = None
        if item is None:
            raise UnknownReference(f"El ítem {entry.get('item_id')} no es de la orden {order.code} o no tiene producto")
        materials = []
        for m in entry.get("materials") or []:
            materials.append(_material_entry(m))
        merged: dict = {}
        for m in materials:  # the same material twice is one line, quantities added
            key = m.get("material_id") or ("new", m["new"]["sku"])
            if key in merged:
                merged[key]["qty_per_unit"] = _qty(Decimal(merged[key]["qty_per_unit"]) + Decimal(m["qty_per_unit"]))
            else:
                merged[key] = m
        materials = [m for m in merged.values() if Decimal(m["qty_per_unit"]) > 0]
        current = current_recipe(item)
        if _recipe_key(materials) == _recipe_key(current):
            continue
        items.append({
            "item_id": item.id,
            "product": {"code": item.product.code, "name": item.product.name},
            "quantity": item.quantity,
            "current": current,
            "materials": materials,
        })
    stages = {}
    for stage, days in (proposal.get("stage_overrides") or {}).items():
        if stage not in STAGE_LABELS:
            raise UnknownReference(f"El paso {stage} no existe; los pasos son {', '.join(STAGE_LABELS)}")
        try:
            days = int(days)
        except (TypeError, ValueError):
            raise UnknownReference(f"Los días de {STAGE_LABELS[stage]} tienen que ser un número entero")
        if not 0 <= days <= MAX_STAGE_DAYS:
            raise UnknownReference(f"Los días de {STAGE_LABELS[stage]} van de 0 a {MAX_STAGE_DAYS}")
        current_days = int(durations.get(stage, 3 if stage == "sewing" else 1))
        if days != current_days:
            stages[stage] = days
    if not items and not stages:
        raise NotUnderstood("La instrucción no cambia la ficha técnica.")
    return {
        "items": items,
        "stage_overrides": stages,
        "stage_current": {stage: int(durations.get(stage, 3 if stage == "sewing" else 1)) for stage in stages},
        "stage_labels": {stage: STAGE_LABELS[stage] for stage in stages},
    }


def _material_entry(m: dict) -> dict:
    try:
        qty = Decimal(str(m.get("qty_per_unit")))
    except (InvalidOperation, TypeError, ValueError):
        raise UnknownReference(f"La cantidad por prenda de {m.get('name') or m.get('sku') or 'un insumo'} no es un número")
    if qty < 0:
        raise UnknownReference("Una cantidad por prenda no puede ser negativa")
    material = None
    if m.get("material_id"):
        material = Material.objects.filter(pk=m["material_id"]).first()
        if material is None:
            raise UnknownReference(f"El insumo {m['material_id']} no existe")
    elif m.get("sku") and not m.get("new"):
        material = Material.objects.filter(sku__iexact=str(m["sku"]).strip()).first()
        if material is None:
            raise UnknownReference(f"El insumo {m['sku']} no existe")
    if material is not None:
        return {"material_id": material.id, "sku": material.sku, "name": material.name, "qty_per_unit": _qty(qty), "unit": material.unit}
    new = m.get("new") or {}
    if not (new.get("name") or "").strip():
        raise UnknownReference("Un insumo nuevo necesita nombre")
    sku = (new.get("sku") or "").strip().upper() or classify._slug_code("", "MAT", new["name"])
    known = Material.objects.filter(sku=sku).first()
    if known is not None:  # a "new" one already created by an earlier revision or classification
        return {"material_id": known.id, "sku": known.sku, "name": known.name, "qty_per_unit": _qty(qty), "unit": known.unit}
    kind = new.get("kind") if new.get("kind") in classify.KINDS else "other"
    unit = new.get("unit") if new.get("unit") in classify.UNITS else "unit"
    return {"new": {"sku": sku, "name": new["name"].strip()[:160], "kind": kind, "unit": unit}, "qty_per_unit": _qty(qty), "unit": unit}


def _recipe_key(lines: list[dict]) -> dict:
    return {(m.get("material_id") or ("new", m["new"]["sku"])): Decimal(str(m["qty_per_unit"])) for m in lines}


def describe_changes(proposal: dict) -> str:
    """The summary when no model wrote one (a proposal applied as is): what enters, leaves or
    changes per garment, and the days per step."""
    parts = []
    for item in proposal["items"]:
        before = {(m.get("material_id") or ("new", m.get("sku"))): m for m in item["current"]}
        after = {(m.get("material_id") or ("new", m["new"]["sku"])): m for m in item["materials"]}
        changes = []
        for key, m in after.items():
            name = m.get("name") or m["new"]["name"]
            if key not in before:
                changes.append(f"entra {name} {m['qty_per_unit']} {m['unit']}")
            elif Decimal(before[key]["qty_per_unit"]) != Decimal(m["qty_per_unit"]):
                changes.append(f"{name} {before[key]['qty_per_unit']} → {m['qty_per_unit']} {m['unit']}")
        changes += [f"sale {m['name']}" for key, m in before.items() if key not in after]
        if changes:
            parts.append(f"{item['product']['name']}: " + ", ".join(changes) + " por prenda")
    for stage, days in proposal["stage_overrides"].items():
        parts.append(f"{STAGE_LABELS[stage]}: {proposal['stage_current'][stage]} → {days} días")
    return "; ".join(parts) + "."


# --- applying -----------------------------------------------------------------------------


def apply(order: Order, proposal: dict) -> list[str]:
    """Saves the overrides (new materials enter the inventory with stock 0), breaks the order
    down again without touching what is already ordered, and recalculates the critical path."""
    for entry in proposal["items"]:
        item = OrderItem.objects.get(pk=entry["item_id"], order=order)
        bom = []
        for m in entry["materials"]:
            material = Material.objects.get(pk=m["material_id"]) if m.get("material_id") else classify._material_for(m)
            bom.append({"material_id": material.id, "qty_per_unit": m["qty_per_unit"]})
        item.bom_override = bom
        item.save(update_fields=["bom_override", "updated_at"])
    if proposal["stage_overrides"]:
        order.stage_overrides = {**(order.stage_overrides or {}), **proposal["stage_overrides"]}
        order.save(update_fields=["stage_overrides", "updated_at"])
    if order.status == Order.Status.REGISTERED:
        break_down_order(order)  # it also computes the critical path
        return []
    warnings = rebreak_down_order(order)
    compute_critical_path(order)
    return warnings
