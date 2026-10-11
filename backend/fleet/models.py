"""Vehicles that deliver customer orders and their sampled positions (ADR 0026)."""

from django.db import models

from core.models import TimeStamped


class Vehicle(TimeStamped):
    class Kind(models.TextChoices):
        VAN = "van", "Furgón"
        PICKUP = "pickup", "Camioneta"
        MOTORCYCLE = "motorcycle", "Moto"
        TRUCK = "truck", "Camión"

    name = models.CharField(max_length=60, unique=True)
    plate = models.CharField(max_length=20, blank=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.VAN)
    capacity_units = models.PositiveIntegerField(help_text="Garments it carries in one trip.")
    color = models.CharField(max_length=7, default="#0072B2", help_text="Hex colour on the map (Okabe-Ito palette).")
    driver_name = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)
    last_lat = models.FloatField(null=True, blank=True)
    last_lng = models.FloatField(null=True, blank=True)
    last_heading = models.FloatField(null=True, blank=True, help_text="Degrees from north, clockwise.")
    last_speed_kmh = models.FloatField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    # Simulator state (ADR 0026 §5): metres covered along the route in progress, the speed-up,
    # the tick, the wait at a stop, and the run each tick belongs to (a restart orphans the old chain).
    sim_active = models.BooleanField(default=False)
    sim_progress_m = models.FloatField(default=0)
    sim_speed_factor = models.FloatField(default=12)
    sim_interval_s = models.PositiveSmallIntegerField(default=3)
    sim_wait_until = models.DateTimeField(null=True, blank=True)
    sim_run = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "vehículo"
        verbose_name_plural = "vehículos"
        ordering = ["-capacity_units", "id"]

    def __str__(self) -> str:
        return self.name


class VehiclePosition(models.Model):
    class Source(models.TextChoices):
        SIMULATOR = "simulator", "Simulador"
        DEVICE = "device", "Dispositivo"
        MANUAL = "manual", "Manual"

    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="positions")
    route = models.ForeignKey("operations.Route", null=True, blank=True, on_delete=models.SET_NULL, related_name="positions")
    lat = models.FloatField()
    lng = models.FloatField()
    heading = models.FloatField(null=True, blank=True)
    speed_kmh = models.FloatField(null=True, blank=True)
    recorded_at = models.DateTimeField()
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.DEVICE)

    class Meta:
        verbose_name = "posición"
        verbose_name_plural = "posiciones"
        ordering = ["vehicle", "recorded_at"]
        indexes = [models.Index(fields=["vehicle", "recorded_at"], name="vehicle_position_time_idx")]
