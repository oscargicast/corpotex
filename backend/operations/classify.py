"""Classification of made-to-order items (ADR 0025 C, B6.4): for each item without a catalogue
product, propose the product (existing or new) and its bill of materials (existing SKUs or new
materials), with a confidence per answer. Jev picks among known options when it is on; Claude
proposes new products and materials (or everything, when Jev is off). Production reviews the
proposal and `apply_classification` writes it."""

import asyncio
import logging
import re
from decimal import Decimal

from django.conf import settings
from django.db import transaction

from core.models import Brand, Material, Product, ProductMaterial
from core.permissions import require_role

from . import jev
from .models import Order, OrderItem

logger = logging.getLogger(__name__)

MIN_CONFIDENCE = 0.6
FALLBACK_CONFIDENCE = 0.5  # What a Claude answer is worth when nobody scored it.
KINDS = [k for k, _ in Material.Kind.choices]
UNITS = [u for u, _ in Material.Unit.choices]

PROPOSAL_SCHEMA = {
    "type": "object",
    "properties": {
        "product": {
            "type": "object",
            "properties": {
                "existing_code": {"type": ["string", "null"], "description": "Code of a catalogue product that fits, else null."},
                "code": {"type": "string", "description": "New code, PREFIX-XXX-NN like UNI-CAS-01."},
                "name": {"type": "string"},
                "brand": {"type": "string"},
            },
            "required": ["existing_code", "code", "name", "brand"],
            "additionalProperties": False,
        },
        "materials": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "existing_sku": {"type": ["string", "null"], "description": "SKU of a known material that fits, else null."},
                    "sku": {"type": "string"},
                    "name": {"type": "string"},
                    "kind": {"type": "string", "enum": KINDS},
                    "unit": {"type": "string", "enum": UNITS},
                    "qty_per_unit": {"type": "number", "description": "Per garment, in `unit`."},
                },
                "required": ["existing_sku", "sku", "name", "kind", "unit", "qty_per_unit"],
                "additionalProperties": False,
            },
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["product", "materials", "confidence"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "Eres el jefe de producción de Corpotex, una fábrica de uniformes en Piura. Dada la descripción de una prenda "
    "pedida por un cliente, decides si corresponde a un producto del catálogo o es un producto nuevo, y propones su "
    "lista de insumos por prenda (tela, botones, cierres, cuellos y puños, hilo, etiquetas) usando los SKU existentes "
    "cuando sirven. Si corresponde a un producto del catálogo, sus insumos son los del catálogo. El corte, la costura, "
    "el bordado, el sublimado y el estampado se hacen en la planta: no son insumos y no van en la lista; solo van "
    "materiales que se compran a proveedores. Responde solo con el JSON del esquema."
)
# Plant processes Claude may still list as materials: never something to buy (finding of 10/10 22:35).
PROCESS = re.compile(r"^\s*(bordad|sublimad|estampad|serigraf|corte\b|costura\b|confecci)", re.IGNORECASE)


def complete_sync(prompt: str, *, schema: dict) -> dict:
    """Claude, one structured call (wrapped so tests can mock it and views stay sync)."""
    from agent.sdk import complete

    coro = complete(prompt, system_prompt=SYSTEM_PROMPT, model=getattr(settings, "AGENT_MODEL", "sonnet"), schema=schema, effort="low")
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _item_text(item: OrderItem) -> str:
    parts = [item.description, f"color {item.color}" if item.color else "", f"personalización: {item.customization}" if item.customization else ""]
    if item.sizes:
        parts.append("tallas " + ", ".join(f"{k}: {v}" for k, v in item.sizes.items()))
    return ". ".join(p for p in parts if p)


def _catalogue():
    products = list(Product.objects.select_related("brand").prefetch_related("materials__material").order_by("code"))
    materials = list(Material.objects.order_by("kind", "sku"))
    return products, materials


def classify_order(order: Order, *, actor) -> dict:
    require_role(actor, "manager", "production")
    products, materials = _catalogue()
    items = [classify_item(item, order, products, materials) for item in order.items.filter(product__isnull=True).order_by("id")]
    return {"order_id": order.id, "items": items}


def classify_item(item: OrderItem, order: Order, products, materials) -> dict:
    text = _item_text(item)
    customer = order.customer if order.customer_id else None  # a draft (ADR 0028) may have no customer yet
    state = f"Pedido de {customer.name}, marca {order.brand.name}: {text}" if customer else f"Pedido para la marca {order.brand.name}: {text}"
    by_code = {p.code: p for p in products}
    by_sku = {m.sku: m for m in materials}

    budget = jev.Budget()  # Jev's time for this item; past it, Claude alone.

    # 1. A catalogue product? Jev chooses when it is on.
    criteria = {p.code: f"{p.name} · {p.brand.name if p.brand else 'sin marca'} · {', '.join(pm.material.name for pm in p.materials.all())}" for p in products}
    criteria[jev.NEW] = "Prenda nueva: ninguna del catálogo corresponde"
    picked = jev.choose(state, criteria, "Elige el producto del catálogo que corresponde a la prenda pedida, o 'nuevo'.", budget=budget)
    if picked and picked[0] in by_code and picked[1] >= MIN_CONFIDENCE:
        return _catalogue_answer(item, text, by_code[picked[0]], picked[1])

    # 2. New (or unsure): Claude proposes the product and its bill of materials.
    prompt = (
        f"{state}\n\nCatálogo de productos (código: nombre · marca · insumos):\n"
        + "\n".join(f"- {code}: {desc}" for code, desc in criteria.items() if code != jev.NEW)
        + "\n\nInsumos existentes (SKU: nombre, tipo, unidad):\n"
        + "\n".join(f"- {m.sku}: {m.name}, {m.kind}, {m.unit}" for m in materials)
        + "\n\nPropón el producto (existing_code si uno del catálogo corresponde, si no un producto nuevo con código, nombre y marca) "
        "y la lista de insumos por prenda (existing_sku cuando un insumo existente sirve, si no un insumo nuevo con sku, nombre, tipo y unidad). "
        "El color y la talla no crean un insumo nuevo: van en la orden; reusa el SKU existente de la misma tela o avío. "
        "Solo insumos que se compran, no procesos de planta (corte, costura, bordado, sublimado); el bordado puede pedir hilo de bordar."
    )
    proposal = complete_sync(prompt, schema=PROPOSAL_SCHEMA)
    base = float(proposal.get("confidence") or FALLBACK_CONFIDENCE)
    product_block = proposal.get("product") or {}
    existing = by_code.get(product_block.get("existing_code") or "")
    if existing:
        # A catalogue product brings its own bill of materials, which is what `apply_classification`
        # uses: showing Claude's list instead would promise new materials that never get created.
        return _catalogue_answer(item, text, existing, base)
    product_out = {"new": {"code": _slug_code(product_block.get("code") or "", order.brand.name, product_block.get("name") or text), "name": product_block.get("name") or text[:160], "brand": product_block.get("brand") or order.brand.name}}

    materials_out = []
    by_name = {x.name.strip().lower(): x for x in materials}
    # Plant processes are never something to buy (#87): they are dropped before anyone is asked.
    proposed = [m for m in proposal.get("materials") or [] if not (PROCESS.match(m.get("name") or "") and not (m.get("existing_sku") or "").strip())]
    # 3. Jev checks every proposed material against the known SKUs (+ nuevo) in ONE call.
    sku_criteria = {**{x.sku: f"{x.name}, {x.kind}, {x.unit}" for x in materials}, jev.NEW: "Insumo nuevo: ninguno de los existentes"}
    answers = jev.choose_many(
        state,
        {f"m{i}": (sku_criteria, f"Insumo propuesto: {m.get('name')} ({m.get('kind')}, {m.get('unit')}). Elige el SKU existente que es este mismo insumo, o 'nuevo'.") for i, m in enumerate(proposed)},
        budget=budget,
    ) or {}
    for i, m in enumerate(proposed):
        sku = (m.get("existing_sku") or "").strip()
        if not sku:  # A "new" one that is a known material in another colour or size stays the known one.
            sku = _known_sku((m.get("sku") or "").strip().upper(), (m.get("name") or "").strip().lower(), by_sku, by_name)
        sku = sku if sku in by_sku else ""
        unit = m.get("unit") if m.get("unit") in UNITS else "unit"
        confidence = base
        answer = answers.get(f"m{i}")
        if answer and sku and answer[0] in by_sku and answer[1] >= MIN_CONFIDENCE:
            sku, confidence = answer[0], round(answer[1], 2)  # Jev confirms (or corrects) an existing material
        elif answer and not sku and answer[0] == jev.NEW:
            confidence = round(answer[1], 2)  # both say new: Jev's confidence
        # Otherwise Claude's call (and the dedupe) stands: Jev's "nuevo" never creates a duplicate, and
        # Jev never folds a new material into an existing one. Measured on CP-2026-0161 (10/10 23:10):
        # it turned a snap fastener into BOT-MET-NX and embroidery thread into HIL-POL-40.
        if sku and sku in by_sku:
            known = by_sku[sku]
            same = next((x for x in materials_out if x.get("sku") == known.sku), None)
            if same:  # e.g. the body fabric and the stripe of the same jersey: one line, quantities added
                same["qty_per_unit"] = str(Decimal(same["qty_per_unit"]) + Decimal(str(m.get("qty_per_unit") or 0)))
                continue
            materials_out.append({"sku": known.sku, "name": known.name, "material_id": known.id, "qty_per_unit": str(m.get("qty_per_unit") or 0), "unit": known.unit, "confidence": confidence})
        else:
            new_sku = (m.get("sku") or "").strip().upper() or _slug_code("", "MAT", m.get("name") or "nuevo")
            materials_out.append({"new": {"sku": new_sku, "name": m.get("name") or new_sku, "kind": m.get("kind") if m.get("kind") in KINDS else "other", "unit": unit}, "qty_per_unit": str(m.get("qty_per_unit") or 0), "unit": unit, "confidence": confidence})
    return {"item_id": item.id, "description": text, "product": product_out, "confidence": round(base, 2), "materials": materials_out}


def _known_sku(sku: str, name: str, by_sku: dict, by_name: dict) -> str:
    """The existing SKU a proposed "new" material duplicates: its SKU extends a known one
    (`TEL-ALG-30-AZM` → `TEL-ALG-30`) or its name is a known name. Empty when it is really new."""
    if sku in by_sku:
        return sku
    prefixes = [known for known in by_sku if sku.startswith(known + "-")]
    if prefixes:
        return max(prefixes, key=len)
    known = by_name.get(name)
    return known.sku if known else ""


def _catalogue_answer(item: OrderItem, text: str, product: Product, confidence: float) -> dict:
    confidence = round(confidence, 2)
    return {
        "item_id": item.id,
        "description": text,
        "product": {"existing_id": product.id, "code": product.code, "name": product.name},
        "confidence": confidence,
        "materials": [
            {"sku": pm.material.sku, "name": pm.material.name, "material_id": pm.material_id, "qty_per_unit": str(pm.qty_per_unit), "unit": pm.material.unit, "confidence": confidence}
            for pm in product.materials.all()
        ],
    }


def _slug_code(code: str, brand: str, name: str) -> str:
    code = re.sub(r"[^A-Z0-9-]", "", (code or "").upper())
    if not code:
        prefix = re.sub(r"[^A-Z]", "", brand.upper())[:3] or "NEW"
        stem = re.sub(r"[^A-Z]", "", name.upper())[:3] or "PRD"
        code = f"{prefix}-{stem}-01"
    base, n = code, 1
    while Product.objects.filter(code=code).exists():
        n += 1
        code = f"{base}-{n}" if not re.search(r"-\d+$", base) else re.sub(r"-\d+$", f"-{n:02d}", base)
    return code


def product_for_entry(entry: dict, order: Order, warnings: list[str]) -> Product:
    """One confirmed classification (`{product: {existing_id} | {new: {code, name, brand}},
    materials: [...]}`): the catalogue product, or a new one with its new materials and bill of
    materials. Shared by `apply-classification` and the order born broken down (ADR 0028)."""
    from .services import UnknownReference

    product_block = entry.get("product") or {}
    if product_block.get("existing_id"):
        product = Product.objects.filter(pk=product_block["existing_id"]).first()
        if product is None:
            raise UnknownReference(f"El producto {product_block['existing_id']} no existe")
        return product
    new = product_block.get("new") or {}
    if not new.get("name"):
        raise UnknownReference("Cada ítem clasificado necesita un producto existente o uno nuevo con nombre")
    brand = Brand.objects.filter(name__iexact=(new.get("brand") or order.brand.name).strip()).first() or order.brand
    product = Product.objects.create(code=_slug_code(new.get("code") or "", brand.name, new["name"]), name=new["name"][:160], brand=brand)
    for m in entry.get("materials") or []:
        material = _material_for(m)
        if material is None:
            continue
        qty = Decimal(str(m.get("qty_per_unit") or 0))
        if qty <= 0:
            warnings.append(f"{material.name}: cantidad por prenda vacía, no entra al desglose")
            continue
        ProductMaterial.objects.get_or_create(product=product, material=material, defaults={"qty_per_unit": qty})
    if not product.materials.exists():
        warnings.append(f"{product.name}: sin insumos; solo se pedirá costura")
    return product


def apply_classification(order: Order, items: list[dict], *, actor) -> tuple[Order, list[str]]:
    """What production confirmed: creates products, materials and bills of materials as needed,
    assigns the product to each item and breaks the order down again."""
    from .services import UnknownReference, break_down_order

    require_role(actor, "manager", "production")
    warnings: list[str] = []
    with transaction.atomic():
        for entry in items:
            try:
                item = order.items.get(pk=entry["item_id"])
            except (OrderItem.DoesNotExist, KeyError):
                raise UnknownReference(f"El ítem {entry.get('item_id')} no es de la orden {order.code}")
            item.product = product_for_entry(entry, order, warnings)
            item.save(update_fields=["product", "updated_at"])
        break_down_order(order)
    return order, warnings


def apply_by_key(order: Order, keyed_items: list[tuple[str | None, OrderItem]], classification: dict | None, warnings: list[str]) -> int:
    """`classification` of `POST/PATCH /api/orders/` (ADR 0028): the items whose `key` has a
    confirmed classification get their product; the rest stay to classify. Returns how many."""
    entries = {str(e["key"]): e for e in (classification or {}).get("items") or [] if e.get("key") not in (None, "")}
    done = 0
    for key, item in keyed_items:
        if item.product_id or key in (None, "") or str(key) not in entries:
            continue
        item.product = product_for_entry(entries[str(key)], order, warnings)
        item.save(update_fields=["product", "updated_at"])
        done += 1
    return done


MIN_DRAFT_TEXT = 12


def classify_draft(brand: Brand, items: list[dict], *, customer=None) -> list[dict]:
    """`POST /api/orders/classify-draft/` (ADR 0028 §1): the `classify` proposal for lines still
    being written, nothing saved. Short lines or lines without a quantity come back `pending`
    without calling any model; a model failure is that line's `error`, never the request's."""
    draft = Order(brand=brand, customer=customer)
    products = materials = None
    results = []
    for line in items:
        key, text, quantity = line.get("key"), (line.get("description") or "").strip(), line.get("quantity")
        if len(text) < MIN_DRAFT_TEXT or not quantity:
            results.append({"key": key, "status": "pending"})
            continue
        if products is None:
            products, materials = _catalogue()
        try:
            proposal = classify_item(OrderItem(order=draft, description=text, quantity=int(quantity)), draft, products, materials)
        except Exception as exc:  # The form keeps working: this line shows the failure and can be saved unclassified.
            logger.warning("classify_draft: line %s failed: %s", key, exc)
            results.append({"key": key, "status": "error", "detail": f"No se pudo clasificar: {exc}"[:300]})
            continue
        proposal.pop("item_id", None)
        results.append({"key": key, "status": "classified", **proposal})
    return results


def _material_for(entry: dict):
    if entry.get("sku") and not entry.get("new"):
        return Material.objects.filter(sku__iexact=entry["sku"].strip()).first()
    new = entry.get("new") or {}
    if not new.get("name"):
        return None
    sku = (new.get("sku") or "").strip().upper() or _slug_code("", "MAT", new["name"])
    material, _ = Material.objects.get_or_create(
        sku=sku,
        defaults={"name": new["name"][:160], "kind": new.get("kind") if new.get("kind") in KINDS else "other", "unit": new.get("unit") if new.get("unit") in UNITS else "unit", "stock": Decimal("0")},
    )
    return material
