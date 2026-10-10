from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from . import models


@admin.register(models.User)
class UserAdmin(DjangoUserAdmin):
    list_display = ["username", "first_name", "role", "is_staff", "is_active"]
    fieldsets = DjangoUserAdmin.fieldsets + (("Estilo", {"fields": ("style_md", "style_refreshed_at")}),)

    @admin.display(description="rol")
    def role(self, obj):
        return obj.role


@admin.register(models.Config)
class ConfigAdmin(admin.ModelAdmin):
    list_display = ["id", "clock_factor", "clock_paused", "buffer_days", "agent_user", "agent_phone"]

    def has_add_permission(self, request):
        return not models.Config.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(models.Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ["name", "description"]


@admin.register(models.Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "tax_id", "lat", "lng"]
    list_filter = ["kind"]


class ProductMaterialInline(admin.TabularInline):
    model = models.ProductMaterial
    extra = 0


@admin.register(models.Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["code", "name"]
    inlines = [ProductMaterialInline]


@admin.register(models.Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ["sku", "name", "kind", "unit", "stock"]
    list_filter = ["kind"]


@admin.register(models.OnboardingStyle)
class OnboardingStyleAdmin(admin.ModelAdmin):
    list_display = ["id", "status", "step", "since", "heartbeat_at"]

    def has_add_permission(self, request):
        return not models.OnboardingStyle.objects.exists()


@admin.register(models.StyleVersion)
class StyleVersionAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "source", "created_at"]
    list_filter = ["source"]
