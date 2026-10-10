from django.contrib import admin

from . import models


class RateInline(admin.TabularInline):
    model = models.Rate
    extra = 0


@admin.register(models.Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "city", "status", "source", "currency", "is_in_house"]
    list_filter = ["kind", "status", "source", "city"]
    search_fields = ["name"]
    inlines = [RateInline]


@admin.register(models.Rate)
class RateAdmin(admin.ModelAdmin):
    list_display = ["supplier", "material", "product", "unit_price", "valid_from"]
    list_filter = ["supplier"]
