"""The manager's pending decisions, the monitor's alerts and who was told about them (ADR 0017,
0020)."""

from django.conf import settings
from django.db import models

from core.models import TimeStamped
from operations.models import Order, PurchaseOrder


class Decision(TimeStamped):
    class Kind(models.TextChoices):
        APPROVE_ASSIGNMENT = "approve_assignment", "Aprobar asignación"
        PRICE = "price", "Precio"
        TERMS = "terms", "Términos"
        OTHER = "other", "Otro"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        APPROVED = "approved", "Aprobada"
        REJECTED = "rejected", "Rechazada"
        SUPPLIER_CHANGED = "supplier_changed", "Proveedor cambiado"
        CANCELLED = "cancelled", "Cancelada"

    kind = models.CharField(max_length=30, choices=Kind.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    purchase_orders = models.ManyToManyField(PurchaseOrder, related_name="decisions")
    conversation = models.ForeignKey(
        "messaging.Conversation",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="decisions",
        help_text="Empty when the matching created it.",
    )
    summary = models.CharField(max_length=300, help_text="What the manager reads.")
    detail = models.JSONField(default=dict, help_text="before, after and proposal.")
    note = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    communicated_at = models.DateTimeField(
        null=True, blank=True, help_text="The agent already told the supplier."
    )

    class Meta:
        verbose_name = "decisión"
        verbose_name_plural = "decisiones"
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.summary}"


class Alert(TimeStamped):
    class Kind(models.TextChoices):
        STALLED_PURCHASE_ORDER = "stalled_purchase_order", "Pedido estancado"
        DELAY = "delay", "Retraso"
        ORDER_IN_DANGER = "order_in_danger", "Orden en peligro"
        NO_RESPONSE = "no_response", "Sin respuesta"
        PAYMENT_DUE = "payment_due", "Pago vencido"
        INSTANCE_DOWN = "instance_down", "WhatsApp desconectado"
        NO_CHANNEL = "no_channel", "Proveedor sin canal"
        TURN_FAILED = "turn_failed", "Turno fallido"
        STYLE_REFRESH_FAILED = "style_refresh_failed", "Refresco de estilo fallido"
        DECISION_PENDING = "decision_pending", "Decisión pendiente"
        CLAUDE_DISCONNECTED = "claude_disconnected", "Claude desconectado"
        PURCHASE_SUGGESTED = "purchase_suggested", "Compra sugerida"

    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Advertencia"
        CRITICAL = "critical", "Crítica"

    class Status(models.TextChoices):
        OPEN = "open", "Abierta"
        ACKNOWLEDGED = "acknowledged", "Reconocida"
        RESOLVED = "resolved", "Resuelta"

    kind = models.CharField(max_length=30, choices=Kind.choices)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.WARNING)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.OPEN)
    order = models.ForeignKey(Order, null=True, blank=True, on_delete=models.CASCADE, related_name="alerts")
    purchase_order = models.ForeignKey(
        PurchaseOrder, null=True, blank=True, on_delete=models.CASCADE, related_name="alerts"
    )
    decision = models.ForeignKey(
        Decision, null=True, blank=True, on_delete=models.CASCADE, related_name="alerts"
    )
    text = models.CharField(max_length=300, help_text="Template text without prices or phones.")
    detail = models.JSONField(null=True, blank=True, help_text="Structured payload for the assistant, e.g. the purchase suggestion (ADR 0025).")
    detected_at = models.DateTimeField(help_text="Simulated time.")
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "alerta"
        verbose_name_plural = "alertas"
        ordering = ["-detected_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "order", "purchase_order", "decision"],
                condition=models.Q(status="open"),
                nulls_distinct=False,
                name="uniq_open_alert_per_target",
            )
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.text}"


class AlertNotification(TimeStamped):
    """One row per alert and user told through the assistant (ADR 0020)."""

    alert = models.ForeignKey(Alert, on_delete=models.CASCADE, related_name="notifications")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    turn = models.ForeignKey(
        "messaging.Turn", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    sent_at = models.DateTimeField(null=True, blank=True, help_text="Empty until the turn succeeds.")

    class Meta:
        verbose_name = "aviso de alerta"
        verbose_name_plural = "avisos de alerta"
