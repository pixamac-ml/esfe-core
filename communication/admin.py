from django.contrib import admin

from .models import (
    CommunicationEvent,
    CommunicationNotification,
    CommunicationDelivery,
    Conversation,
    ConversationParticipant,
    ConversationMessage,
    MessageAttachment,
    MessageReadReceipt,
)


@admin.register(CommunicationEvent)
class CommunicationEventAdmin(admin.ModelAdmin):
    list_display = (
        "event_type",
        "source_app",
        "actor",
        "recipient",
        "status",
        "created_at",
    )
    list_filter = ("status", "source_app", "event_type", "created_at")
    search_fields = ("event_type", "source_app", "id")


@admin.register(CommunicationNotification)
class CommunicationNotificationAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "recipient",
        "channel",
        "priority",
        "status",
        "read_at",
        "created_at",
    )
    list_filter = ("channel", "priority", "status", "created_at")
    search_fields = ("title", "body", "recipient__username", "recipient__email")


@admin.register(CommunicationDelivery)
class CommunicationDeliveryAdmin(admin.ModelAdmin):
    list_display = (
        "notification",
        "channel",
        "provider",
        "status",
        "attempt_count",
        "sent_at",
        "delivered_at",
    )
    list_filter = ("channel", "provider", "status", "created_at")
    search_fields = ("provider_message_id", "notification__title", "error_message")


class ConversationParticipantInline(admin.TabularInline):
    model = ConversationParticipant
    extra = 0


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("subject", "conversation_type", "status", "created_by", "created_at")
    list_filter = ("conversation_type", "status", "created_at")
    search_fields = ("subject",)
    inlines = [ConversationParticipantInline]


@admin.register(ConversationMessage)
class ConversationMessageAdmin(admin.ModelAdmin):
    list_display = ("conversation", "author", "message_type", "created_at", "edited_at")
    list_filter = ("message_type", "created_at")
    search_fields = ("body", "author__username", "conversation__subject")


admin.site.register(MessageAttachment)
admin.site.register(MessageReadReceipt)
