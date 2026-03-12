from django.contrib import admin

from .models import (
    Cycle,
    Diploma,
    Filiere,
    Programme,
    ProgrammeYear,
    Fee,
    RequiredDocument,
    ProgrammeRequiredDocument,
    ProgrammeQuickFact,
    ProgrammeTab,
    ProgrammeSection,
    CompetenceBlock,
    CompetenceItem,
)


# ==================================================
# INLINE : FAITS RAPIDES
# ==================================================
class ProgrammeQuickFactInline(admin.TabularInline):
    model = ProgrammeQuickFact
    extra = 0
    ordering = ("order",)
    min_num = 0


# ==================================================
# INLINE : ITEMS DE COMPÉTENCES
# ==================================================
class CompetenceItemInline(admin.TabularInline):
    model = CompetenceItem
    extra = 0
    ordering = ("order",)
    min_num = 0


# ==================================================
# INLINE : BLOCS DE COMPÉTENCES
# ==================================================
class CompetenceBlockInline(admin.TabularInline):
    model = CompetenceBlock
    extra = 0
    ordering = ("order",)
    min_num = 0


# ==================================================
# INLINE : SECTIONS DANS UN ONGLET
# ==================================================
class ProgrammeSectionInline(admin.TabularInline):
    model = ProgrammeSection
    extra = 0
    ordering = ("order",)
    min_num = 0


# ==================================================
# INLINE : ONGLETS
# ==================================================
class ProgrammeTabInline(admin.TabularInline):
    model = ProgrammeTab
    extra = 0
    ordering = ("order",)
    min_num = 0


# ==================================================
# INLINE : ANNÉES DU PROGRAMME
# ==================================================
class ProgrammeYearInline(admin.TabularInline):
    model = ProgrammeYear
    extra = 0
    ordering = ("year_number",)
    min_num = 1


# ==================================================
# INLINE : FRAIS PAR ANNÉE
# ==================================================
class FeeInline(admin.TabularInline):
    model = Fee
    extra = 0
    ordering = ("amount",)
    min_num = 0


# ==================================================
# INLINE : DOCUMENTS REQUIS PAR PROGRAMME
# ==================================================
class ProgrammeRequiredDocumentInline(admin.TabularInline):
    model = ProgrammeRequiredDocument
    extra = 0
    autocomplete_fields = ("document",)


# ==================================================
# CYCLE
# ==================================================
@admin.register(Cycle)
class CycleAdmin(admin.ModelAdmin):
    list_display = ("name", "theme", "min_duration_years", "max_duration_years", "is_active")
    list_filter = ("theme", "is_active")
    search_fields = ("name",)
    ordering = ("min_duration_years",)
    prepopulated_fields = {"slug": ("name",)}
    fieldsets = (
        ("Identification", {"fields": ("name", "slug", "description")}),
        ("Configuration visuelle", {"fields": ("theme",)}),
        ("Durée & statut", {"fields": ("min_duration_years", "max_duration_years", "is_active")}),
    )
    list_per_page = 25


# ==================================================
# DIPLÔME
# ==================================================
@admin.register(Diploma)
class DiplomaAdmin(admin.ModelAdmin):
    list_display = ("name", "level")
    list_filter = ("level",)
    search_fields = ("name",)
    list_per_page = 25


# ==================================================
# FILIÈRE
# ==================================================
@admin.register(Filiere)
class FiliereAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("name",)
    list_per_page = 25


# ==================================================
# PROGRAMME
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
    list_filter = ("cycle", "filiere", "diploma_awarded", "is_active", "is_featured")
    search_fields = (
        "title",
        "short_description",
        "description",
        "learning_outcomes",
        "career_opportunities",
        "program_structure",
    )
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ("created_at", "updated_at")
    ordering = ("title",)

    inlines = (
        ProgrammeYearInline,
        ProgrammeRequiredDocumentInline,
        ProgrammeQuickFactInline,
        ProgrammeTabInline,
        CompetenceBlockInline,
    )

    fieldsets = (
        ("Identification", {
            "fields": ("title", "slug", "cycle", "filiere", "diploma_awarded")
        }),
        ("Durée & statut", {
            "fields": ("duration_years", "is_active", "is_featured")
        }),
        ("Présentation générale", {
            "fields": ("short_description", "description")
        }),
        # =============================================
        # SECTION OBJECTIFS - VISIBLE PAR DÉFAUT
        # =============================================
        ("Objectifs de la formation (JSON)", {
            "fields": ("learning_outcomes",),
            "description": """
            <strong>Format JSON requis :</strong><br>
            <code>[{"icon": "chart", "color": "secondary", "title": "Titre", "desc": "Description"}]</code><br><br>
            <strong>Icônes disponibles :</strong> chart, users, trending, lightbulb, target, briefcase, globe, code<br>
            <strong>Couleurs disponibles :</strong> secondary (turquoise), accent (orange), primary (bleu)
            """,
        }),
        ("Autres contenus Landing Page", {
            "fields": ("career_opportunities", "program_structure", "illustration"),
            "classes": ("collapse",),
        }),
        ("Système", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )
    list_per_page = 25


# ==================================================
# ANNÉES DU PROGRAMME
# ==================================================
@admin.register(ProgrammeYear)
class ProgrammeYearAdmin(admin.ModelAdmin):
    list_display = ("programme", "year_number")
    list_filter = ("year_number",)
    search_fields = ("programme__title",)
    ordering = ("programme", "year_number")
    inlines = (FeeInline,)
    list_per_page = 25


# ==================================================
# FRAIS
# ==================================================
@admin.register(Fee)
class FeeAdmin(admin.ModelAdmin):
    list_display = ("programme_year", "label", "amount", "due_month")
    list_filter = ("due_month",)
    search_fields = ("programme_year__programme__title", "label")
    ordering = ("programme_year", "amount")
    list_per_page = 25


# ==================================================
# DOCUMENTS REQUIS
# ==================================================
@admin.register(RequiredDocument)
class RequiredDocumentAdmin(admin.ModelAdmin):
    list_display = ("name", "is_mandatory")
    list_filter = ("is_mandatory",)
    search_fields = ("name",)
    list_per_page = 25


# ==================================================
# LIAISON PROGRAMME ↔ DOCUMENT
# ==================================================
@admin.register(ProgrammeRequiredDocument)
class ProgrammeRequiredDocumentAdmin(admin.ModelAdmin):
    list_display = ("programme", "document")
    list_filter = ("programme",)
    search_fields = ("programme__title", "document__name")
    autocomplete_fields = ("programme", "document")
    list_per_page = 25


# ==================================================
# FAITS RAPIDES
# ==================================================
@admin.register(ProgrammeQuickFact)
class ProgrammeQuickFactAdmin(admin.ModelAdmin):
    list_display = ("programme", "icon", "label", "value", "order")
    list_filter = ("icon",)
    search_fields = ("programme__title", "label", "value")
    ordering = ("programme", "order")
    list_per_page = 25


# ==================================================
# ONGLETS
# ==================================================
@admin.register(ProgrammeTab)
class ProgrammeTabAdmin(admin.ModelAdmin):
    list_display = ("programme", "title", "tab_type", "slug", "order", "is_active")
    list_filter = ("tab_type", "is_active")
    search_fields = ("programme__title", "title")
    ordering = ("programme", "order")
    inlines = (ProgrammeSectionInline,)
    list_per_page = 25


# ==================================================
# SECTIONS
# ==================================================
@admin.register(ProgrammeSection)
class ProgrammeSectionAdmin(admin.ModelAdmin):
    list_display = ("tab", "section_type", "title", "order")
    list_filter = ("section_type",)
    search_fields = ("tab__title", "title", "content")
    ordering = ("tab", "order")
    list_per_page = 25


# ==================================================
# BLOCS DE COMPÉTENCES
# ==================================================
@admin.register(CompetenceBlock)
class CompetenceBlockAdmin(admin.ModelAdmin):
    list_display = ("programme", "title", "order")
    search_fields = ("programme__title", "title", "description")
    ordering = ("programme", "order")
    inlines = (CompetenceItemInline,)
    list_per_page = 25


# ==================================================
# ITEMS DE COMPÉTENCES
# ==================================================
@admin.register(CompetenceItem)
class CompetenceItemAdmin(admin.ModelAdmin):
    list_display = ("block", "title", "order")
    search_fields = ("block__title", "title", "description")
    ordering = ("block", "order")
    list_per_page = 25