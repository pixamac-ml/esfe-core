# ==================================================
# ADMIN CONFIGURATION
# ==================================================

from django.contrib import admin
from .models import (
    AcademicEnrollment,
    AcademicYear,
    AcademicClass,
    Semester,
    EC,
    UE,
    ECGrade,
    ECChapter,
    ECContent,
    StudentContentProgress,
    AcademicScheduleEvent,
    AcademicScheduleChangeLog,
    AcademicScheduleExecutionLog,
    AcademicBulletin,
    AcademicDiplomaAward,
    AcademicDebt,
    AcademicDecisionLog,
    LessonLog,
    WeeklyScheduleSlot,
    Language,
    Profession,
)

@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code")


@admin.register(Profession)
class ProfessionAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(AcademicClass)
class AcademicClassAdmin(admin.ModelAdmin):
    list_display = ("name", "programme", "branch", "academic_year", "level", "validation_threshold", "admissibility_gap", "is_active")
    list_filter = ("academic_year", "branch", "programme", "level")
    search_fields = ("name",)


@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ("academic_class", "number", "total_required_credits")
    list_filter = ("number", "academic_class__academic_year")
    search_fields = ("academic_class__name",)


class ECInline(admin.TabularInline):
    model = EC
    extra = 1


class ECChapterInline(admin.TabularInline):
    model = ECChapter
    extra = 0


@admin.register(UE)
class UEAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "semester")
    list_filter = ("semester",)
    search_fields = ("code", "title")
    inlines = [ECInline]


@admin.register(EC)
class ECAdmin(admin.ModelAdmin):
    list_display = ("title", "ue", "credit_required", "coefficient")
    list_filter = ("ue",)
    search_fields = ("title",)
    inlines = [ECChapterInline]


@admin.register(AcademicEnrollment)
class AcademicEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "programme", "branch", "academic_year", "is_active")
    list_filter = ("academic_year", "branch", "programme")
    search_fields = ("student__username",)


@admin.register(ECGrade)
class ECGradeAdmin(admin.ModelAdmin):
    list_display = (
        "enrollment",
        "ec",
        "note",
        "note_coefficient",
        "credit_obtained",
        "is_validated"
    )
    list_filter = ("is_validated",)
    readonly_fields = (
        "note_coefficient",
        "credit_obtained",
        "is_validated",
    )


@admin.register(AcademicBulletin)
class AcademicBulletinAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "student",
        "bulletin_type",
        "academic_year",
        "academic_class",
        "status",
        "average",
        "decision",
        "generated_at",
    )
    list_filter = ("bulletin_type", "status", "branch", "academic_year", "academic_class")
    search_fields = ("reference", "student__matricule", "student__user__username", "student__user__email")
    readonly_fields = ("reference", "snapshot", "generated_at", "published_at", "created_at", "updated_at")


@admin.register(AcademicDiplomaAward)
class AcademicDiplomaAwardAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "student",
        "diploma",
        "programme",
        "academic_year",
        "branch",
        "status",
        "final_average",
        "mention",
    )
    list_filter = ("status", "branch", "academic_year", "programme", "diploma")
    search_fields = ("reference", "student__matricule", "student__user__username", "programme__title", "diploma__name")
    readonly_fields = ("reference", "snapshot", "delivered_at", "created_at", "updated_at")


class ECContentInline(admin.StackedInline):
    model = ECContent
    extra = 0
    fields = ("title", "content_type", "file", "video_url", "text_content", "duration", "order", "is_active")


@admin.register(ECChapter)
class ECChapterAdmin(admin.ModelAdmin):
    list_display = ("title", "ec", "order")
    list_filter = ("ec__ue__semester__academic_class",)
    search_fields = ("title", "ec__title", "ec__ue__title", "ec__ue__code")
    inlines = [ECContentInline]


@admin.register(ECContent)
class ECContentAdmin(admin.ModelAdmin):
    list_display = ("title", "chapter", "content_type", "order", "is_active", "updated_at")
    list_filter = ("content_type", "is_active", "chapter__ec__ue__semester__academic_class")
    search_fields = ("title", "chapter__title", "chapter__ec__title", "chapter__ec__ue__code")
    ordering = ("chapter", "order", "id")


@admin.register(StudentContentProgress)
class StudentContentProgressAdmin(admin.ModelAdmin):
    list_display = ("student", "content", "progress_percent", "is_completed", "updated_at")
    list_filter = ("is_completed", "content__content_type", "content__chapter__ec__ue__semester__academic_class")
    search_fields = ("student__username", "student__email", "content__title", "content__chapter__title")
    readonly_fields = ("first_viewed_at", "updated_at")


class AcademicScheduleChangeLogInline(admin.TabularInline):
    model = AcademicScheduleChangeLog
    extra = 0
    readonly_fields = (
        "action_type",
        "old_start_datetime",
        "old_end_datetime",
        "new_start_datetime",
        "new_end_datetime",
        "old_status",
        "new_status",
        "reason",
        "changed_by",
        "changed_at",
    )
    can_delete = False


class AcademicScheduleExecutionLogInline(admin.TabularInline):
    model = AcademicScheduleExecutionLog
    extra = 0


@admin.register(AcademicScheduleEvent)
class AcademicScheduleEventAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "event_type",
        "academic_class",
        "teacher",
        "branch",
        "start_datetime",
        "end_datetime",
        "status",
        "is_active",
    )
    list_filter = (
        "event_type",
        "status",
        "is_active",
        "branch",
        "academic_year",
        "academic_class",
        "teacher",
        "start_datetime",
    )
    search_fields = ("title", "description", "location", "ec__title", "academic_class__name", "teacher__username")
    ordering = ("-start_datetime",)
    inlines = [AcademicScheduleChangeLogInline, AcademicScheduleExecutionLogInline]


@admin.register(AcademicScheduleChangeLog)
class AcademicScheduleChangeLogAdmin(admin.ModelAdmin):
    list_display = ("event", "action_type", "changed_by", "changed_at")
    list_filter = ("action_type", "event__branch", "event__academic_class", "event__teacher", "changed_at")
    search_fields = ("event__title", "reason", "changed_by__username")
    readonly_fields = (
        "event",
        "action_type",
        "old_start_datetime",
        "old_end_datetime",
        "new_start_datetime",
        "new_end_datetime",
        "old_status",
        "new_status",
        "reason",
        "changed_by",
        "changed_at",
    )


@admin.register(AcademicScheduleExecutionLog)
class AcademicScheduleExecutionLogAdmin(admin.ModelAdmin):
    list_display = ("event", "actual_teacher", "started_at", "ended_at", "is_completed", "completed_by")
    list_filter = ("is_completed", "event__branch", "event__academic_class", "event__teacher", "started_at")
    search_fields = ("event__title", "notes", "actual_teacher__username", "completed_by__username")


@admin.register(LessonLog)
class LessonLogAdmin(admin.ModelAdmin):
    list_display = (
        "academic_class",
        "ec",
        "teacher",
        "date",
        "start_time",
        "end_time",
        "status",
        "branch",
    )
    list_filter = (
        "status",
        "date",
        "academic_class",
        "branch",
        "teacher",
    )
    search_fields = (
        "academic_class__name",
        "academic_class__programme__title",
        "ec__title",
        "teacher__username",
        "teacher__first_name",
        "teacher__last_name",
        "content",
        "observations",
    )
    autocomplete_fields = (
        "academic_class",
        "ec",
        "teacher",
        "schedule_event",
        "branch",
        "created_by",
        "validated_by",
    )


@admin.register(WeeklyScheduleSlot)
class WeeklyScheduleSlotAdmin(admin.ModelAdmin):
    list_display = (
        "academic_class",
        "weekday",
        "start_time",
        "end_time",
        "ec",
        "teacher",
        "branch",
        "is_active",
    )
    list_filter = ("branch", "academic_year", "weekday", "is_active")
    search_fields = ("room", "academic_class__name", "ec__title", "teacher__username")
    autocomplete_fields = ("academic_class", "ec", "teacher", "branch", "academic_year", "created_by")


@admin.register(AcademicDebt)
class AcademicDebtAdmin(admin.ModelAdmin):
    list_display = (
        "enrollment",
        "ec",
        "semester",
        "academic_year",
        "academic_class",
        "score_original",
        "score_retake",
        "status",
        "carry_forward_to",
        "created_at",
    )
    list_filter = ("status", "academic_year", "academic_class", "semester")
    search_fields = (
        "enrollment__student__username",
        "enrollment__student__email",
        "ec__title",
    )
    readonly_fields = ("created_at", "cleared_at", "updated_at")
    autocomplete_fields = ("enrollment", "ec", "semester", "academic_year", "academic_class", "carry_forward_to")


@admin.register(AcademicDecisionLog)
class AcademicDecisionLogAdmin(admin.ModelAdmin):
    list_display = (
        "academic_class",
        "academic_year",
        "actor",
        "total_students",
        "validated_count",
        "admissible_count",
        "non_admis_count",
        "created_at",
    )
    list_filter = ("academic_year", "academic_class", "created_at")
    search_fields = (
        "academic_class__name",
        "actor__username",
    )
    readonly_fields = ("created_at", "details")
    autocomplete_fields = ("academic_class", "academic_year", "actor")
