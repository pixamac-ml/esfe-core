from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import (
    Institution,
    LegalPage,
    LegalSection,
    LegalSidebarBlock,
    LegalPageHistory,
)


# ==========================================================
# INSTITUTION
# ==========================================================

@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "city",
        "country",
        "phone",
        "email",
        "updated_at",
    )

    search_fields = ("name", "city", "email")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("Informations générales", {
            "fields": (
                "name",
                "short_name",
                "legal_status",
                "approval_number",
            )
        }),
        ("Coordonnées", {
            "fields": (
                "address",
                "city",
                "country",
                "phone",
                "email",
            )
        }),
        ("Hébergement", {
            "fields": (
                "hosting_provider",
                "hosting_location",
            )
        }),
        ("Métadonnées", {
            "fields": (
                "created_at",
                "updated_at",
            )
        }),
    )


# ==========================================================
# SECTIONS INLINE
# ==========================================================

class LegalSectionInline(admin.TabularInline):
    model = LegalSection
    extra = 1
    ordering = ("order",)
    fields = ("order", "title", "content")


class LegalSidebarInline(admin.TabularInline):
    model = LegalSidebarBlock
    extra = 1
    ordering = ("order",)
    fields = ("order", "title", "content")


# ==========================================================
# PAGE LÉGALE
# ==========================================================

@admin.register(LegalPage)
class LegalPageAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "page_type",
        "status",
        "version",
        "updated_at",
    )

    list_filter = ("page_type", "status")
    search_fields = ("title", "version")
    readonly_fields = ("created_at", "updated_at")

    inlines = [LegalSectionInline, LegalSidebarInline]

    fieldsets = (
        ("Informations principales", {
            "fields": (
                "page_type",
                "title",
                "introduction",
            )
        }),
        ("Publication", {
            "fields": (
                "status",
                "version",
            )
        }),
        ("Métadonnées", {
            "fields": (
                "created_at",
                "updated_at",
            )
        }),
    )


# ==========================================================
# HISTORIQUE (LECTURE SEULE)
# ==========================================================

@admin.register(LegalPageHistory)
class LegalPageHistoryAdmin(admin.ModelAdmin):

    list_display = ("page", "version", "created_at")
    list_filter = ("version",)
    search_fields = ("page__title", "version")
    readonly_fields = ("page", "version", "content_snapshot", "created_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
