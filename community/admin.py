from django.contrib import admin
from .models import (
    Category,
    Tag,
    Topic,
    Answer,
    Vote,
    Attachment,
    TopicView,
)


# ==========================
# CATEGORY (Domaine)
# ==========================
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("order",)


# ==========================
# TAG
# ==========================
@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "usage_count")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("name",)


# ==========================
# ATTACHMENT INLINE
# ==========================
class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0
    raw_id_fields = ("uploaded_by",)


# ==========================
# TOPIC
# ==========================
@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "author",
        "category",
        "is_published",
        "is_locked",
        "is_public",
        "view_count",
        "last_activity_at",
        "created_at",
    )

    list_filter = (
        "is_published",
        "is_locked",
        "is_public",
        "category",
        "created_at",
        "last_activity_at",
    )

    search_fields = ("title", "content")
    prepopulated_fields = {"slug": ("title",)}
    raw_id_fields = ("author", "accepted_answer")
    filter_horizontal = ("tags",)
    inlines = [AttachmentInline]

    readonly_fields = ("view_count", "last_activity_at", "created_at", "updated_at")

    ordering = ("-last_activity_at",)


# ==========================
# ANSWER
# ==========================
@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = (
        "author",
        "topic",
        "parent",
        "upvotes",
        "downvotes",
        "is_deleted",
        "created_at",
    )

    list_filter = (
        "is_deleted",
        "created_at",
    )

    search_fields = ("content",)
    raw_id_fields = ("topic", "parent", "author")

    readonly_fields = ("created_at",)

    ordering = ("-upvotes", "created_at")


# ==========================
# VOTE
# ==========================
@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ("user", "answer", "value", "created_at")
    list_filter = ("value", "created_at")
    raw_id_fields = ("user", "answer")
    ordering = ("-created_at",)


# ==========================
# TOPIC VIEW (anti-abus)
# ==========================
@admin.register(TopicView)
class TopicViewAdmin(admin.ModelAdmin):
    list_display = ("topic", "user", "ip_address", "created_at")
    list_filter = ("created_at",)
    raw_id_fields = ("topic", "user")
    ordering = ("-created_at",)


# ==========================
# ATTACHMENT
# ==========================
@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ("uploaded_by", "topic", "answer", "created_at")
    raw_id_fields = ("uploaded_by", "topic", "answer")
    ordering = ("-created_at",)