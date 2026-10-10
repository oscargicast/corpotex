"""Loads the demo fixtures (`backend/seed/data/*.json`, ADR 0021) into the models.

References are natural keys (sku, code, name); dates are relative to the demo day `T`
(`"T+3"`, `"T-2 14:30"`); money is a decimal string. Unknown keys are ignored, so the JSON can
carry fields the model computes (totals, scores, kind). Any broken reference aborts the whole
load (the caller wraps it in a transaction)."""

import json
import logging
import re
import unicodedata
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.files import File
from django.utils import timezone

from core.models import ROLE_GROUPS, Brand, Config, Customer, Material, Product, ProductMaterial, StyleVersion, User
from manager.models import Alert, Decision
from messaging.models import AllowedNumber, Conversation, Message
from operations.models import (
    Delivery,
    Order,
    OrderItem,
    Payment,
    ProgressReport,
    PurchaseOrder,
    PurchaseOrderItem,
    Requirement,
    StatusChange,
)
from suppliers.models import Rate, Supplier

logger = logging.getLogger(__name__)

SEED_DIR = Path(__file__).resolve().parent
DATA_DIR = SEED_DIR / "data"
IMAGES_DIR = SEED_DIR / "images"
LIMA = timezone.get_default_timezone()
REL = re.compile(r"^T([+-]\d+)?(?:\s+(\d{1,2}):(\d{2}))?$")
ORDER_CODE = re.compile(r"^CP-\d{4}-\d{4}$")
PO_CODE = re.compile(r"^P[TIF]-\d{4}$")
PO_PREFIX = {"workshop": "PT", "material": "PI", "finished": "PF"}

# Demo phone numbers are constants on purpose (decision of 10/10; the repo is public).
REAL_SUPPLIER_KEY = "Confecciones del Norte"
REAL_SUPPLIER_PHONE = "51906746241"
MANAGER_PHONE = "51907898162"


class SeedError(Exception):
    pass


class Loader:
    def __init__(self, data_dir: Path = DATA_DIR, images_dir: Path = IMAGES_DIR, *, out=None):
        self.data_dir = data_dir
        self.images_dir = images_dir
        self.out = out or (lambda msg: logger.info(msg))
        self.t = timezone.localtime(timezone.now())  # Real time (decision of 10/10 21:40); "T+N HH:MM" sets the hour.
        self.brands: dict[str, Brand] = {}
        self.customers: dict[str, Customer] = {}
        self.materials: dict[str, Material] = {}
        self.products: dict[str, Product] = {}
        self.suppliers: dict[str, Supplier] = {}
        self.orders: dict[str, Order] = {}
        self.purchase_orders: dict[str, PurchaseOrder] = {}
        self.users: dict[str, User] = {}

    # --- helpers ---------------------------------------------------------------------------

    def read(self, name: str) -> list:
        path = self.data_dir / f"{name}.json"
        if not path.exists():
            return []
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)

    def rel_datetime(self, value):
        if value in (None, ""):
            return None
        match = REL.match(str(value).strip())
        if not match:
            raise SeedError(f"Fecha relativa inválida: {value!r} (se espera 'T+N' o 'T-N HH:MM')")
        days = int(match.group(1) or 0)
        when = self.t + timedelta(days=days)
        if match.group(2):
            when = when.replace(hour=int(match.group(2)), minute=int(match.group(3)))
        return when

    def rel_date(self, value):
        when = self.rel_datetime(value)
        return when.date() if when else None

    @staticmethod
    def dec(value, default="0"):
        return Decimal(str(value if value not in (None, "") else default))

    def ref(self, table: dict, key, what: str):
        if key is None:
            return None
        try:
            return table[key]
        except KeyError:
            raise SeedError(f"{what} desconocido: {key!r}") from None

    def image(self, instance, field: str, rel_path, fallback_name: str):
        """Copies `images/<kind>/<key>.jpg` into MEDIA and attaches it."""
        candidates = []
        if rel_path:
            candidates.append(self.images_dir.parent / rel_path)
            candidates.append(self.images_dir / Path(rel_path).name)
        candidates.append(self.images_dir / fallback_name)
        for path in candidates:
            if path.exists():
                with path.open("rb") as fh:
                    getattr(instance, field).save(path.name, File(fh), save=False)
                return True
        return False

    # --- users and config ------------------------------------------------------------------

    def load_users(self):
        password = settings_env("SEED_USERS_PASSWORD")
        if not password:
            logger.warning("SEED_USERS_PASSWORD is not set: role users keep password = username")
            self.out("aviso: SEED_USERS_PASSWORD no está en .env; contraseña = usuario")
        for role, group_name in ROLE_GROUPS.items():
            username = {"manager": "gerente", "sales": "comercial", "production": "produccion"}[role]
            user, created = User.objects.get_or_create(username=username, defaults={"first_name": username.title()})
            if password:
                user.set_password(password)
            elif created:
                user.set_password(username)
            user.is_staff = False  # The admin is the superuser's only.
            user.save()
            user.groups.add(Group.objects.get(name=group_name))
            self.users[username] = user
            from rest_framework.authtoken.models import Token

            Token.objects.get_or_create(user=user)
        su_name = settings_env("DJANGO_SUPERUSER_USERNAME")
        su_pass = settings_env("DJANGO_SUPERUSER_PASSWORD")
        if su_name and su_pass and not User.objects.filter(username=su_name).exists():
            User.objects.create_superuser(username=su_name, password=su_pass, email="")
            self.out(f"superuser {su_name} creado")

    def load_config(self):
        config = Config.load()
        raw = {}
        path = self.data_dir / "config.json"
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
        plant = raw.get("plant") or self.plant_from_readme()
        config.clock_sim_start = config.clock_real_start = timezone.now()  # Real time, no acceleration.
        config.clock_paused = False
        config.clock_factor = Decimal("1")
        config.buffer_days = int(raw.get("buffer_days", 5))
        config.stage_durations = raw.get("stage_durations") or {"cutting": 1, "sublimation": 1, "embroidery": 1, "sewing": 3, "finishing": 1}
        config.agent_user = self.users["gerente"]
        config.agent_phone = raw.get("agent_phone") or MANAGER_PHONE
        if plant:
            config.plant_name = plant.get("name", "")
            config.plant_lat = plant.get("lat")
            config.plant_lng = plant.get("lng")
        config.save()

    def plant_from_readme(self) -> dict | None:
        readme = SEED_DIR / "README.md"
        if not readme.exists():
            return None
        match = re.search(r'\{"plant":\s*(\{.*?\})\}', readme.read_text(encoding="utf-8"), re.S)
        return json.loads(match.group(1)) if match else None

    # --- catalogue --------------------------------------------------------------------------

    def load_catalogue(self):
        for row in self.read("brands"):
            self.brands[row["name"]] = Brand.objects.create(name=row["name"], description=row.get("description", ""))
        for row in self.read("customers"):
            self.customers[row["name"]] = Customer.objects.create(
                name=row["name"], tax_id=row.get("tax_id") or None, kind=row.get("kind", "company"),
                address=row.get("address", ""), lat=row.get("lat"), lng=row.get("lng"),
            )
        for row in self.read("materials"):
            material = Material(sku=row["sku"], name=row["name"], kind=row["kind"], unit=row["unit"], stock=self.dec(row.get("stock")))
            self.image(material, "image", row.get("image"), f"materials/{row['sku']}.jpg")
            material.save()
            self.materials[material.sku] = material
        for row in self.read("products"):
            product = Product(code=row["code"], name=row["name"])
            self.image(product, "image", row.get("image"), f"products/{row['code']}.jpg")
            product.save()
            self.products[product.code] = product
        for row in self.read("product_materials"):
            ProductMaterial.objects.create(
                product=self.ref(self.products, row["product"], "producto"),
                material=self.ref(self.materials, row["material"], "insumo"),
                qty_per_unit=self.dec(row["qty_per_unit"]),
            )

    # --- suppliers --------------------------------------------------------------------------

    def load_suppliers(self):
        for row in self.read("suppliers"):
            source = row.get("source", "registered")
            source_detail = row.get("source_detail")
            notes = row.get("notes", "") or ""
            if source == "external" and not source_detail and notes:
                source_detail, notes = {"source": "notes", "excerpt": notes}, ""  # Old JSON: the source sat in notes.
            supplier = Supplier.objects.create(
                name=row["name"],
                kind=row["kind"],
                specialties=row.get("specialties") or [],
                city=row.get("city", ""),
                address=row.get("address", ""),
                lat=row.get("lat"),
                lng=row.get("lng"),
                is_in_house=bool(row.get("is_in_house")),
                weekly_capacity=row.get("weekly_capacity"),
                lead_time_days=row.get("lead_time_days") or 7,
                follow_up_every_hours=row.get("follow_up_every_hours") or 48,
                currency=row.get("currency") or (row.get("rates") or [{}])[0].get("currency") or "PEN",
                source=source,
                source_detail=source_detail,
                status=row.get("status", "active"),
                notes=notes,
            )
            self.suppliers[supplier.name] = supplier
            for rate in row.get("rates") or []:
                Rate.objects.create(
                    supplier=supplier,
                    material=self.ref(self.materials, rate.get("material"), "insumo") if rate.get("material") else None,
                    product=self.ref(self.products, rate.get("product"), "producto") if rate.get("product") else None,
                    unit_price=self.dec(rate["unit_price"]),
                    valid_from=self.rel_date(rate.get("valid_from")) or self.t.date(),
                )
            if not supplier.is_in_house and source != "external":
                ascii_name = unicodedata.normalize("NFKD", supplier.name).encode("ascii", "ignore").decode()
                slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
                AllowedNumber.objects.create(phone=f"sim-{slug}"[:40], name="", supplier=supplier, active=True, simulated=True)
            for number in row.get("numbers") or []:
                phone = number.get("phone", "")
                if not phone or phone.startswith("sim-"):
                    continue
                AllowedNumber.objects.get_or_create(phone=phone, defaults={"name": number.get("name", ""), "supplier": supplier, "active": bool(number.get("active"))})
        real = self.suppliers.get(REAL_SUPPLIER_KEY)
        if real:
            AllowedNumber.objects.update_or_create(
                phone=REAL_SUPPLIER_PHONE, defaults={"name": "", "supplier": real, "active": True, "simulated": False}
            )

    # --- orders and purchase orders ---------------------------------------------------------

    def load_orders(self):
        from operations.services import break_down_order

        for row in self.read("orders"):
            if not ORDER_CODE.match(row["code"]):
                raise SeedError(f"orders.json: código {row['code']!r} no cumple CP-AAAA-NNNN")
            order = Order.objects.create(
                code=row["code"],
                customer=self.ref(self.customers, row["customer"], "cliente"),
                brand=self.ref(self.brands, row["brand"], "marca"),
                owner=self.users.get("comercial"),
                status=row.get("status", "registered"),
                production_stage=row.get("production_stage") or "",
                issued_on=self.rel_date(row.get("issued_on")) or self.t.date(),
                promised_on=self.rel_date(row["promised_on"]),
                estimated_on=self.rel_date(row.get("estimated_on")),
                risk=row.get("risk") or "ok",
                risk_reason=row.get("risk_reason") or "",
            )
            for item in row.get("items") or []:
                OrderItem.objects.create(
                    order=order,
                    product=self.ref(self.products, item["product"], "producto"),
                    quantity=int(item["quantity"]),
                    sizes=item.get("sizes") or {},
                    color=item.get("color", "") or "",
                    customization=item.get("customization") or "",
                    unit_price=self.dec(item["unit_price"]),
                )
            self.orders[order.code] = order
            if order.status != "registered":
                status, stage, estimated, risk, reason = order.status, order.production_stage, order.estimated_on, order.risk, order.risk_reason
                break_down_order(order)
                Order.objects.filter(pk=order.pk).update(status=status, production_stage=stage, estimated_on=estimated, risk=risk, risk_reason=reason)
                order.refresh_from_db()

    def requirement_for(self, order: Order, kind: str, material_key, product_key) -> Requirement:
        filters = {"order": order, "kind": kind}
        if material_key:
            filters["material"] = self.ref(self.materials, material_key, "insumo")
        if product_key:
            filters["product"] = self.ref(self.products, product_key, "producto")
        requirement = Requirement.objects.filter(**filters).first()
        if requirement is None:
            requirement = Requirement.objects.create(qty_needed=0, **filters)
        return requirement

    def load_purchase_orders(self):
        rows = self.read("purchase_orders")
        for row in rows:
            supplier = self.ref(self.suppliers, row["supplier"], "proveedor")
            kind = row.get("kind") or supplier.kind
            if not PO_CODE.match(row["code"]) or not row["code"].startswith(PO_PREFIX.get(kind, "??")):
                raise SeedError(f"purchase_orders.json: código {row['code']!r} debe ser {PO_PREFIX.get(kind, 'PT|PI|PF')}-NNNN")
            po = PurchaseOrder.objects.create(
                code=row["code"],
                supplier=supplier,
                status=row.get("status", "suggested"),
                suggested_supplier=self.ref(self.suppliers, row.get("suggested_supplier"), "proveedor") if row.get("suggested_supplier") else supplier,
                rationale=row.get("rationale", "") or "",
                scores=row.get("scores") or {},
                internal_due_on=self.rel_date(row.get("internal_due_on")),
                committed_on=self.rel_date(row.get("committed_on")),
                next_follow_up_at=self.rel_datetime(row.get("next_follow_up_at")),
                terms=row.get("terms", "") or "",
                rating=self.rating(row),
            )
            self.purchase_orders[po.code] = po
            for item in row.get("items") or []:
                requirement = self.requirement_for(self.ref(self.orders, item["order"], "orden"), row.get("kind") or supplier.kind, item.get("material"), item.get("product"))
                qty = self.dec(item["quantity"])
                if requirement.qty_needed == 0:
                    requirement.qty_needed = qty
                    requirement.save(update_fields=["qty_needed"])
                PurchaseOrderItem.objects.create(
                    purchase_order=po, requirement=requirement, quantity=qty,
                    unit_price=self.dec(item.get("unit_price")), qty_delivered=self.dec(item.get("qty_delivered")),
                )
            for report in row.get("progress_reports") or []:
                ProgressReport.objects.create(
                    purchase_order=po, units_done=int(report["units_done"]), note=report.get("note", "") or "",
                    reported_at=self.rel_datetime(report.get("reported_at")) or self.t, acknowledged_at=self.t,
                )
            for delivery in row.get("deliveries") or []:
                Delivery.objects.create(
                    purchase_order=po, qty_received=self.dec(delivery["qty_received"]), qty_defective=self.dec(delivery.get("qty_defective")),
                    quality=int(delivery.get("quality", 5)), received_at=self.rel_datetime(delivery.get("received_at")) or self.t, note=delivery.get("note", "") or "",
                )
            for payment in row.get("payments") or []:
                Payment.objects.create(
                    purchase_order=po, kind=payment["kind"], amount=self.dec(payment["amount"]),
                    method=payment.get("method") or "", paid_at=self.rel_datetime(payment.get("paid_at")),
                )
        # Second pass: links between purchase orders.
        for row in rows:
            if row.get("redistributed_from"):
                po = self.purchase_orders[row["code"]]
                po.redistributed_from = self.ref(self.purchase_orders, row["redistributed_from"], "pedido")
                po.save(update_fields=["redistributed_from"])

    def rating(self, row) -> dict | None:
        rating = row.get("rating")
        if rating:
            return rating
        if row.get("rating_score") is None and row.get("status") != "delivered":
            return None
        if row.get("rating_score") is None:
            return None
        return {
            "delay_days": row.get("rating_delay_days", 0),
            "quality": row.get("rating_quality", 4),
            "defect_pct": str(row.get("rating_defect_pct", "0.00")),
            "price_vs_ref_pct": str(row.get("rating_price_vs_ref_pct", "0.00")),
            "score": str(row.get("rating_score")),
            "rated_at": (self.rel_datetime(row.get("delivered_on")) or self.t).isoformat(),
        }

    # --- decisions, alerts, conversations, style --------------------------------------------

    def load_decisions(self):
        for row in self.read("decisions"):
            pos = [self.ref(self.purchase_orders, code, "pedido") for code in row.get("purchase_orders") or []]
            conversation = None
            if row.get("conversation"):
                conversation = self.conversation(row["conversation"])
            elif pos and row.get("kind") != "approve_assignment":
                conversation = self.conversation({"supplier": pos[0].supplier.name})
            decision = Decision.objects.create(
                kind=row["kind"],
                status=row.get("status", "pending"),
                conversation=conversation,
                summary=(row.get("summary") or "")[:300],
                detail=self.normalize_detail(row.get("detail") or {}, default_po=pos[0] if len(pos) == 1 else None),
                note=row.get("note", "") or "",
                resolved_by=self.users.get("gerente") if row.get("resolved_at") else None,
                resolved_at=self.rel_datetime(row.get("resolved_at")),
                communicated_at=self.rel_datetime(row.get("communicated_at")),
            )
            decision.purchase_orders.set(pos)
            for po in pos:
                if po.conversation_id is None and conversation is not None:
                    po.conversation = conversation
                    po.save(update_fields=["conversation"])

    def normalize_detail(self, detail: dict, default_po=None) -> dict:
        """Kenji's `proposal` may be one object; the dashboard expects a list, each with
        `purchase_order` and `candidates`."""
        detail = dict(detail)
        proposal = detail.get("proposal")
        if isinstance(proposal, dict):
            proposal = [proposal]
        normalized = []
        for entry in proposal or []:
            entry = dict(entry)
            supplier = entry.get("supplier")
            if isinstance(supplier, str):
                sup = self.suppliers.get(supplier)
                entry["supplier"] = {"id": sup.id, "name": sup.name} if sup else {"id": None, "name": supplier}
            code = entry.get("purchase_order_code") or (entry.get("purchase_order") or {}).get("code") if isinstance(entry.get("purchase_order"), dict) else entry.get("purchase_order")
            po = (self.purchase_orders.get(code) if code else None) or default_po
            entry["purchase_order"] = {"id": po.id, "code": po.code} if po else None
            entry.setdefault("candidates", [])
            entry["committed_on"] = self.rel_date(entry.get("committed_on")).isoformat() if entry.get("committed_on") else None
            normalized.append(entry)
        if proposal is not None:
            detail["proposal"] = normalized
        for key in ("before", "after"):
            block = detail.get(key)
            if isinstance(block, dict):
                block.setdefault("route_id", None)
                if block.get("estimated_on"):
                    block["estimated_on"] = self.rel_date(block["estimated_on"]).isoformat()
        return detail

    def load_alerts(self):
        for row in self.read("alerts"):
            Alert.objects.create(
                kind=row["kind"],
                severity=row.get("severity", "warning"),
                status=row.get("status", "open"),
                order=self.ref(self.orders, row.get("order"), "orden") if row.get("order") else None,
                purchase_order=self.ref(self.purchase_orders, row.get("purchase_order"), "pedido") if row.get("purchase_order") else None,
                text=(row.get("text") or "")[:300],
                detected_at=self.rel_datetime(row.get("detected_at")) or self.t,
                resolved_at=self.rel_datetime(row.get("resolved_at")),
            )

    def conversation(self, spec: dict) -> Conversation | None:
        supplier = self.ref(self.suppliers, spec["supplier"], "proveedor")
        numbers = supplier.numbers.filter(active=True)
        number = numbers.filter(name=spec.get("number")).first() if spec.get("number") else None
        number = number or numbers.filter(simulated=True).first() or numbers.first()
        if number is None:
            return None
        channel = spec.get("channel") or ("simulator" if number.simulated else "whatsapp")
        conversation, _ = Conversation.objects.get_or_create(channel=channel, allowed_number=number)
        return conversation

    def load_conversations(self):
        for row in self.read("conversations"):
            conversation = self.conversation(row)
            if conversation is None:
                continue
            for message in row.get("messages") or []:
                Message.objects.create(
                    conversation=conversation,
                    author=message.get("author", "supplier"),
                    text=message.get("text", ""),
                    status="processed" if message.get("author", "supplier") == "supplier" else "sent",
                    sent_at=self.rel_datetime(message.get("sent_at")) or self.t,
                )

    def load_style(self, *, reset: bool):
        manager = self.users["gerente"]
        if not reset and StyleVersion.objects.filter(user=manager).exists():
            return
        StyleVersion.objects.filter(user=manager).delete()
        template = self.template_style()
        notes_snapshot = {str(s.id): s.notes for s in self.suppliers.values() if s.notes}
        versions = [{"source": "template", "style_md": template, "changelog": "Perfil base", "created_at": "T-30 11:00"}]
        for row in self.read("style_versions"):
            style_md = row.get("style_md")
            if not style_md and row.get("style_md_file"):
                style_md = (self.data_dir / row["style_md_file"]).read_text(encoding="utf-8")
            if row.get("source") == "template" or not style_md:
                continue
            style_md = self.retitle(style_md)
            self.validate_style(style_md)
            snapshot = row.get("notes_snapshot") or row.get("notes") or notes_snapshot
            if isinstance(snapshot, dict) and snapshot and not all(k.isdigit() for k in snapshot):
                snapshot = {str(self.suppliers[name].id): text for name, text in snapshot.items() if name in self.suppliers}
            versions.append({**row, "style_md": style_md, "notes_snapshot": snapshot})
        for version in versions:
            sv = StyleVersion.objects.create(
                user=manager,
                style_md=version["style_md"],
                notes_snapshot=version.get("notes_snapshot") or notes_snapshot,
                source=version.get("source", "manual"),
                changelog=version.get("changelog", ""),
            )
            created_at = self.rel_datetime(version.get("created_at"))
            if created_at:
                StyleVersion.objects.filter(pk=sv.pk).update(created_at=created_at)
        manager.style_md = versions[-1]["style_md"]
        manager.save(update_fields=["style_md"])

    @staticmethod
    def retitle(style_md: str) -> str:
        """`validate_style` requires the exact title of the template."""
        try:
            from agent.persona.style import TITLE
        except ImportError:
            return style_md
        lines = style_md.splitlines()
        for i, line in enumerate(lines):
            if line.startswith("# "):
                lines[i] = TITLE
                break
        else:
            lines.insert(0, TITLE)
        return "\n".join(lines) + "\n"

    def template_style(self) -> str:
        """Always the base template of `persona`, never `data/BOSS.md` (rule of 10/10)."""
        path = Path(settings.BASE_DIR) / "agent" / "persona" / "templates" / "style.base.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return "# Estilo del Gerente\n\nPendiente: completar con el onboarding.\n"

    def validate_style(self, style_md: str) -> None:
        try:
            from agent.persona.style import validate_style
        except ImportError:
            return
        names = list(self.suppliers)
        try:
            errors = validate_style(style_md, supplier_names=names)
        except TypeError:
            errors = validate_style(style_md)
        if errors:
            raise SeedError(f"style_versions.json: estilo inválido: {'; '.join(errors)}")

    # --- orchestration ----------------------------------------------------------------------

    def wipe(self):
        """Demo data only: never users, tokens, the WhatsApp onboarding state nor the style."""
        for model in (Message, Conversation, Alert, Decision, StatusChange, Payment, Delivery, ProgressReport, PurchaseOrderItem, PurchaseOrder, Requirement, OrderItem, Order, Rate, AllowedNumber, Supplier, ProductMaterial, Product, Material, Customer, Brand):
            model.objects.all().delete()
        from messaging.models import Turn

        Turn.objects.all().delete()

    ORDER_PATH = ["registered", "broken_down", "confirmed", "sourcing", "in_production", "ready", "delivered"]
    PO_PATH = ["suggested", "approved", "negotiating", "confirmed", "in_progress", "delivered"]
    ACTORS = {
        "registered": "comercial", "broken_down": "system", "confirmed": "produccion", "sourcing": "gerente",
        "in_production": "system", "ready": "produccion", "delivered": "produccion", "cancelled": "gerente",
        "suggested": "system", "approved": "gerente", "negotiating": "agent", "in_progress": "agent",
        "cancelled_by_supplier": "agent", "declined_by_supplier": "agent",
    }

    def load_status_history(self):
        """The JSON only states the current status; the timeline gets one plausible row per
        state already passed, spread between the issue date and T (or the delivery)."""
        for order in Order.objects.all():
            path = self.ORDER_PATH if order.status in self.ORDER_PATH else self.ORDER_PATH[:3] + [order.status]
            steps = path[: path.index(order.status) + 1]
            start = datetime.combine(order.issued_on, time(9, 0), tzinfo=LIMA)
            end = min(self.t, datetime.combine(order.estimated_on or self.t.date(), time(17, 0), tzinfo=LIMA)) if order.status == "delivered" else self.t
            self._history(order, steps, start, end, "order")
        for po in PurchaseOrder.objects.select_related("supplier"):
            path = self.PO_PATH if po.status in self.PO_PATH else self.PO_PATH[:5] + [po.status]
            steps = path[: path.index(po.status) + 1]
            if po.supplier.is_in_house:
                steps = [s for i, s in enumerate(steps) if i == len(steps) - 1 or s not in ("approved", "negotiating")]
            anchor = po.committed_on or po.internal_due_on or self.t.date()
            start = datetime.combine(anchor - timedelta(days=po.supplier.lead_time_days + 2), time(10, 0), tzinfo=LIMA)
            last_delivery = po.deliveries.order_by("-received_at").first()
            end = last_delivery.received_at if po.status == "delivered" and last_delivery else self.t
            self._history(po, steps, min(start, end - timedelta(hours=1)), end, "purchase_order")

    def _history(self, obj, steps, start, end, target):
        if not steps:
            return
        span = max((end - start) / max(len(steps) - 1, 1), timedelta(minutes=30)) if len(steps) > 1 else timedelta(0)
        for index, status in enumerate(steps):
            at = start + span * index if index < len(steps) - 1 else end
            StatusChange.objects.create(status=status, at=min(at, end), actor=self.ACTORS.get(status, "system"), **{target: obj})

    def finish(self):
        """Wires what the JSON cannot: the conversation of each live purchase order and the
        critical path of every order."""
        from messaging.services import conversation_for_supplier
        from operations.services import compute_critical_path

        for po in PurchaseOrder.objects.filter(status__in=PurchaseOrder.OPEN_STATUSES, conversation__isnull=True).select_related("supplier"):
            conversation = conversation_for_supplier(po.supplier)
            if conversation:
                po.conversation = conversation
                po.save(update_fields=["conversation"])
        for order in Order.objects.all():
            fixed = (order.estimated_on, order.risk, order.risk_reason)
            compute_critical_path(order)
            if fixed[0]:  # The JSON decides the demo's dates and risk; keep them.
                Order.objects.filter(pk=order.pk).update(estimated_on=fixed[0], risk=fixed[1], risk_reason=fixed[2])


def settings_env(name: str) -> str:
    import os

    return os.environ.get(name, "")
