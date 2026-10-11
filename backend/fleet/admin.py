from django.contrib import admin

from . import models


@admin.register(models.Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ["name", "plate", "kind", "capacity_units", "driver_name", "is_active", "last_seen_at"]
    list_filter = ["kind", "is_active"]
    search_fields = ["name", "plate", "driver_name"]


@admin.register(models.VehiclePosition)
class VehiclePositionAdmin(admin.ModelAdmin):
    list_display = ["vehicle", "recorded_at", "lat", "lng", "speed_kmh", "source"]
    list_filter = ["vehicle", "source"]
