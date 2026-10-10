"""Users and roles, the simulated clock, the catalogue and the manager's style.

Field names are the API contract (docs/backend/modelo-de-datos.md). Choice values are
English, labels are Spanish (ADR 0014).
"""

from django.contrib.auth.models import AbstractUser
from django.db import models


class TimeStamped(models.Model):
    """Audit timestamps in real time; business dates use `core.clock`."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


def _keep_created_at(instance: TimeStamped) -> None:
    """A singleton saved from a fresh instance would UPDATE `created_at` to NULL; keep the
    stored value (or stamp now on the first save)."""
    from django.utils import timezone

    if instance.created_at is None:
        stored = type(instance).objects.filter(pk=1).values_list("created_at", flat=True).first()
        instance.created_at = stored or timezone.now()


class Role(models.TextChoices):
    MANAGER = "manager", "Gerente"
    SALES = "sales", "Comercial"
    PRODUCTION = "production", "Producción"


# Django group name per role: the group name is an admin label, so it stays in Spanish.
ROLE_GROUPS = {
    Role.MANAGER: "Gerente",
    Role.SALES: "Comercial",
    Role.PRODUCTION: "Produccion",
}
GROUP_ROLES = {group: role for role, group in ROLE_GROUPS.items()}


class User(AbstractUser):
    style_md = models.TextField(blank=True, verbose_name="estilo (BOSS.md)")
    style_refreshed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    @property
    def role(self) -> str | None:
        """The role comes from the group; a user without a role group has none."""
        for group_name in self.groups.values_list("name", flat=True):
            if group_name in GROUP_ROLES:
                return GROUP_ROLES[group_name]
        return None


class Config(TimeStamped):
    """Single row. `load()` is the only way to get it."""

    clock_real_start = models.DateTimeField()
    clock_sim_start = models.DateTimeField()
    clock_factor = models.DecimalField(
        max_digits=8, decimal_places=2, default=1, help_text="Simulated minutes per real minute."
    )
    clock_paused = models.BooleanField(default=False)
    buffer_days = models.PositiveSmallIntegerField(default=5)
    decision_pending_hours = models.PositiveSmallIntegerField(default=12)
    stage_durations = models.JSONField(
        default=dict, help_text='Days per in-plant stage, e.g. {"cutting": 1, "sewing": 3}.'
    )
    agent_user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    agent_phone = models.CharField(max_length=20, blank=True, help_text="JID digits, no +.")
    plant_name = models.CharField(max_length=120, blank=True)
    plant_lat = models.FloatField(null=True, blank=True)
    plant_lng = models.FloatField(null=True, blank=True)
    onboarding = models.JSONField(default=dict)
    claude_connected_at = models.DateTimeField(null=True, blank=True)
    claude_last_error = models.TextField(blank=True)
    claude_last_error_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "configuración"
        verbose_name_plural = "configuración"

    def save(self, *args, **kwargs):
        self.pk = 1
        _keep_created_at(self)
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "Config":
        from django.utils import timezone

        now = timezone.now()
        config, _ = cls.objects.get_or_create(
            pk=1, defaults={"clock_real_start": now, "clock_sim_start": now}
        )
        return config


class Brand(TimeStamped):
    name = models.CharField(max_length=80, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = "marca"
        verbose_name_plural = "marcas"

    def __str__(self) -> str:
        return self.name


class Customer(TimeStamped):
    class Kind(models.TextChoices):
        COMPANY = "company", "Empresa"
        SCHOOL = "school", "Colegio"
        NGO = "ngo", "ONG"
        INDIVIDUAL = "individual", "Persona"

    name = models.CharField(max_length=160)
    tax_id = models.CharField(max_length=20, unique=True, null=True, blank=True, verbose_name="RUC")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    address = models.CharField(max_length=200, blank=True)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name = "cliente"
        verbose_name_plural = "clientes"

    def __str__(self) -> str:
        return self.name


class Product(TimeStamped):
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=160)
    image = models.ImageField(upload_to="products/", blank=True)

    class Meta:
        verbose_name = "producto"
        verbose_name_plural = "productos"

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class Material(TimeStamped):
    class Kind(models.TextChoices):
        FABRIC = "fabric", "Tela"
        BUTTON = "button", "Botón"
        ZIPPER = "zipper", "Cierre"
        COLLAR_CUFF = "collar_cuff", "Cuello y puño"
        OTHER = "other", "Otro"

    class Unit(models.TextChoices):
        M = "m", "m"
        KG = "kg", "kg"
        UNIT = "unit", "unidad"

    sku = models.CharField(max_length=40, unique=True, help_text="Corpotex's internal code.")
    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    unit = models.CharField(max_length=10, choices=Unit.choices)
    stock = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    image = models.ImageField(upload_to="materials/", blank=True)

    class Meta:
        verbose_name = "insumo"
        verbose_name_plural = "insumos"

    def __str__(self) -> str:
        return f"{self.sku} {self.name}"


class ProductMaterial(TimeStamped):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="materials")
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="products")
    qty_per_unit = models.DecimalField(max_digits=12, decimal_places=4)

    class Meta:
        verbose_name = "insumo por producto"
        verbose_name_plural = "insumos por producto"
        constraints = [
            models.UniqueConstraint(fields=["product", "material"], name="uniq_product_material")
        ]


class OnboardingStyle(TimeStamped):
    """Single row: the draft of the manager's style while the onboarding runs."""

    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Sin iniciar"
        EXTRACTING = "extracting", "Extrayendo"
        DRAFT = "draft", "Borrador"
        APPROVED = "approved", "Aprobado"
        ERROR = "error", "Error"

    class Step(models.TextChoices):
        SUPPLIERS = "suppliers", "Proveedores"
        MERGING = "merging", "Juntando"

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_STARTED)
    since = models.DateField(null=True, blank=True)
    step = models.CharField(max_length=20, choices=Step.choices, blank=True)
    progress = models.JSONField(default=dict, help_text="Per-supplier status.")
    draft_style_md = models.TextField(blank=True)
    draft_notes = models.JSONField(default=dict, help_text="supplier_id -> notes")
    draft_source = models.CharField(
        max_length=20, blank=True, help_text="StyleVersion.Source the draft came from (onboarding or template)."
    )
    temp_transcript = models.JSONField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "onboarding de estilo"
        verbose_name_plural = "onboarding de estilo"

    def save(self, *args, **kwargs):
        self.pk = 1
        _keep_created_at(self)
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "OnboardingStyle":
        row, _ = cls.objects.get_or_create(pk=1)
        return row


class StyleVersion(TimeStamped):
    class Source(models.TextChoices):
        ONBOARDING = "onboarding", "Onboarding"
        DAILY = "daily", "Diario"
        TEMPLATE = "template", "Plantilla"
        MANUAL = "manual", "Manual"
        ROLLBACK = "rollback", "Vuelta atrás"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="style_versions")
    style_md = models.TextField()
    notes_snapshot = models.JSONField(default=dict, help_text="supplier_id -> notes")
    source = models.CharField(max_length=20, choices=Source.choices)
    changelog = models.TextField(blank=True)

    class Meta:
        verbose_name = "versión de estilo"
        verbose_name_plural = "versiones de estilo"
        ordering = ["-created_at"]
