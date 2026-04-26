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
)

@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(AcademicClass)
class AcademicClassAdmin(admin.ModelAdmin):
    list_display = ("name", "programme", "branch", "academic_year", "level", "is_active")
    list_filter = ("academic_year", "branch", "programme", "level")
    search_fields = ("name",)


@admin.register(Semester)
class SemesterAdmin(admin.ModelAdmin):
    list_display = ("academic_class", "number", "total_required_credits")
    list_filter = ("number", "academic_class__academic_year")


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
        "is_validated"
    )


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
