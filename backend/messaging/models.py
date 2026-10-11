"""Allowlist, conversations (WhatsApp, simulator and the dashboard assistant), messages and
the turn queue (ADR 0010, 0016, 0017)."""

from django.conf import settings
from django.db import models

from core.models import TimeStamped
from suppliers.models import Supplier


class AllowedNumber(TimeStamped):
    """The only source of supplier phone numbers and the safety net: nothing outside this
    table, active, is ever answered (ADR 0001, 0016)."""

    phone = models.CharField(
        max_length=40, unique=True, help_text="JID digits without +, or sim-<slug> if simulated."
    )
    lid = models.CharField(max_length=40, blank=True, help_text="WhatsApp @lid id, when known.")
    name = models.CharField(max_length=80, blank=True, help_text="Owner, manager or contact name.")
    supplier = models.ForeignKey(
        Supplier, null=True, blank=True, on_delete=models.SET_NULL, related_name="numbers"
    )
    active = models.BooleanField(default=False)
    simulated = models.BooleanField(default=False, help_text="Simulator only, never WhatsApp.")

    class Meta:
        verbose_name = "número permitido"
        verbose_name_plural = "números permitidos"

    def __str__(self) -> str:
        return f"{self.phone} ({self.name or self.supplier or '-'})"

    @property
    def jid(self) -> str:
        return self.lid if self.lid else f"{self.phone}@s.whatsapp.net"


class Conversation(TimeStamped):
    class Channel(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"
        SIMULATOR = "simulator", "Simulador"
        DASHBOARD = "dashboard", "Asistente del dashboard"

    channel = models.CharField(max_length=20, choices=Channel.choices)
    allowed_number = models.ForeignKey(
        AllowedNumber, null=True, blank=True, on_delete=models.PROTECT, related_name="conversations"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="conversations",
        help_text="Dashboard assistant only.",
    )
    agent_session = models.CharField(max_length=120, blank=True, help_text="Agent SDK session id.")
    pending_action = models.JSONField(
        null=True, blank=True, help_text="{tool, args, turn_id} waiting for the user's confirmation."
    )

    class Meta:
        verbose_name = "conversación"
        verbose_name_plural = "conversaciones"
        constraints = [
            models.UniqueConstraint(
                fields=["channel", "allowed_number"],
                condition=models.Q(allowed_number__isnull=False),
                name="uniq_conversation_channel_number",
            ),
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(channel="dashboard"),
                name="uniq_dashboard_conversation_per_user",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(channel="dashboard", user__isnull=False, allowed_number__isnull=True)
                    | (~models.Q(channel="dashboard") & models.Q(user__isnull=True, allowed_number__isnull=False))
                ),
                name="conversation_owner_matches_channel",
            ),
        ]

    def __str__(self) -> str:
        owner = self.user or self.allowed_number
        return f"{self.channel}: {owner}"

    @property
    def supplier(self) -> Supplier | None:
        return self.allowed_number.supplier if self.allowed_number_id else None


class Message(TimeStamped):
    class Author(models.TextChoices):
        SUPPLIER = "supplier", "Proveedor"
        AGENT = "agent", "Agente"
        MANAGER = "manager", "Gerente"
        USER = "user", "Usuario del dashboard"

    class Status(models.TextChoices):
        RECEIVED = "received", "Recibido"
        PROCESSED = "processed", "Procesado"
        ERROR = "error", "Error"
        SENT = "sent", "Enviado"
        FAILED = "failed", "Fallido"

    INBOUND_AUTHORS = (Author.SUPPLIER, Author.USER)

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    author = models.CharField(max_length=10, choices=Author.choices)
    text = models.TextField(blank=True)
    media = models.FileField(upload_to="messages/", blank=True)
    external_id = models.CharField(
        max_length=120, unique=True, null=True, blank=True, help_text="WhatsApp id; avoids duplicates."
    )
    status = models.CharField(max_length=10, choices=Status.choices)
    error = models.TextField(blank=True)
    sent_at = models.DateTimeField(help_text="Real time.")
    read_at = models.DateTimeField(null=True, blank=True, help_text="Assistant messages only.")
    turn = models.ForeignKey(
        "Turn", null=True, blank=True, on_delete=models.SET_NULL, related_name="sent_messages"
    )
    action = models.JSONField(null=True, blank=True, help_text="Assistant card: tool or alert.")
    context = models.JSONField(null=True, blank=True, help_text="Dashboard view: path, view, id.")

    class Meta:
        verbose_name = "mensaje"
        verbose_name_plural = "mensajes"
        ordering = ["sent_at", "id"]
        indexes = [
            models.Index(
                fields=["conversation", "sent_at"],
                name="msg_received_idx",
                condition=models.Q(status="received"),
            ),
            models.Index(
                fields=["conversation"],
                name="msg_unread_assistant_idx",
                condition=models.Q(author="agent", read_at__isnull=True),
            ),
        ]

    @property
    def direction(self) -> str:
        return "inbound" if self.author in self.INBOUND_AUTHORS else "outbound"


class Turn(TimeStamped):
    """One agent run per conversation. At most one `pending` per conversation; `reason` is a
    trace only, the batch is built from fresh state (ADR 0010)."""

    class Reason(models.TextChoices):
        MESSAGE = "message", "Mensaje"
        DECISION = "decision", "Decisión"
        FOLLOW_UP = "follow_up", "Seguimiento"
        PURCHASE_ORDER_APPROVED = "purchase_order_approved", "Pedido aprobado"
        ALERT = "alert", "Alerta"
        WEB_REPORT = "web_report", "Reporte web"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        RUNNING = "running", "En curso"
        DONE = "done", "Hecho"
        ERROR = "error", "Error"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="turns")
    reason = models.CharField(max_length=30, choices=Reason.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.TextField(blank=True)
    available_at = models.DateTimeField(help_text="Real time.")
    follow_up = models.JSONField(
        null=True, blank=True, help_text="Set by the tick only (ADR 0027): kind, reason, mode and purchase_order_ids."
    )

    class Meta:
        verbose_name = "turno"
        verbose_name_plural = "turnos"
        ordering = ["available_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["conversation"],
                condition=models.Q(status="pending"),
                name="uniq_pending_turn_per_conversation",
            )
        ]
        indexes = [models.Index(fields=["status", "available_at"], name="turn_status_available_idx")]
