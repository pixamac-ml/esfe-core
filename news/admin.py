# admin.py
from django.contrib import admin
from .models import News, Category, NewsImage


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
