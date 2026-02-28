from django.contrib import admin
from .models import Category, Topic, Answer, Vote, Attachment


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "order")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("order",)


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "category", "is_published", "is_locked", "created_at")
    list_filter = ("is_published", "is_locked", "category", "created_at")
    search_fields = ("title", "content")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [AttachmentInline]


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ("author", "topic", "parent", "is_accepted", "is_deleted", "created_at")
    list_filter = ("is_accepted", "is_deleted", "created_at")
    search_fields = ("content",)
    raw_id_fields = ("topic", "parent", "author")


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ("user", "answer", "value", "created_at")
    list_filter = ("value",)


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ("uploaded_by", "topic", "answer", "created_at")