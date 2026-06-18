# students/admin.py

from django.contrib import admin
from django.utils import timezone
from .models import (
    AttendanceAlert, AttendanceRollSheet,
    CarteEtudiant, Student, StudentAttendance,
    StudentCase, StudentCaseNote, TeacherAttendance, VerificationLog,
)


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


@admin.register(AttendanceRollSheet)
class AttendanceRollSheetAdmin(admin.ModelAdmin):
    list_display = (
        "academic_class",
        "date",
        "status",
        "branch",
        "schedule_event",
        "validated_at",
        "updated_by",
    )
    list_filter = ("status", "date", "branch")
    search_fields = ("academic_class__name", "academic_class__programme__title", "academic_class__level")
    autocomplete_fields = ("branch", "academic_class", "schedule_event", "validated_by", "updated_by")


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


@admin.register(CarteEtudiant)
class CarteEtudiantAdmin(admin.ModelAdmin):
    list_display = ("etudiant", "annee", "code_annexe", "statut", "date_expiration", "carte_valide")
    list_filter = ("statut", "annee", "code_annexe")
    search_fields = ("etudiant__matricule", "etudiant__inscription__candidature__last_name")
    readonly_fields = ("date_emission", "created_at")
    actions = ["revoquer_cartes", "marquer_perdues"]

    @admin.display(boolean=True, description="Valide")
    def carte_valide(self, obj):
        return obj.is_valide

    @admin.action(description="Révoquer les cartes sélectionnées")
    def revoquer_cartes(self, request, queryset):
        queryset.update(statut="revoquee")

    @admin.action(description="Marquer comme perdue")
    def marquer_perdues(self, request, queryset):
        queryset.update(statut="perdue")


@admin.register(VerificationLog)
class VerificationLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "carte", "ip", "code_tente", "resultat")
    list_filter = ("resultat", "created_at")
    readonly_fields = ("created_at",)


class StudentCaseNoteInline(admin.TabularInline):
    model = StudentCaseNote
    extra = 1
    readonly_fields = ("author", "created_at")


@admin.register(StudentCase)
class StudentCaseAdmin(admin.ModelAdmin):
    list_display = ("title", "student", "case_type", "priority", "status", "branch", "created_at")
    list_filter = ("priority", "status", "case_type", "branch")
    search_fields = (
        "title",
        "student__matricule",
        "student__inscription__candidature__first_name",
        "student__inscription__candidature__last_name",
    )
    readonly_fields = ("created_at", "updated_at", "resolved_at")
    inlines = [StudentCaseNoteInline]

