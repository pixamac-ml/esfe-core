from django.contrib import admin

from portal.models import (
    AccountSupportState,
    ArchiveBatch,
    BranchITSettings,
    SupportAuditLog,
    SupportTicket,
    SupportTicketComment,
    TeacherDashboardPreference,
)


@admin.register(SupportAuditLog)
class SupportAuditLogAdmin(admin.ModelAdmin):
    list_display = ("action_type", "target_label", "actor", "branch", "created_at")
    list_filter = ("action_type", "branch", "created_at")
    search_fields = ("target_label", "details", "actor__username", "target_user__username")
    date_hierarchy = "created_at"


class SupportTicketCommentInline(admin.TabularInline):
    model = SupportTicketComment
    extra = 0
    readonly_fields = ("author", "body", "created_at")
    can_delete = False


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "category", "priority", "status", "branch", "assigned_to", "created_at")
    list_filter = ("status", "priority", "category", "branch", "created_at")
    search_fields = ("title", "description", "requester_user__username", "student__matricule")
    date_hierarchy = "created_at"
    inlines = [SupportTicketCommentInline]


@admin.register(AccountSupportState)
class AccountSupportStateAdmin(admin.ModelAdmin):
    list_display = ("user", "is_suspended", "is_blocked", "must_change_password", "failed_login_count", "updated_at")
    list_filter = ("is_suspended", "is_blocked", "must_change_password", "updated_at")
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__email", "note")


@admin.register(BranchITSettings)
class BranchITSettingsAdmin(admin.ModelAdmin):
    list_display = ("branch", "validation_threshold", "active_academic_year", "updated_at")
    search_fields = ("branch__name", "branch__code", "active_academic_year")


@admin.register(ArchiveBatch)
class ArchiveBatchAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "archive_type",
        "status",
        "branch",
        "academic_year",
        "academic_class",
        "classes_count",
        "students_count",
        "created_by",
        "created_at",
    )
    list_filter = ("status", "archive_type", "branch", "academic_year", "created_at")
    search_fields = ("reason", "created_by__username", "academic_class__level", "academic_year__name")
    readonly_fields = (
        "archive_type",
        "status",
        "branch",
        "academic_year",
        "academic_class",
        "reason",
        "snapshot",
        "classes_count",
        "enrollments_count",
        "inscriptions_count",
        "students_count",
        "grades_count",
        "payments_count",
        "created_by",
        "restored_by",
        "created_at",
        "restored_at",
    )
    date_hierarchy = "created_at"


@admin.register(TeacherDashboardPreference)
class TeacherDashboardPreferenceAdmin(admin.ModelAdmin):
    list_display = ("teacher", "branch", "default_section", "dark_mode", "sidebar_collapsed", "updated_at")
    list_filter = ("branch", "default_section", "dark_mode", "sidebar_collapsed", "compact_mode")
    search_fields = ("teacher__username", "teacher__first_name", "teacher__last_name", "branch__name", "branch__code")
