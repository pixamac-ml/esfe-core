from django.contrib import admin
from .models import RegistryEntry, Appointment, VisitorLog, DocumentReceipt, SecretaryTask

@admin.register(RegistryEntry)
class RegistryEntryAdmin(admin.ModelAdmin):
    list_display = (
        "registry_number",
        "entry_type",
        "visitor_name",
        "target_service",
        "priority",
        "created_at",
        "created_by",
        "status",
        "is_archived",
    )
    list_filter = ("status", "entry_type", "priority", "target_service", "branch", "is_archived", "is_active")
    search_fields = (
        "registry_number",
        "event_identifier",
        "title",
        "description",
        "entry_type",
        "visitor_name",
        "visitor_phone",
        "visitor_email",
        "motive",
        "related_student__matricule",
    )
    readonly_fields = ("registry_number", "daily_number", "event_identifier", "history")

@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("title", "person_name", "scheduled_at", "created_by", "assigned_to", "status")
    list_filter = ("status", "is_archived", "is_active")
    search_fields = ("title", "person_name", "email", "phone")

@admin.register(VisitorLog)
class VisitorLogAdmin(admin.ModelAdmin):
    list_display = ("full_name", "arrived_at", "departed_at", "status", "created_by")
    list_filter = ("status", "is_archived", "is_active")
    search_fields = ("full_name", "phone", "reason")

@admin.register(DocumentReceipt)
class DocumentReceiptAdmin(admin.ModelAdmin):
    list_display = ("title", "submitted_by_name", "received_at", "received_by", "status", "is_archived")
    list_filter = ("status", "is_archived", "is_active")
    search_fields = ("title", "submitted_by_name", "description")

@admin.register(SecretaryTask)
class SecretaryTaskAdmin(admin.ModelAdmin):
    list_display = ("title", "priority", "status", "assigned_to", "due_date", "created_at")
    list_filter = ("priority", "status", "is_archived", "is_active")
    search_fields = ("title", "description", "assigned_to__username")

