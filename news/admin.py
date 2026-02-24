from django.contrib import admin
from django.utils import timezone

from .models import News, Category, NewsImage, Program, ResultSession


# --------------------------------------------------
# CATEGORY ADMIN
# --------------------------------------------------
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("nom", "ordre", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("nom",)
    prepopulated_fields = {"slug": ("nom",)}
    ordering = ("ordre",)
    list_editable = ("ordre", "is_active")


# --------------------------------------------------
# NEWS IMAGE INLINE (GALERIE)
# --------------------------------------------------
class NewsImageInline(admin.TabularInline):
    model = NewsImage
    extra = 1
    fields = ("image", "alt_text", "ordre")
    ordering = ("ordre",)


# --------------------------------------------------
# NEWS ADMIN
# --------------------------------------------------
@admin.register(News)
class NewsAdmin(admin.ModelAdmin):

    list_display = (
        "titre",
        "categorie",
        "status",
        "published_at",
        "created_at",
    )

    list_filter = (
        "status",
        "categorie",
        "created_at",
    )

    search_fields = (
        "titre",
        "resume",
        "contenu",
    )

    prepopulated_fields = {"slug": ("titre",)}

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    inlines = [NewsImageInline]

    ordering = ("-published_at", "-created_at")

    fieldsets = (
        (
            "Contenu",
            {
                "fields": (
                    "titre",
                    "slug",
                    "categorie",
                    "resume",
                    "contenu",
                    "image",
                    "program",
                )
            },
        ),
        (
            "Publication",
            {
                "fields": (
                    "status",
                    "published_at",
                    "auteur",
                )
            },
        ),
        (
            "Métadonnées",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    # --------------------------------------------------
    # SÉCURISATION PUBLICATION
    # --------------------------------------------------
    def save_model(self, request, obj, form, change):

        # Si on publie sans date → on force la date
        if obj.status == obj.STATUS_PUBLISHED and not obj.published_at:
            obj.published_at = timezone.now()

        # Si pas d’auteur → on attribue l’admin connecté
        if not obj.auteur:
            obj.auteur = request.user

        super().save_model(request, obj, form, change)


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ("nom", "is_active", "created_at")
    prepopulated_fields = {"slug": ("nom",)}


@admin.register(ResultSession)
class ResultSessionAdmin(admin.ModelAdmin):

    list_display = (
        "titre",
        "type",
        "annee_academique",
        "annexe",
        "filiere",
        "classe",
        "is_published",
        "created_at",
    )

    list_filter = (
        "type",
        "annee_academique",
        "annexe",
        "is_published",
        "created_at",
    )

    search_fields = (
        "titre",
        "annexe",
        "filiere",
        "classe",
    )

    readonly_fields = ("created_at",)

    ordering = ("-annee_academique", "-created_at")

    fieldsets = (
        (
            "Informations générales",
            {
                "fields": (
                    "titre",
                    "type",
                    "annee_academique",
                )
            },
        ),
        (
            "Organisation académique",
            {
                "fields": (
                    "annexe",
                    "filiere",
                    "classe",
                )
            },
        ),
        (
            "Fichier officiel",
            {
                "fields": (
                    "fichier_pdf",
                    "is_published",
                )
            },
        ),
        (
            "Métadonnées",
            {
                "fields": (
                    "created_at",
                )
            },
        ),
    )