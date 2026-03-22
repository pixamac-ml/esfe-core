from django.contrib import admin
from .models import (
    Category,
    Tag,
    Topic,
    Answer,
    Vote,
    Attachment,
    TopicView,
    Notification,
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

    prepopulated_fields = {
        "slug": ("title",)
    }

    raw_id_fields = (
        "author",
        "accepted_answer",
    )

    filter_horizontal = ("tags",)

    inlines = [AttachmentInline]

    readonly_fields = (
        "view_count",
        "last_activity_at",
        "created_at",
        "updated_at",
    )

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

    raw_id_fields = (
        "topic",
        "parent",
        "author",
    )

    readonly_fields = ("created_at",)

    ordering = ("-upvotes", "created_at")


# ==========================
# VOTE
# ==========================
@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "answer",
        "value",
        "created_at",
    )

    list_filter = (
        "value",
        "created_at",
    )

    raw_id_fields = (
        "user",
        "answer",
    )

    ordering = ("-created_at",)


# ==========================
# TOPIC VIEW (anti-abus)
# ==========================
@admin.register(TopicView)
class TopicViewAdmin(admin.ModelAdmin):

    list_display = (
        "topic",
        "user",
        "ip_address",
        "created_at",
    )

    list_filter = ("created_at",)

    raw_id_fields = (
        "topic",
        "user",
    )

    ordering = ("-created_at",)


# ==========================
# ATTACHMENT
# ==========================
@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):

    list_display = (
        "uploaded_by",
        "topic",
        "answer",
        "created_at",
    )

    raw_id_fields = (
        "uploaded_by",
        "topic",
        "answer",
    )

    ordering = ("-created_at",)


# ==========================
# NOTIFICATION
# ==========================
@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):

    list_display = (
        "user",
        "actor",
        "notification_type",
        "topic",
        "answer",
        "is_read",
        "created_at",
    )

    list_filter = (
        "notification_type",
        "is_read",
        "created_at",
    )

    search_fields = (
        "user__username",
        "actor__username",
        "topic__title",
    )

    raw_id_fields = (
        "user",
        "actor",
        "topic",
        "answer",
    )

    readonly_fields = ("created_at",)

    ordering = ("-created_at",)


from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "reporter",
        "get_content",
        "reason",
        "status",
        "created_at",
        "reviewed_by",
    )

    list_filter = (
        "status",
        "reason",
        "created_at",
    )

    search_fields = (
        "reporter__username",
        "topic__title",
        "details",
    )

    raw_id_fields = (
        "reporter",
        "topic",
        "answer",
        "reviewed_by",
    )

    readonly_fields = ("created_at", "resolved_at")

    ordering = ("-created_at",)

    list_editable = ("status",)

    actions = ["mark_resolved", "mark_dismissed"]

    def get_content(self, obj):
        if obj.topic:
            return f"Sujet: {obj.topic.title[:30]}"
        return f"Réponse #{obj.answer.id}"

    get_content.short_description = "Contenu signalé"

    @admin.action(description="Marquer comme résolu")
    def mark_resolved(self, request, queryset):
        queryset.update(status="resolved", reviewed_by=request.user)

    @admin.action(description="Rejeter les signalements")
    def mark_dismissed(self, request, queryset):
        queryset.update(status="dismissed", reviewed_by=request.user)








# ==========================
# ADMIN GAMIFICATION
# ==========================
from .models_gamification import (
    XPConfig,
    GamificationProfile,
    XPTransaction,
    BadgeDefinition,
    UserBadge,
    LeaderboardEntry,
)


@admin.register(XPConfig)
class XPConfigAdmin(admin.ModelAdmin):
    list_display = ("action", "points", "is_active")
    list_editable = ("points", "is_active")
    list_filter = ("is_active",)


@admin.register(GamificationProfile)
class GamificationProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "level",
        "total_xp",
        "answers_given",
        "answers_accepted",
        "current_streak",
    )
    list_filter = ("level",)
    search_fields = ("user__username",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(XPTransaction)
class XPTransactionAdmin(admin.ModelAdmin):
    list_display = ("user", "points", "action", "balance_after", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("user__username",)
    date_hierarchy = "created_at"


@admin.register(BadgeDefinition)
class BadgeDefinitionAdmin(admin.ModelAdmin):
    list_display = ("icon", "name", "category", "rarity", "xp_reward", "is_active")
    list_filter = ("category", "rarity", "is_active")
    list_editable = ("is_active",)
    search_fields = ("name", "code")


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display = ("user", "badge", "earned_at", "is_featured")
    list_filter = ("badge", "earned_at")
    search_fields = ("user__username", "badge__name")
    raw_id_fields = ("user",)


@admin.register(LeaderboardEntry)
class LeaderboardEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "period", "category", "rank", "score")
    list_filter = ("period", "category")