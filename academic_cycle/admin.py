from django.contrib import admin

from . import models


@admin.register(models.BranchAcademicCycle)
class BranchAcademicCycleAdmin(admin.ModelAdmin):
    list_display = ("branch", "academic_year", "status", "activated_at", "closed_at", "updated_at")
    list_filter = ("status", "branch", "academic_year")
    search_fields = ("branch__name", "branch__code", "academic_year__name")


@admin.register(models.ClassCycleStatus)
class ClassCycleStatusAdmin(admin.ModelAdmin):
    list_display = ("academic_class", "branch_cycle", "status", "readiness_score", "has_blocking_anomaly")
    list_filter = ("status", "branch_cycle__branch", "branch_cycle__academic_year", "has_blocking_anomaly")
    search_fields = ("academic_class__name", "academic_class__level", "academic_class__programme__title")


@admin.register(models.AcademicClosureReport)
class AcademicClosureReportAdmin(admin.ModelAdmin):
    list_display = ("branch_cycle", "status", "total_classes", "completed_classes", "blocked_classes", "generated_at")
    list_filter = ("status", "branch_cycle__branch", "branch_cycle__academic_year")
    readonly_fields = ("generated_at",)


@admin.register(models.StudentYearDecision)
class StudentYearDecisionAdmin(admin.ModelAdmin):
    list_display = ("student", "academic_year", "branch", "decision", "is_final", "decided_at")
    list_filter = ("decision", "is_final", "branch", "academic_year")
    search_fields = ("student__matricule", "student__user__username", "student__user__email")


@admin.register(models.StudentAcademicDebt)
class StudentAcademicDebtAdmin(admin.ModelAdmin):
    list_display = ("student", "source_academic_year", "branch", "debt_type", "missing_credits", "status")
    list_filter = ("status", "debt_type", "branch", "source_academic_year")
    search_fields = ("student__matricule", "student__user__username")


@admin.register(models.AcademicDebtEvaluationSession)
class AcademicDebtEvaluationSessionAdmin(admin.ModelAdmin):
    list_display = ("title", "branch", "academic_year", "session_type", "status", "starts_at", "ends_at")
    list_filter = ("status", "session_type", "branch", "academic_year")
    search_fields = ("title",)


@admin.register(models.AcademicDebtEvaluation)
class AcademicDebtEvaluationAdmin(admin.ModelAdmin):
    list_display = ("student", "debt", "session", "grade", "is_validated", "validated_at")
    list_filter = ("is_validated", "session__branch", "session__academic_year")
    search_fields = ("student__matricule",)


@admin.register(models.StudentFinancialPosition)
class StudentFinancialPositionAdmin(admin.ModelAdmin):
    list_display = ("student", "academic_year", "branch", "remaining_amount", "status", "last_computed_at")
    list_filter = ("status", "branch", "academic_year")
    search_fields = ("student__matricule", "student__user__username")


@admin.register(models.StudentAccessPolicy)
class StudentAccessPolicyAdmin(admin.ModelAdmin):
    list_display = ("student", "academic_year", "branch", "access_level", "can_access_dashboard", "computed_at")
    list_filter = ("access_level", "branch", "academic_year")
    search_fields = ("student__matricule", "student__user__username")


@admin.register(models.AcademicReEnrollment)
class AcademicReEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "target_academic_year", "branch", "status", "activated_at")
    list_filter = ("status", "branch", "target_academic_year")
    search_fields = ("student__matricule", "token")


@admin.register(models.TransferRequest)
class TransferRequestAdmin(admin.ModelAdmin):
    list_display = ("student", "source_branch", "target_academic_year", "status", "submitted_at", "reviewed_at")
    list_filter = ("status", "source_branch", "target_academic_year")
    search_fields = ("student__matricule", "reason")


@admin.register(models.AcademicCorrectionRequest)
class AcademicCorrectionRequestAdmin(admin.ModelAdmin):
    list_display = ("request_type", "student", "branch", "academic_year", "status", "created_at")
    list_filter = ("status", "request_type", "branch", "academic_year")
    search_fields = ("student__matricule", "description")


@admin.register(models.AcademicAuditLog)
class AcademicAuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "object_type", "object_id", "actor", "branch", "academic_year", "created_at")
    list_filter = ("action", "branch", "academic_year")
    search_fields = ("object_type", "object_id", "actor__username", "student__matricule")
    readonly_fields = (
        "actor",
        "branch",
        "academic_year",
        "student",
        "action",
        "object_type",
        "object_id",
        "old_values",
        "new_values",
        "reason",
        "ip_address",
        "user_agent",
        "created_at",
    )
