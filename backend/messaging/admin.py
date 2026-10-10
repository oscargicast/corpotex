from django.contrib import admin

from . import models


@admin.register(models.AllowedNumber)
class AllowedNumberAdmin(admin.ModelAdmin):
    list_display = ["phone", "name", "supplier", "active", "simulated", "lid"]
    list_filter = ["active", "simulated"]
    search_fields = ["phone", "name", "supplier__name"]


@admin.register(models.Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ["id", "channel", "allowed_number", "user", "agent_session"]
    list_filter = ["channel"]


@admin.register(models.Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ["id", "conversation", "author", "status", "sent_at", "turn"]
    list_filter = ["author", "status", "conversation__channel"]
    search_fields = ["text", "external_id"]


@admin.register(models.Turn)
class TurnAdmin(admin.ModelAdmin):
    list_display = ["id", "conversation", "reason", "status", "attempts", "available_at"]
    list_filter = ["status", "reason"]
