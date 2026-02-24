from django.contrib import admin
from django.utils.html import mark_safe
from django.utils import timezone
from django.db.models import Count, Q

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
        'image_tag',
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
        'image_preview',
        'created_at',
        'updated_at',
        'published_at',
    )

    fieldsets = (
        ('Contenu', {
            'fields': (
                'title',
                'slug',
                'excerpt',
                'content',
                'featured_image',
                'image_preview',
                'category'
            )
        }),
        ('Publication', {
            'fields': (
                'status',
                'allow_comments'
            )
        }),
        ('Auteur & Dates', {
            'fields': (
                'author',
                'published_at',
                'created_at',
                'updated_at'
            )
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
            _comment_count=Count(
                'comments',
                filter=Q(comments__status=Comment.STATUS_APPROVED)
            )
        )

    def image_preview(self, obj):
        if obj.featured_image:
            return mark_safe(
                f'<img src="{obj.featured_image.url}" '
                f'style="height:120px; border-radius:8px; object-fit:cover;" />'
            )
        return "Aucune image"

    image_preview.short_description = "Aperçu"

    def image_tag(self, obj):
        if obj.featured_image:
            return mark_safe(
                f'<img src="{obj.featured_image.url}" '
                f'style="height:40px; border-radius:4px; object-fit:cover;" />'
            )
        return "—"

    image_tag.short_description = "Image"

    def comment_count(self, obj):
        return obj._comment_count

    comment_count.short_description = "Commentaires approuvés"

    def publish_articles(self, request, queryset):
        queryset.update(
            status='published',
            published_at=timezone.now()
        )

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
        'dislikes_count',
        'created_at',
    )

    list_filter = (
        'status',
        'created_at',
        'flagged',
    )

    search_fields = (
        'author_name',
        'content',
        'article__title'
    )

    readonly_fields = (
        'created_at',
        'approved_at',
    )

    actions = [
        'approve_comments',
        'reject_comments'
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('article').annotate(
            _likes_count=Count(
                'reactions',
                filter=Q(
                    reactions__reaction_type=CommentLike.REACTION_LIKE
                )
            ),
            _dislikes_count=Count(
                'reactions',
                filter=Q(
                    reactions__reaction_type=CommentLike.REACTION_DISLIKE
                )
            )
        )

    def likes_count(self, obj):
        return obj._likes_count

    likes_count.short_description = "Likes"

    def dislikes_count(self, obj):
        return obj._dislikes_count

    dislikes_count.short_description = "Dislikes"

    def short_content(self, obj):
        if len(obj.content) > 60:
            return obj.content[:60] + "..."
        return obj.content

    short_content.short_description = "Contenu"

    def approve_comments(self, request, queryset):
        queryset.update(
            status=Comment.STATUS_APPROVED,
            approved_at=timezone.now(),
            approved_by=request.user
        )

    approve_comments.short_description = "Approuver"

    def reject_comments(self, request, queryset):
        queryset.update(status=Comment.STATUS_REJECTED)

    reject_comments.short_description = "Rejeter"


# ==========================================================
# COMMENT LIKE ADMIN (Lecture seule)
# ==========================================================

@admin.register(CommentLike)
class CommentLikeAdmin(admin.ModelAdmin):

    list_display = (
        'comment',
        'reaction_type',
        'ip_address',
        'created_at',
    )

    readonly_fields = (
        'comment',
        'reaction_type',
        'ip_address',
        'created_at',
    )

    list_filter = ('reaction_type', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False