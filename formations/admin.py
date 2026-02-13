from django.contrib import admin

from .models import (
    Cycle,
    Diploma,
    Filiere,
    Programme,
    ProgrammeYear,
    RequiredDocument,
    ProgrammeRequiredDocument,
)

# ==================================================
# CYCLE (Licence / Master / Doctorat)
# ==================================================
@admin.register(Cycle)
class CycleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "min_duration_years",
        "max_duration_years",
        "is_active",
    )

    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("min_duration_years",)

    list_per_page = 25


# ==================================================
# DIPLÔME
# ==================================================
@admin.register(Diploma)
class DiplomaAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "level",
    )

    list_filter = ("level",)
    search_fields = ("name",)

    list_per_page = 25


# ==================================================
# FILIÈRE
# ==================================================
@admin.register(Filiere)
class FiliereAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "is_active",
    )

    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("name",)

    list_per_page = 25


# ==================================================
# INLINE : ANNÉES DU PROGRAMME
# ==================================================
class ProgrammeYearInline(admin.TabularInline):
    model = ProgrammeYear
    extra = 0
    ordering = ("year_number",)
    min_num = 1


# ==================================================
# INLINE : DOCUMENTS REQUIS PAR PROGRAMME
# ==================================================
class ProgrammeRequiredDocumentInline(admin.TabularInline):
    model = ProgrammeRequiredDocument
    extra = 0
    autocomplete_fields = ("document",)


# ==================================================
# PROGRAMME (FORMATION / SPÉCIALITÉ)
# ==================================================
@admin.register(Programme)
class ProgrammeAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "cycle",
        "filiere",
        "diploma_awarded",
        "duration_years",
        "is_active",
        "is_featured",
        "created_at",
    )

    list_filter = (
        "cycle",
        "filiere",
        "diploma_awarded",
        "is_active",
        "is_featured",
    )

    search_fields = (
        "title",
        "short_description",
        "description",
    )

    prepopulated_fields = {
        "slug": ("title",)
    }

    readonly_fields = (
        "created_at",
    )

    ordering = ("title",)

    inlines = (
        ProgrammeYearInline,
        ProgrammeRequiredDocumentInline,
    )

    list_per_page = 25

    fieldsets = (
        ("Identification", {
            "fields": (
                "title",
                "slug",
                "cycle",
                "filiere",
                "diploma_awarded",
            )
        }),
        ("Durée & statut", {
            "fields": (
                "duration_years",
                "is_active",
                "is_featured",
            )
        }),
        ("Descriptions", {
            "fields": (
                "short_description",
                "description",
            )
        }),
        ("Système", {
            "fields": (
                "created_at",
            )
        }),
    )


# ==================================================
# ANNÉES DU PROGRAMME (ADMIN DIRECT)
# ==================================================
@admin.register(ProgrammeYear)
class ProgrammeYearAdmin(admin.ModelAdmin):
    list_display = (
        "programme",
        "year_number",
    )

    list_filter = ("year_number",)
    search_fields = ("programme__title",)
    ordering = ("programme", "year_number")

    list_per_page = 25


# ==================================================
# DOCUMENTS REQUIS (GLOBAL)
# ==================================================
@admin.register(RequiredDocument)
class RequiredDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "is_mandatory",
    )

    list_filter = ("is_mandatory",)
    search_fields = ("name",)

    list_per_page = 25


# ==================================================
# LIAISON PROGRAMME ↔ DOCUMENT
# ==================================================
@admin.register(ProgrammeRequiredDocument)
class ProgrammeRequiredDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "programme",
        "document",
    )

    list_filter = ("programme",)
    search_fields = (
        "programme__title",
        "document__name",
    )

    autocomplete_fields = (
        "programme",
        "document",
    )

    list_per_page = 25
