from django.contrib import admin

from . import models


@admin.register(models.Decision)
class DecisionAdmin(admin.ModelAdmin):
    list_display = ["id", "kind", "status", "summary", "resolved_by", "resolved_at"]
    list_filter = ["kind", "status"]
    filter_horizontal = ["purchase_orders"]


class AlertNotificationInline(admin.TabularInline):
    model = models.AlertNotification
    extra = 0


@admin.register(models.Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ["id", "kind", "severity", "status", "order", "purchase_order", "detected_at"]
    list_filter = ["kind", "severity", "status"]
    inlines = [AlertNotificationInline]


@admin.register(models.AlertNotification)
class AlertNotificationAdmin(admin.ModelAdmin):
    list_display = ["alert", "user", "turn", "sent_at"]
