# students/admin.py

from django.contrib import admin
from .models import AttendanceAlert, Student, StudentAttendance, TeacherAttendance


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = (
        "matricule",
        "full_name",
        "email",
        "is_active",
        "created_at",
    )

    list_filter = (
        "is_active",
        "created_at",
    )

    search_fields = (
        "matricule",
        "user__first_name",
        "user__last_name",
        "user__email",
    )

    readonly_fields = (
        "created_at",
    )

    def full_name(self, obj):
        return obj.user.get_full_name()
    full_name.short_description = "Nom complet"

    def email(self, obj):
        return obj.user.email


@admin.register(StudentAttendance)
class StudentAttendanceAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "academic_class",
        "schedule_event",
        "date",
        "status",
        "arrival_time",
        "branch",
        "recorded_by",
    )
    list_filter = (
        "status",
        "date",
        "academic_class",
        "schedule_event",
        "branch",
    )
    search_fields = (
        "student__matricule",
        "student__user__username",
        "student__inscription__candidature__first_name",
        "student__inscription__candidature__last_name",
        "recorded_by__username",
    )
    autocomplete_fields = ("student", "academic_class", "branch", "recorded_by")


@admin.register(TeacherAttendance)
class TeacherAttendanceAdmin(admin.ModelAdmin):
    list_display = (
        "teacher",
        "schedule_event",
        "date",
        "status",
        "arrival_time",
        "branch",
        "recorded_by",
    )
    list_filter = (
        "status",
        "date",
        "schedule_event",
        "branch",
    )
    search_fields = (
        "teacher__username",
        "teacher__first_name",
        "teacher__last_name",
        "recorded_by__username",
    )
    autocomplete_fields = ("teacher", "branch", "recorded_by")


@admin.register(AttendanceAlert)
class AttendanceAlertAdmin(admin.ModelAdmin):
    list_display = ("student", "alert_type", "count", "branch", "triggered_at", "is_resolved")
    list_filter = ("alert_type", "branch", "is_resolved", "triggered_at")
    search_fields = (
        "student__matricule",
        "student__inscription__candidature__first_name",
        "student__inscription__candidature__last_name",
    )
    autocomplete_fields = ("student", "branch")
