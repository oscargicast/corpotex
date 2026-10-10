"""Suppliers and workshops with their historical prices. Phone numbers live in
`messaging.AllowedNumber` (ADR 0016); scores are computed from closed purchase orders."""

from django.contrib.postgres.fields import ArrayField
from django.db import models

from core.models import Material, Product, TimeStamped


class SupplierKind(models.TextChoices):
    MATERIAL = "material", "Insumos"
    WORKSHOP = "workshop", "Taller"
    FINISHED = "finished", "Producto terminado"


class Currency(models.TextChoices):
    PEN = "PEN", "PEN"
    USD = "USD", "USD"


class Supplier(TimeStamped):
    class Source(models.TextChoices):
        REGISTERED = "registered", "Registrado"
        SELF_REGISTERED = "self_registered", "Autoregistro"
        EXTERNAL = "external", "Fuente externa"

    class Status(models.TextChoices):
        ACTIVE = "active", "Activo"
        PENDING_REVIEW = "pending_review", "Por revisar"
        INACTIVE = "inactive", "Inactivo"

    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=20, choices=SupplierKind.choices)
    specialties = ArrayField(models.CharField(max_length=60), default=list, blank=True)
    city = models.CharField(max_length=80, blank=True)
    address = models.CharField(max_length=200, blank=True)
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)
    is_in_house = models.BooleanField(default=False, help_text="Corpotex's own plant.")
    weekly_capacity = models.PositiveIntegerField(null=True, blank=True)
    lead_time_days = models.PositiveSmallIntegerField(default=7)
    follow_up_every_hours = models.PositiveSmallIntegerField(default=48)
    currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.PEN)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.REGISTERED)
    source_detail = models.JSONField(
        null=True, blank=True, help_text="url and excerpt of an external source; no prompt reads it."
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    notes = models.TextField(blank=True, help_text="How to treat them; approved style notes.")

    class Meta:
        verbose_name = "proveedor"
        verbose_name_plural = "proveedores"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


SUPPLIER_SOURCE = Supplier.Source.choices  # module-level for ENUM_NAME_OVERRIDES
SUPPLIER_STATUS = Supplier.Status.choices


class Rate(TimeStamped):
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="rates")
    material = models.ForeignKey(
        Material, null=True, blank=True, on_delete=models.PROTECT, related_name="rates"
    )
    product = models.ForeignKey(
        Product, null=True, blank=True, on_delete=models.PROTECT, related_name="rates"
    )
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    valid_from = models.DateField()

    class Meta:
        verbose_name = "tarifa"
        verbose_name_plural = "tarifas"
        ordering = ["-valid_from"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(material__isnull=False, product__isnull=True)
                    | models.Q(material__isnull=True, product__isnull=False)
                ),
                name="rate_material_xor_product",
            )
        ]
