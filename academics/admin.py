# ==================================================
# ADMIN CONFIGURATION
# ==================================================

from django.contrib import admin
from .models import AcademicEnrollment, AcademicYear, AcademicClass, Semester, EC, UE, ECGrade, ECChapter, ECContent

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


class ECContentInline(admin.TabularInline):
    model = ECContent
    extra = 0


@admin.register(ECChapter)
class ECChapterAdmin(admin.ModelAdmin):
    list_display = ("title", "ec", "order")
    list_filter = ("ec__ue__semester__academic_class",)
    search_fields = ("title", "ec__title", "ec__ue__title", "ec__ue__code")
    inlines = [ECContentInline]


@admin.register(ECContent)
class ECContentAdmin(admin.ModelAdmin):
    list_display = ("title", "chapter", "content_type", "order", "created_at")
    list_filter = ("content_type", "chapter__ec__ue__semester__academic_class")
    search_fields = ("title", "chapter__title", "chapter__ec__title", "chapter__ec__ue__code")
