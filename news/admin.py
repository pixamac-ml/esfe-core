from django.contrib import admin
from django.utils import timezone

from .models import News, Category, NewsImage, Program, ResultSession
from django.utils.html import format_html
from .models import Event, EventType, MediaItem

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



@admin.register(EventType)
class EventTypeAdmin(admin.ModelAdmin):

    list_display = ("name", "slug", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("name",)


class MediaItemInline(admin.TabularInline):

    model = MediaItem
    extra = 1
    fields = (
        "media_type",
        "image",
        "thumbnail_preview",
        "video_url",
        "caption",
        "is_featured",
    )

    readonly_fields = ("thumbnail_preview",)

    def thumbnail_preview(self, obj):
        if obj.thumbnail:
            return format_html(
                '<img src="{}" width="80" style="border-radius:6px;" />',
                obj.thumbnail.url
            )
        return "-"
    thumbnail_preview.short_description = "Aperçu"


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "event_type",
        "event_date",
        "is_published",
        "media_count",
        "created_at",
    )

    list_filter = (
        "event_type",
        "is_published",
        "event_date",
    )

    search_fields = (
        "title",
        "description",
    )

    prepopulated_fields = {"slug": ("title",)}

    readonly_fields = (
        "created_at",
        "updated_at",
        "cover_preview",
    )

    inlines = [MediaItemInline]

    ordering = ("-event_date",)

    fieldsets = (
        (
            "Informations principales",
            {
                "fields": (
                    "title",
                    "slug",
                    "event_type",
                    "description",
                    "event_date",
                )
            },
        ),
        (
            "Image de couverture",
            {
                "fields": (
                    "cover_image",
                    "cover_preview",
                )
            },
        ),
        (
            "Publication",
            {
                "fields": (
                    "is_published",
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

    def cover_preview(self, obj):
        if obj.cover_thumbnail:
            return format_html(
                '<img src="{}" width="120" style="border-radius:8px;" />',
                obj.cover_thumbnail.url
            )
        return "-"
    cover_preview.short_description = "Aperçu couverture"

