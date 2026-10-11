"""Valida la carpeta seed/ contra el contrato. Uso: python validate_seed.py"""
import json, os, re, sys
H = os.path.dirname(os.path.abspath(__file__)); E = []
def L(n): return json.load(open(f"{H}/data/{n}.json"))
def err(m): E.append(m)
d = {n: L(n) for n in "brands customers materials products product_materials suppliers orders purchase_orders alerts decisions style_versions".split()}
idx = lambda n, k: {x[k] for x in d[n]}
B, C, M, P, S, O, PO = idx("brands","name"), idx("customers","name"), idx("materials","sku"), idx("products","code"), idx("suppliers","name"), idx("orders","code"), idx("purchase_orders","code")
for n,k in [("brands","name"),("customers","name"),("materials","sku"),("products","code"),("suppliers","name"),("orders","code"),("purchase_orders","code")]:
    if len(idx(n,k)) != len(d[n]): err(f"{n}: {k} duplicado")
def ref(v, s, w, null=False):
    if v is None and null: return
    if v not in s: err(f"{w}: referencia rota {v!r}")
def enum(v, ok, w):
    if v not in ok: err(f"{w}: valor inválido {v!r}")
def money(a,b,w):
    if abs(float(a)-float(b)) > 0.005: err(f"{w}: {a} != {b}")
# fechas / telefonos / campos prohibidos en todo el árbol
DATE = re.compile(r"^T[+-]\d+( \d{2}:\d{2})?$"); ABS = re.compile(r"\b(19|20)\d{2}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b")
PHONE = re.compile(r"(\+?51\s?)?9\d{2}[\s-]?\d{3}[\s-]?\d{3}|\+\d{6,}")
BAN = {"owner","approved_by","recorded_by","received_by","conversation","user","phone","critical_path","spec_sheet","requirements"}
DK = re.compile(r"(_on|_at|valid_from)$")
def walk(x, w):
    if isinstance(x, dict):
        for k, v in x.items():
            if k in BAN: err(f"{w}.{k}: campo prohibido")
            if DK.search(k) and v is not None and not (isinstance(v,str) and DATE.match(v)): err(f"{w}.{k}: fecha no relativa {v!r}")
            walk(v, f"{w}.{k}")
    elif isinstance(x, list): [walk(v, f"{w}[{i}]") for i, v in enumerate(x)]
    elif isinstance(x, str):
        if ABS.search(x): err(f"{w}: fecha absoluta {x!r}")
        if PHONE.search(x): err(f"{w}: parece teléfono {x!r}")
for n, v in d.items(): walk(v, n)
for f in os.listdir(f"{H}/data"):
    t = open(f"{H}/data/{f}").read()
    if PHONE.search(t): err(f"{f}: parece teléfono")
# catálogo
for x in d["customers"]:
    enum(x["kind"], {"company","school","ngo","individual"}, x["name"])
    if x.get("tax_id") and not re.fullmatch(r"\d{11}", x["tax_id"]): err(f"{x['name']}: RUC inválido")
for x in d["materials"]:
    enum(x["kind"], {"fabric","button","zipper","collar_cuff","other"}, x["sku"]); enum(x["unit"], {"m","kg","unit"}, x["sku"])
    if x["image"] != f"images/materials/{x['sku']}.jpg": err(f"{x['sku']}: ruta de imagen")
for x in d["products"]:
    if x["image"] != f"images/products/{x['code']}.jpg": err(f"{x['code']}: ruta de imagen")
for x in d["product_materials"]: ref(x["product"], P, "pm"); ref(x["material"], M, "pm")
bom = {}
for x in d["product_materials"]: bom.setdefault(x["product"], set()).add(x["material"])
for p in P:
    if p not in bom: err(f"{p}: sin product_materials")
for im in [x["image"] for x in d["materials"] + d["products"]]:
    f = f"{H}/{im}"
    if not os.path.exists(f): err(f"falta {im}"); continue
    if os.path.getsize(f) >= 300_000: err(f"{im}: >= 300 KB")
    try:
        from PIL import Image; w, h = Image.open(f).size
        if max(w, h) > 1200: err(f"{im}: {w}x{h}")
    except ImportError: pass
# proveedores
for s in d["suppliers"]:
    w = s["name"]; enum(s["kind"], {"material","workshop","finished"}, w); enum(s["city"], {"Piura","Lima","México"}, w)
    enum(s["source"], {"registered","self_registered","suggested","external"}, w); enum(s["status"], {"active","pending_review","inactive"}, w)
    for k in ("lat","lng"):
        if k in s and not isinstance(s[k], (int, float)): err(f"{w}: {k} no numérico")
    if s["status"] == "pending_review":
        if s["rates"]: err(f"{w}: pendiente con rates")
        continue
    enum(s["payment_method"], {"yape","transfer","cash"}, w)
    if not 0 <= float(s["on_time_score"]) <= 1 or not 1 <= float(s["quality_score"]) <= 5: err(f"{w}: score fuera de rango")
    if s["kind"] == "workshop" and not s.get("weekly_capacity"): err(f"{w}: taller sin capacidad")
    for r in s["rates"]:
        ref(r["material"], M, w, True); ref(r["product"], P, w, True); enum(r["currency"], {"PEN","USD"}, w); enum(r["source"], {"historical","quote","negotiated"}, w)
        if (r["material"] is None) == (r["product"] is None): err(f"{w}: rate con material y producto")
        if r["currency"] == "USD" and s["city"] != "México": err(f"{w}: USD fuera de México")
# órdenes
for o in d["orders"]:
    w = o["code"]; ref(o["customer"], C, w); ref(o["brand"], B, w)
    enum(o["status"], {"registered","broken_down","confirmed","sourcing","in_production","ready","delivered","cancelled"}, w)
    enum(o["risk"], {"ok","at_risk","in_danger"}, w); enum(o["source"], {"api","pdf","manual"}, w)
    if o["status"] == "in_production": enum(o["production_stage"], {"cutting","sublimation","embroidery","sewing","finishing"}, w)
    elif o["production_stage"] is not None: err(f"{w}: production_stage fuera de in_production")
    tot = 0
    for i in o["items"]:
        ref(i["product"], P, w); enum(i["customization"], {"embroidery","print","sublimation",None}, w)
        if sum(i["sizes"].values()) != i["quantity"]: err(f"{w}: tallas no suman {i['quantity']}")
        tot += i["quantity"] * float(i["unit_price"])
    money(o["total_amount"], tot, f"{w} total")
if not {"registered","broken_down","confirmed","sourcing","in_production","ready","delivered","cancelled"} <= {o["status"] for o in d["orders"]}: err("faltan estados de orden")
omap = {o["code"]: o for o in d["orders"]}
# pedidos
POST = {"confirmed","in_progress","delivered","cancelled_by_supplier","cancelled"}
for p in d["purchase_orders"]:
    w = p["code"]; ref(p["supplier"], S, w); ref(p["suggested_supplier"], S, w); ref(p["redistributed_from"], PO, w, True)
    enum(p["kind"], {"material","workshop","finished"}, w); enum(p["currency"], {"PEN","USD"}, w)
    enum(p["status"], {"suggested","approved","negotiating","confirmed","in_progress","delivered","declined_by_supplier","cancelled_by_supplier","cancelled"}, w)
    for c in p["candidates"]: ref(c["supplier"], S, w)
    for k, v in p["scores"].items():
        if not 0 <= v <= 1: err(f"{w}: score {k}")
    tot = 0
    for i in p["items"]:
        ref(i["order"], O, w); enum(i["kind"], {"material","workshop","finished"}, w)
        if i["kind"] == "material":
            ref(i["material"], M, w)
            if i["product"] is not None: err(f"{w}: item material con producto")
            if not any(i["material"] in bom[it["product"]] for it in omap[i["order"]]["items"]): err(f"{w}: {i['material']} no está en el BOM de {i['order']}")
        else:
            ref(i["product"], P, w)
            if i["product"] not in {it["product"] for it in omap[i["order"]]["items"]}: err(f"{w}: {i['product']} no está en {i['order']}")
        tot += float(i["quantity"]) * float(i["unit_price"])
    money(p["total_amount"], tot, f"{w} total")
    if p["payments"]:
        if p["status"] not in POST: err(f"{w}: pagos antes de confirmed")
        money(sum(float(x["amount"]) for x in p["payments"]), p["total_amount"], f"{w} pagos")
        for x in p["payments"]:
            enum(x["kind"], {"advance","balance"}, w); enum(x["method"], {"yape","transfer","cash"}, w); enum(x["status"], {"pending","paid"}, w)
            if (x["status"] == "paid") != (x["paid_at"] is not None): err(f"{w}: paid_at incoherente")
    elif p["status"] in POST - {"cancelled","cancelled_by_supplier"}: err(f"{w}: sin pagos")
    for r in p["progress_reports"]: enum(r["source"], {"whatsapp","web","manual"}, w)
    if p["status"] == "delivered":
        for k in ["rating_delay_days","rating_quality","rating_defect_pct","rating_price_vs_ref_pct","rating_score","rated_at"]:
            if k not in p: err(f"{w}: falta {k}")
        if p["delivered_on"] is None: err(f"{w}: delivered sin delivered_on")
    elif "rating_score" in p: err(f"{w}: rating fuera de delivered")
    for x in p.get("deliveries", []):
        if not 1 <= x["quality"] <= 5: err(f"{w}: quality")
# alertas
seen = set()
for a in d["alerts"]:
    w = f"alert {a['kind']}"; ref(a["order"], O, w, True); ref(a["purchase_order"], PO, w, True)
    enum(a["kind"], {"stalled_purchase_order","delay","order_in_danger","no_response","payment_due","instance_down","no_channel","turn_failed","style_refresh_failed"}, w)
    enum(a["severity"], {"info","warning","critical"}, w); enum(a["status"], {"open","acknowledged","resolved"}, w)
    if (a["status"] == "resolved") != (a["resolved_at"] is not None): err(f"{w}: resolved_at")
    key = (a["kind"], a["order"], a["purchase_order"])
    if a["status"] != "resolved":
        if key in seen: err(f"{w}: duplicado abierto {key}")
        seen.add(key)
# decisiones
for x in d["decisions"]:
    w = f"decision {x['kind']}"; ref(x["order"], O, w); ref(x["new_supplier"], S, w, True)
    for c in x["purchase_orders"]: ref(c, PO, w)
    enum(x["kind"], {"approve_assignment","price","terms","other"}, w); enum(x["status"], {"pending","approved","rejected","supplier_changed","cancelled"}, w)
    enum(x["channel"], {"dashboard","assistant","admin"}, w)
for v in d["style_versions"]: enum(v["source"], {"onboarding","daily","template","manual","rollback"}, "style")
# escena demo
po38 = [p for p in d["purchase_orders"] if any(i["order"] == "CP-2026-0142" for i in p["items"]) and p["kind"] == "workshop"]
if len(po38) != 1 or po38[0]["supplier"] != "Confecciones del Norte" or po38[0]["status"] != "in_progress" or po38[0]["units_done"] != 400: err("escena demo: pedido de taller")
if any(x["kind"] == "approve_assignment" and x["order"] == "CP-2026-0142" for x in d["decisions"]): err("escena demo: decision prohibida")
if any(a["kind"] == "order_in_danger" and a["order"] == "CP-2026-0142" for a in d["alerts"]): err("escena demo: alerta prohibida")
print("\n".join(E) or "OK: seed válido"); sys.exit(1 if E else 0)
