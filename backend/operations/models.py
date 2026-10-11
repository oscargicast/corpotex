"""Customer orders, their breakdown, purchase orders to suppliers, progress, deliveries,
payments and pickup routes. State transitions live in services, never in save()."""

import uuid

from django.conf import settings
from django.db import models

from core.models import Customer, Brand, Material, Product, TimeStamped
from suppliers.models import Supplier, SupplierKind


class Order(TimeStamped):
    class Status(models.TextChoices):
        REGISTERED = "registered", "Registrada"
        BROKEN_DOWN = "broken_down", "Desglosada"
        CONFIRMED = "confirmed", "Confirmada"
        SOURCING = "sourcing", "En abastecimiento"
        IN_PRODUCTION = "in_production", "En producción"
        READY = "ready", "Lista"
        DELIVERED = "delivered", "Entregada"
        CANCELLED = "cancelled", "Cancelada"

    class Stage(models.TextChoices):
        CUTTING = "cutting", "Corte"
        SUBLIMATION = "sublimation", "Sublimado"
        EMBROIDERY = "embroidery", "Bordado"
        SEWING = "sewing", "Costura"
        FINISHING = "finishing", "Acabado"

    class Risk(models.TextChoices):
        OK = "ok", "OK"
        AT_RISK = "at_risk", "En riesgo"
        IN_DANGER = "in_danger", "En peligro"

    code = models.CharField(max_length=40, unique=True, help_text="Code from the sales system.")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="orders")
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="orders")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REGISTERED)
    production_stage = models.CharField(max_length=20, choices=Stage.choices, blank=True)
    issued_on = models.DateField()
    promised_on = models.DateField(help_text="Promised to the customer.")
    notes = models.TextField(blank=True, help_text="Free text from the order form (ADR 0025 B).")
    needs_classification = models.BooleanField(default=False, help_text="Some item has no catalogue product yet (ADR 0025 C).")
    estimated_on = models.DateField(null=True, blank=True, help_text="From the critical path.")
    critical_path = models.JSONField(default=list)
    risk = models.CharField(max_length=20, choices=Risk.choices, default=Risk.OK)
    risk_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "orden"
        verbose_name_plural = "órdenes"
        ordering = ["-issued_on", "-id"]

    def __str__(self) -> str:
        return self.code


class OrderItem(TimeStamped):

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveIntegerField()
    sizes = models.JSONField(default=dict, help_text="Quantity per size.")
    color = models.CharField(max_length=60, blank=True)
    customization = models.CharField(max_length=200, blank=True, help_text="Free text: embroidery, sublimation, print, several at once.")
    description = models.TextField(blank=True, help_text="What the customer asked for when no catalogue product fits (ADR 0025 C).")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Sale price; empty when the form does not know it yet.")

    class Meta:
        verbose_name = "ítem de orden"
        verbose_name_plural = "ítems de orden"


class Requirement(TimeStamped):
    class Status(models.TextChoices):
        OPEN = "open", "Por pedir"
        ORDERED = "ordered", "Pedido"
        COVERED = "covered", "Cubierto"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="requirements")
    kind = models.CharField(max_length=20, choices=SupplierKind.choices)
    material = models.ForeignKey(
        Material, null=True, blank=True, on_delete=models.PROTECT, related_name="requirements"
    )
    product = models.ForeignKey(
        Product, null=True, blank=True, on_delete=models.PROTECT, related_name="requirements"
    )
    qty_needed = models.DecimalField(max_digits=12, decimal_places=2)
    qty_from_stock = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.OPEN, help_text="Materials wait as open until Produccion generates the consolidated purchase order (ADR 0025)."
    )

    class Meta:
        verbose_name = "requerimiento"
        verbose_name_plural = "requerimientos"

    @property
    def qty_to_order(self):
        return self.qty_needed - self.qty_from_stock


class PurchaseOrder(TimeStamped):
    class Status(models.TextChoices):
        SUGGESTED = "suggested", "Sugerido"
        APPROVED = "approved", "Aprobado"
        NEGOTIATING = "negotiating", "En negociación"
        CONFIRMED = "confirmed", "Confirmado"
        IN_PROGRESS = "in_progress", "En proceso"
        DELIVERED = "delivered", "Entregado"
        DECLINED_BY_SUPPLIER = "declined_by_supplier", "Rechazado por el proveedor"
        CANCELLED_BY_SUPPLIER = "cancelled_by_supplier", "Cancelado por el proveedor"
        CANCELLED = "cancelled", "Cancelado"

    OPEN_STATUSES = (
        Status.APPROVED,
        Status.NEGOTIATING,
        Status.CONFIRMED,
        Status.IN_PROGRESS,
    )

    code = models.CharField(max_length=40, unique=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    conversation = models.ForeignKey(
        "messaging.Conversation",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="purchase_orders",
        help_text="Chat where this purchase order is negotiated.",
    )
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.SUGGESTED)
    suggested_supplier = models.ForeignKey(
        Supplier, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    rationale = models.TextField(blank=True, help_text="Why this supplier (matching).")
    scores = models.JSONField(default=dict, help_text="Per-criterion score of the chosen supplier.")
    report_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    report_link_sent_at = models.DateTimeField(null=True, blank=True)
    redistributed_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="redistributed_into"
    )
    internal_due_on = models.DateField(null=True, blank=True, help_text="What we ask the supplier.")
    committed_on = models.DateField(null=True, blank=True, help_text="What the supplier agreed.")
    next_follow_up_at = models.DateTimeField(null=True, blank=True)
    terms = models.TextField(blank=True)
    rating = models.JSONField(
        null=True,
        blank=True,
        help_text="On close: delay_days, quality, defect_pct, price_vs_ref_pct, score, rated_at.",
    )

    class Meta:
        verbose_name = "pedido"
        verbose_name_plural = "pedidos"
        ordering = ["-id"]
        indexes = [
            models.Index(
                fields=["next_follow_up_at"],
                name="po_follow_up_open_idx",
                condition=models.Q(
                    status__in=["approved", "negotiating", "confirmed", "in_progress"]
                ),
            )
        ]

    def __str__(self) -> str:
        return self.code

    @property
    def kind(self) -> str:
        return self.supplier.kind


class PurchaseOrderItem(TimeStamped):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    requirement = models.ForeignKey(
        Requirement, on_delete=models.PROTECT, related_name="purchase_order_items"
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    qty_delivered = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = "ítem de pedido"
        verbose_name_plural = "ítems de pedido"


class ProgressReport(TimeStamped):
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name="progress_reports"
    )
    units_done = models.PositiveIntegerField()
    note = models.TextField(blank=True)
    photo = models.ImageField(upload_to="progress/", blank=True)
    message = models.ForeignKey(
        "messaging.Message", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    reported_at = models.DateTimeField()
    acknowledged_at = models.DateTimeField(
        null=True, blank=True, help_text="Web reports: the agent already acknowledged it."
    )

    class Meta:
        verbose_name = "avance"
        verbose_name_plural = "avances"
        ordering = ["-reported_at"]

    @property
    def source(self) -> str:
        return "whatsapp" if self.message_id else "web"


class Delivery(TimeStamped):
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="deliveries")
    qty_received = models.DecimalField(max_digits=12, decimal_places=2)
    qty_defective = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    quality = models.PositiveSmallIntegerField(help_text="1 to 5.")
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    received_at = models.DateTimeField()
    note = models.TextField(blank=True)

    class Meta:
        verbose_name = "entrega"
        verbose_name_plural = "entregas"


class Payment(TimeStamped):
    class Kind(models.TextChoices):
        ADVANCE = "advance", "Adelanto"
        BALANCE = "balance", "Saldo"

    class Method(models.TextChoices):
        YAPE = "yape", "Yape"
        TRANSFER = "transfer", "Transferencia"
        CASH = "cash", "Efectivo"

    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="payments")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=10, choices=Method.choices, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    receipt = models.FileField(upload_to="receipts/", blank=True)

    class Meta:
        verbose_name = "pago"
        verbose_name_plural = "pagos"

    @property
    def status(self) -> str:
        return "paid" if self.paid_at else "pending"

    @property
    def due_on(self):
        """Computed: the advance is due when the purchase order was confirmed (the payments are
        created then); the balance, on the last delivery or the committed date."""
        if self.kind == self.Kind.ADVANCE:
            return self.created_at.date() if self.created_at else None
        delivery = self.purchase_order.deliveries.order_by("-received_at").first()
        return delivery.received_at.date() if delivery else self.purchase_order.committed_on

    @property
    def is_overdue(self) -> bool:
        from core import clock

        due = self.due_on
        return bool(due and not self.paid_at and due < clock.today())


class StatusChange(models.Model):
    """One row per status transition of an order or a purchase order: the timeline the
    dashboard shows as "next step" (decision of 10/10 21:40)."""

    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.CASCADE, related_name="status_changes")
    purchase_order = models.ForeignKey(
        PurchaseOrder, null=True, blank=True, on_delete=models.CASCADE, related_name="status_changes"
    )
    status = models.CharField(max_length=30)
    at = models.DateTimeField()
    actor = models.CharField(max_length=60, blank=True, help_text='"system", "agent", a username or empty.')
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        verbose_name = "cambio de estado"
        verbose_name_plural = "cambios de estado"
        ordering = ["at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(order__isnull=False, purchase_order__isnull=True)
                    | models.Q(order__isnull=True, purchase_order__isnull=False)
                ),
                name="status_change_one_target",
            )
        ]

    @property
    def status_display(self) -> str:
        choices = Order.Status.choices if self.order_id else PurchaseOrder.Status.choices
        return dict(choices).get(self.status, self.status)


class Route(TimeStamped):
    class Status(models.TextChoices):
        PROPOSED = "proposed", "Propuesta"
        PLANNED = "planned", "Planificada"
        IN_PROGRESS = "in_progress", "En curso"
        COMPLETED = "completed", "Completada"
        REPLACED = "replaced", "Reemplazada"
        DISCARDED = "discarded", "Descartada"

    date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    distance_km = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    duration_min = models.PositiveIntegerField(default=0)
    path = models.JSONField(default=dict, help_text="GeoJSON LineString (straight lines).")
    recalculated_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="recalculated_into"
    )

    class Meta:
        verbose_name = "ruta"
        verbose_name_plural = "rutas"
        ordering = ["-date", "-id"]


class RouteStop(TimeStamped):
    class Kind(models.TextChoices):
        PLANT = "plant", "Planta"
        PICKUP = "pickup", "Recojo"  # Kept for old rows; nothing generates pickups since 10/10 23:35.
        DELIVERY = "delivery", "Entrega"

    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="stops")
    position = models.PositiveSmallIntegerField(help_text="0 and the last one are the plant (kind=plant).")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    purchase_order = models.ForeignKey(
        PurchaseOrder, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    name = models.CharField(max_length=160)
    address = models.CharField(max_length=200, blank=True)
    lat = models.FloatField()
    lng = models.FloatField()
    eta = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "parada"
        verbose_name_plural = "paradas"
        ordering = ["route", "position"]
        constraints = [
            models.UniqueConstraint(fields=["route", "position"], name="uniq_route_stop_position")
        ]
