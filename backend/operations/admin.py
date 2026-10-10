from django.contrib import admin

from . import models


class OrderItemInline(admin.TabularInline):
    model = models.OrderItem
    extra = 0


class RequirementInline(admin.TabularInline):
    model = models.Requirement
    extra = 0


@admin.register(models.Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["code", "customer", "brand", "status", "risk", "issued_on", "promised_on", "estimated_on"]
    list_filter = ["status", "risk", "brand"]
    search_fields = ["code", "customer__name"]
    inlines = [OrderItemInline, RequirementInline]


class PurchaseOrderItemInline(admin.TabularInline):
    model = models.PurchaseOrderItem
    extra = 0


class ProgressReportInline(admin.TabularInline):
    model = models.ProgressReport
    extra = 0


class PaymentInline(admin.TabularInline):
    model = models.Payment
    extra = 0


@admin.register(models.PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ["code", "supplier", "status", "internal_due_on", "committed_on", "next_follow_up_at"]
    list_filter = ["status", "supplier"]
    search_fields = ["code", "supplier__name"]
    readonly_fields = ["report_token"]
    inlines = [PurchaseOrderItemInline, ProgressReportInline, PaymentInline]


@admin.register(models.Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ["purchase_order", "qty_received", "qty_defective", "quality", "received_at"]


@admin.register(models.Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["purchase_order", "kind", "amount", "method", "paid_at"]
    list_filter = ["kind", "method"]


class RouteStopInline(admin.TabularInline):
    model = models.RouteStop
    extra = 0


@admin.register(models.Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ["id", "date", "status", "distance_km", "duration_min", "recalculated_from"]
    list_filter = ["status"]
    inlines = [RouteStopInline]


admin.site.register(models.Requirement)
admin.site.register(models.ProgressReport)
admin.site.register(models.RouteStop)
