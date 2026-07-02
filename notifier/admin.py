from django.contrib import admin

from .models import NotificationEvent, NotificationMessage, DeliveryAttempt


@admin.register(NotificationEvent)
class NotificationEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "source_app", "actor", "recipient", "status", "created_at")
    list_filter = ("status", "source_app", "event_type", "created_at")
    search_fields = ("event_type", "source_app", "id")


@admin.register(NotificationMessage)
class NotificationMessageAdmin(admin.ModelAdmin):
    list_display = ("title", "recipient", "channel", "priority", "status", "read_at", "created_at")
    list_filter = ("channel", "priority", "status", "created_at")
    search_fields = ("title", "body", "recipient__username", "recipient__email")


@admin.register(DeliveryAttempt)
class DeliveryAttemptAdmin(admin.ModelAdmin):
    list_display = ("message", "channel", "provider", "status", "attempt_count", "sent_at", "delivered_at")
    list_filter = ("channel", "provider", "status", "created_at")
    search_fields = ("provider_message_id", "message__title", "error_message")
