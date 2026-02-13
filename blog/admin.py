from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from django.db.models import Count

from .models import Article, Comment, CommentLike, Category


# ==========================================================
# CATEGORY ADMIN
# ==========================================================

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):

    list_display = (
        'name',
        'is_active',
        'created_at',
        'article_count',
    )

    list_filter = ('is_active',)
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}

    readonly_fields = ('created_at',)

    def article_count(self, obj):
        return obj.articles.count()

    article_count.short_description = "Nombre d’articles"


# ==========================================================
# ARTICLE ADMIN
# ==========================================================

@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):

    list_display = (
        'title',
        'category',
        'author',
        'status',
        'published_at',
        'comment_count',
        'is_deleted',
        'created_at',
    )

    list_filter = (
        'status',
        'category',
        'is_deleted',
        'created_at',
        'published_at',
    )

    search_fields = (
        'title',
        'excerpt',
        'content',
    )

    prepopulated_fields = {'slug': ('title',)}

    readonly_fields = (
        'created_at',
        'updated_at',
        'published_at',
    )

    fieldsets = (
        ('Contenu', {
            'fields': ('title', 'slug', 'excerpt', 'content', 'category')
        }),
        ('Publication', {
            'fields': ('status', 'allow_comments')
        }),
        ('Auteur & Dates', {
            'fields': ('author', 'published_at', 'created_at', 'updated_at')
        }),
        ('Suppression', {
            'fields': ('is_deleted',)
        }),
    )

    actions = [
        'publish_articles',
        'archive_articles',
        'soft_delete_articles',
        'restore_articles'
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('author', 'category').annotate(
            _comment_count=Count('comments')
        )

    def comment_count(self, obj):
        return obj._comment_count

    comment_count.short_description = "Commentaires"

    def publish_articles(self, request, queryset):
        queryset.update(status='published', published_at=timezone.now())

    publish_articles.short_description = "Publier les articles sélectionnés"

    def archive_articles(self, request, queryset):
        queryset.update(status='archived')

    archive_articles.short_description = "Archiver les articles sélectionnés"

    def soft_delete_articles(self, request, queryset):
        queryset.update(is_deleted=True)

    soft_delete_articles.short_description = "Soft delete"

    def restore_articles(self, request, queryset):
        queryset.update(is_deleted=False)

    restore_articles.short_description = "Restaurer articles supprimés"


# ==========================================================
# COMMENT ADMIN
# ==========================================================

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):

    list_display = (
        'short_content',
        'article',
        'author_name',
        'status',
        'likes_count',
        'created_at',
    )

    list_filter = (
        'status',
        'created_at',
    )

    search_fields = (
        'author_name',
        'content',
        'article__title'
    )

    readonly_fields = (
        'created_at',
    )

    actions = [
        'approve_comments',
        'reject_comments'
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('article').annotate(
            _likes_count=Count('likes')
        )

    def likes_count(self, obj):
        return obj._likes_count

    likes_count.short_description = "Likes"

    def short_content(self, obj):
        if len(obj.content) > 60:
            return obj.content[:60] + "..."
        return obj.content

    short_content.short_description = "Contenu"

    def approve_comments(self, request, queryset):
        queryset.update(status='approved')

    approve_comments.short_description = "Approuver"

    def reject_comments(self, request, queryset):
        queryset.update(status='rejected')

    reject_comments.short_description = "Rejeter"


# ==========================================================
# COMMENT LIKE ADMIN (Lecture seule)
# ==========================================================

@admin.register(CommentLike)
class CommentLikeAdmin(admin.ModelAdmin):

    list_display = (
        'comment',
        'ip_address',
        'created_at',
    )

    readonly_fields = (
        'comment',
        'ip_address',
        'created_at',
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
