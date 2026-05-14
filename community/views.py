import logging
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.models import User
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.template.loader import render_to_string
from django.db.models import Prefetch, Count, F, Q
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.contrib.auth import get_user_model

from .forms import TopicForm, ReportForm
from .models import Topic, Category, Answer, Vote, TopicView, Tag, Report
from community.services.notifications import (
    create_notification,
    notify_accepted_answer,
    notify_new_answer,
    notify_reply_to_reply,
)
from community.services.gamification import GamificationService
from community.models_gamification import GamificationProfile, UserBadge


logger = logging.getLogger(__name__)


def paginate_items(request, items, per_page=12, page_param="page"):
    paginator = Paginator(items, per_page)
    page_number = request.GET.get(page_param, 1)
    try:
        return paginator.page(page_number)
    except PageNotAnInteger:
        return paginator.page(1)
    except EmptyPage:
        return paginator.page(paginator.num_pages)


# =====================================================
# BUILDER : QUERY TOPICS
# =====================================================
def build_topic_queryset(sort="active", query="", focus=""):
    queryset = _community_topic_base_queryset()

    if query:
        queryset = queryset.filter(
            Q(title__icontains=query) |
            Q(content__icontains=query) |
            Q(tags__name__icontains=query) |
            Q(author__username__icontains=query) |
            Q(category__name__icontains=query)
        ).distinct()

    queryset = _apply_topic_focus(queryset, focus)

    sort_map = {
        "recent": ["-created_at"],
        "answers": ["-answer_count", "-last_activity_at"],
        "views": ["-view_count", "-last_activity_at"],
        "active": ["-last_activity_at"],
        "hot": ["-answer_count", "-view_count", "-last_activity_at"],
    }

    ordering = ["-is_pinned"] + sort_map.get(sort, sort_map["active"])
    return queryset.order_by(*ordering)


def _community_topic_base_queryset():
    return (
        Topic.objects
        .filter(is_published=True, is_deleted=False)
        .select_related("author", "author__profile", "category")
        .prefetch_related("tags")
        .annotate(
            answer_count=Count(
                "answers",
                filter=Q(answers__is_deleted=False)
            )
        )
    )


def _apply_topic_focus(queryset, focus):
    focus = (focus or "").strip().lower()
    if focus == "pinned":
        return queryset.filter(is_pinned=True)
    if focus == "unanswered":
        return queryset.filter(answer_count=0)
    if focus == "answered":
        return queryset.filter(answer_count__gt=0)
    return queryset

# =====================================================
# BUILDER : SIDEBAR CONTEXT
# =====================================================
def build_sidebar_context(request=None):
    categories = (
        Category.objects
        .filter(is_active=True)
        .annotate(
            topic_count=Count(
                "topics",
                filter=Q(
                    topics__is_deleted=False,
                    topics__is_published=True
                )
            )
        )
        .order_by("name")
    )

    user_subscriptions = []
    if request and request.user.is_authenticated:
        user_subscriptions = list(
            Category.objects
            .filter(subscribers=request.user, is_active=True)
            .values_list("id", flat=True)
        )

    top_users = (
        User.objects
        .select_related("profile")
        .filter(profile__isnull=False)
        .annotate(
            answer_count=Count(
                "community_answers",
                filter=Q(community_answers__is_deleted=False)
            )
        )
        .filter(answer_count__gt=0)
        .order_by("-answer_count")[:10]
    )

    popular_tags = (
        Tag.objects
        .annotate(
            topic_count=Count(
                "topics",
                filter=Q(
                    topics__is_deleted=False,
                    topics__is_published=True
                )
            )
        )
        .filter(topic_count__gt=0)
        .order_by("-topic_count")[:8]
    )

    return {
        "categories": categories,
        "top_users": top_users,
        "popular_tags": popular_tags,
        "user_subscriptions": user_subscriptions,
    }


def build_community_hub_context(request, *, sort="active", query="", focus=""):
    topics_qs = build_topic_queryset(sort=sort, query=query, focus=focus)
    page_obj = paginate_items(request, topics_qs, per_page=12)

    today = timezone.localdate()
    thirty_days_ago = today - timedelta(days=30)

    published_topics = _community_topic_base_queryset()
    published_answers = (
        Answer.objects
        .filter(is_deleted=False, topic__is_deleted=False, topic__is_published=True)
        .select_related("author", "topic", "topic__category")
    )

    recent_authors = set(
        published_topics.filter(last_activity_at__date__gte=thirty_days_ago).values_list("author_id", flat=True)
    )
    recent_authors.update(
        published_answers.filter(created_at__date__gte=thirty_days_ago).values_list("author_id", flat=True)
    )

    top_contributors = (
        User.objects
        .select_related("profile")
        .select_related("profile", "gamification")
        .prefetch_related("user_badges")
        .filter(profile__isnull=False)
        .annotate(
            topic_count=Count("community_topics", filter=Q(community_topics__is_deleted=False)),
            answer_count=Count("community_answers", filter=Q(community_answers__is_deleted=False)),
            badge_count=Count("user_badges", distinct=True),
        )
        .filter(Q(topic_count__gt=0) | Q(answer_count__gt=0))
        .order_by("-answer_count", "-topic_count", "first_name", "last_name")[:6]
    )

    featured_topics = list(
        published_topics
        .filter(is_pinned=True)
        .annotate(answer_count=Count("answers", filter=Q(answers__is_deleted=False)))
        .order_by("-last_activity_at", "-created_at")[:3]
    )
    if len(featured_topics) < 3:
        fallback_ids = {topic.id for topic in featured_topics}
        featured_topics.extend(
            list(
                published_topics
                .exclude(id__in=fallback_ids)
                .annotate(answer_count=Count("answers", filter=Q(answers__is_deleted=False)))
                .order_by("-last_activity_at", "-view_count")[: 3 - len(featured_topics)]
            )
        )

    trending_topics = list(
        published_topics
        .annotate(answer_count=Count("answers", filter=Q(answers__is_deleted=False)))
        .order_by("-answer_count", "-view_count", "-last_activity_at")[:5]
    )
    unanswered_topics = list(
        published_topics
        .annotate(answer_count=Count("answers", filter=Q(answers__is_deleted=False)))
        .filter(answer_count=0)
        .order_by("-created_at")[:5]
    )
    recent_topics = list(
        published_topics
        .annotate(answer_count=Count("answers", filter=Q(answers__is_deleted=False)))
        .order_by("-created_at")[:5]
    )

    community_stats = {
        "topics_total": published_topics.count(),
        "answers_total": published_answers.count(),
        "contributors_total": len(recent_authors),
        "today_topics": published_topics.filter(created_at__date=today).count(),
        "today_answers": published_answers.filter(created_at__date=today).count(),
        "pinned_topics": len(featured_topics),
        "unanswered_topics": len(unanswered_topics),
    }

    return {
        "topics": page_obj.object_list,
        "topics_total": topics_qs.count(),
        "page_obj": page_obj,
        "current_sort": sort,
        "query": query,
        "current_focus": focus,
        "community_stats": community_stats,
        "featured_topics": featured_topics,
        "trending_topics": trending_topics,
        "unanswered_topics": unanswered_topics,
        "recent_topics": recent_topics,
        "top_contributors": top_contributors,
        **build_sidebar_context(request),
    }


# =====================================================
# LISTE GÉNÉRALE
# =====================================================
def topic_list(request):
    sort = request.GET.get("sort", "active")
    query = request.GET.get("q", "").strip()
    focus = request.GET.get("focus", "").strip()

    context = build_community_hub_context(request, sort=sort, query=query, focus=focus)

    if request.headers.get("HX-Request"):
        html = render_to_string(
            "community/partials/topic_list_items.html",
            context,
            request=request
        )
        return HttpResponse(html)

    return render(request, "community/topic_list.html", context)


# =====================================================
# LISTE PAR TAG
# =====================================================
def topic_by_tag(request, slug):
    sort = request.GET.get("sort", "active")
    query = request.GET.get("q", "").strip()
    focus = request.GET.get("focus", "").strip()

    tag = get_object_or_404(Tag, slug=slug)

    context = build_community_hub_context(request, sort=sort, query=query, focus=focus)
    topics_qs = build_topic_queryset(sort=sort, query=query, focus=focus).filter(tags=tag)
    page_obj = paginate_items(request, topics_qs, per_page=12)
    context.update({
        "topics": page_obj.object_list,
        "topics_total": topics_qs.count(),
        "page_obj": page_obj,
        "tag": tag,
    })

    if request.headers.get("HX-Request"):
        html = render_to_string(
            "community/partials/topic_list_items.html",
            context,
            request=request
        )
        return HttpResponse(html)

    return render(request, "community/topic_list.html", context)


# =====================================================
# LISTE PAR CATÉGORIE
# =====================================================
def topic_by_category(request, slug):
    sort = request.GET.get("sort", "active")
    query = request.GET.get("q", "").strip()
    focus = request.GET.get("focus", "").strip()

    category = get_object_or_404(Category, slug=slug, is_active=True)

    context = build_community_hub_context(request, sort=sort, query=query, focus=focus)
    topics_qs = build_topic_queryset(sort=sort, query=query, focus=focus).filter(category=category)
    page_obj = paginate_items(request, topics_qs, per_page=12)
    context.update({
        "topics": page_obj.object_list,
        "topics_total": topics_qs.count(),
        "page_obj": page_obj,
        "category": category,
    })

    if request.headers.get("HX-Request"):
        html = render_to_string(
            "community/partials/topic_list_items.html",
            context,
            request=request
        )
        return HttpResponse(html)

    return render(request, "community/topic_list.html", context)


# =====================================================
# DÉTAIL D'UN SUJET
# =====================================================
def topic_detail(request, slug):
    topic = get_object_or_404(
        Topic.objects.select_related("author", "author__profile", "category"),
        slug=slug,
        is_published=True
    )

    # Anti-refresh intelligent
    ip_address = request.META.get("REMOTE_ADDR")
    now = timezone.now()
    today = now.date()

    view_exists = TopicView.objects.filter(
        topic=topic,
        user=request.user if request.user.is_authenticated else None,
        ip_address=ip_address,
        created_at__date=today
    ).exists()

    if not view_exists:
        TopicView.objects.create(
            topic=topic,
            user=request.user if request.user.is_authenticated else None,
            ip_address=ip_address
        )
        Topic.objects.filter(pk=topic.pk).update(view_count=F("view_count") + 1)
        topic.refresh_from_db(fields=["view_count"])

    # Réponses principales
    root_answers = (
        Answer.objects
        .filter(topic=topic, parent__isnull=True, is_deleted=False)
        .select_related("author", "author__profile")
        .prefetch_related(
            Prefetch(
                "replies",
                queryset=Answer.objects
                .filter(is_deleted=False)
                .select_related("author", "author__profile")
                .order_by("-upvotes", "created_at")
            )
        )
        .order_by("-upvotes", "created_at")
    )

    # Mettre accepted_answer en premier
    if topic.accepted_answer:
        accepted = topic.accepted_answer
        root_answers = sorted(
            root_answers,
            key=lambda a: a.id != accepted.id
        )

    answers_total = len(root_answers)

    answers_page = paginate_items(
        request,
        root_answers,
        per_page=10,
        page_param="answers_page"
    )

    # Sujets similaires
    related_topics = list(
        Topic.objects
        .filter(
            is_published=True,
            is_deleted=False,
        )
        .exclude(pk=topic.pk)
        .select_related("author", "author__profile", "category")
        .prefetch_related("tags")
        .annotate(answer_count=Count("answers", filter=Q(answers__is_deleted=False)))
        .filter(Q(category=topic.category) | Q(tags__in=topic.tags.all()))
        .distinct()
        .order_by("-is_pinned", "-answer_count", "-view_count", "-last_activity_at")[:6]
    )

    topic_insights = {
        "answers_total": answers_total,
        "views_total": topic.view_count,
        "tags_total": topic.tags.count(),
        "related_total": len(related_topics),
    }

    # Abonnements utilisateur
    user_subscriptions = []
    if request.user.is_authenticated:
        user_subscriptions = list(
            Category.objects
            .filter(subscribers=request.user, is_active=True)
            .values_list("id", flat=True)
        )

    return render(request, "community/topic_detail.html", {
        "topic": topic,
        "answers": answers_page.object_list,
        "answers_total": answers_total,
        "answers_page": answers_page,
        "related_topics": related_topics,
        "topic_insights": topic_insights,
        "user_subscriptions": user_subscriptions,
    })


# =====================================================
# AJOUT RÉPONSE (HTMX)
# =====================================================
@login_required
@require_POST
def add_answer(request, slug):
    topic = get_object_or_404(
        Topic.objects.select_related("author", "category"),
        slug=slug,
        is_locked=False,
        is_published=True
    )

    content = request.POST.get("content", "").strip()

    if not content:
        return HttpResponseBadRequest("Contenu vide ou invalide.")

    parent = None
    parent_id = request.POST.get("parent_id")

    if parent_id:
        parent = Answer.objects.filter(
            id=parent_id,
            topic=topic,
            is_deleted=False
        ).select_related("author").first()

        if not parent:
            return HttpResponseBadRequest("Réponse parent invalide.")

    answer = Answer.objects.create(
        topic=topic,
        author=request.user,
        content=content,
        parent=parent
    )

    # Mise à jour activité du sujet
    Topic.objects.filter(pk=topic.pk).update(
        last_activity_at=timezone.now()
    )

    try:
        if parent:
            notify_reply_to_reply(parent, answer)
        else:
            notify_new_answer(topic, answer)
    except Exception as exc:
        logger.exception("Echec notifications reponse topic=%s answer=%s: %s", topic.id, answer.id, exc)

    # Préchargement auteur pour template
    answer = (
        Answer.objects
        .select_related("author")
        .get(pk=answer.pk)
    )

    # Réponse HTMX
    if request.headers.get("HX-Request"):
        template_name = "community/partials/answer_item.html"
        if parent:
            template_name = "community/partials/reply_item.html"

        html = render_to_string(
            template_name,
            {
                "answer": answer,
                "topic": topic,
            },
            request=request
        )
        return HttpResponse(html)

    return HttpResponse(status=204)


# =====================================================
# VOTE RÉPONSE (HTMX)
# =====================================================
@login_required
@require_POST
def vote_answer(request, answer_id):
    answer = get_object_or_404(Answer, id=answer_id, is_deleted=False)

    try:
        value = int(request.POST.get("value"))
        if value not in [1, -1]:
            return HttpResponseBadRequest("Vote invalide.")
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Vote invalide.")

    Vote.objects.update_or_create(
        user=request.user,
        answer=answer,
        defaults={"value": value}
    )

    # Recalcul propre
    answer.upvotes = answer.votes.filter(value=1).count()
    answer.downvotes = answer.votes.filter(value=-1).count()
    answer.save(update_fields=["upvotes", "downvotes"])

    if request.headers.get("HX-Request"):
        return HttpResponse(
            f"""
            <div class="vote-count text-lg font-bold
                {'text-green-600' if answer.score > 0 else 'text-red-600' if answer.score < 0 else 'text-gray-500'}">
                {answer.score}
            </div>
            """
        )

    return HttpResponse(status=204)


# =====================================================
# CRÉATION SUJET
# =====================================================
@login_required
def create_topic(request):
    if request.method == "POST":
        form = TopicForm(request.POST, request.FILES)

        if form.is_valid():
            topic = form.save(commit=False)
            topic.author = request.user
            topic.last_activity_at = timezone.now()
            topic.save()
            form.save_m2m()

            category = topic.category

            if form.cleaned_data.get("subscribe"):
                try:
                    category.subscribers.add(request.user)
                except Exception as exc:
                    logger.warning("Impossible d'abonner user=%s categorie=%s: %s", request.user.id, category.id, exc)

            # NOTIFICATIONS DES ABONNÉS
            subscribers = (
                category.subscribers
                .filter(is_active=True)
                .exclude(id=request.user.id)
                .distinct()
            )

            for user in subscribers:
                try:
                    create_notification(
                        user=user,
                        actor=request.user,
                        topic=topic,
                        notification_type="new_topic",
                        send_email=True
                    )
                except Exception as exc:
                    logger.warning("Echec notif nouveau topic pour user=%s topic=%s: %s", user.id, topic.id, exc)

            if request.headers.get("HX-Request"):
                response = HttpResponse()
                response["HX-Redirect"] = topic.get_absolute_url()
                return response

            return redirect(topic.get_absolute_url())

        if request.headers.get("HX-Request"):
            html = render_to_string(
                "community/partials/topic_form.html",
                {"form": form},
                request=request
            )
            return HttpResponse(html)

    else:
        form = TopicForm()

    return render(
        request,
        "community/create_topic.html",
        {"form": form}
    )


@login_required
def edit_topic(request, slug):
    topic = get_object_or_404(
        Topic,
        slug=slug,
        author=request.user,
        is_deleted=False
    )

    if request.method == "POST":
        form = TopicForm(request.POST, request.FILES, instance=topic)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.updated_by = request.user
            updated.is_edited = True
            updated.save()
            form.save_m2m()
            return redirect(topic.get_absolute_url())
    else:
        form = TopicForm(instance=topic)

    return render(request, "community/edit_topic.html", {
        "form": form,
        "topic": topic
    })


@login_required
@require_POST
def delete_topic(request, slug):
    topic = get_object_or_404(
        Topic,
        slug=slug,
        author=request.user,
        is_deleted=False
    )

    topic.is_deleted = True
    topic.save(update_fields=["is_deleted"])

    return redirect("accounts:profile")


# =====================================================
# ABONNEMENT AUX DOMAINES
# =====================================================
@login_required
@require_POST
def subscribe_category(request, slug):
    category = get_object_or_404(Category, slug=slug, is_active=True)
    category.subscribers.add(request.user)

    if request.headers.get("HX-Request"):
        html = render_to_string(
            "community/partials/subscribe_button.html",
            {"category": category, "is_subscribed": True},
            request=request
        )
        return HttpResponse(html)

    return redirect("community:topic_by_category", slug=slug)


@login_required
@require_POST
def unsubscribe_category(request, slug):
    category = get_object_or_404(Category, slug=slug, is_active=True)
    category.subscribers.remove(request.user)

    if request.headers.get("HX-Request"):
        html = render_to_string(
            "community/partials/subscribe_button.html",
            {"category": category, "is_subscribed": False},
            request=request
        )
        return HttpResponse(html)

    return redirect("community:topic_by_category", slug=slug)


@login_required
def my_subscriptions(request):
    subscriptions = (
        Category.objects
        .filter(subscribers=request.user, is_active=True)
        .annotate(
            topic_count=Count(
                "topics",
                filter=Q(
                    topics__is_deleted=False,
                    topics__is_published=True
                )
            )
        )
        .order_by("name")
    )

    return render(request, "community/my_subscriptions.html", {
        "subscriptions": subscriptions,
    })


# =====================================================
# MEMBRES
# =====================================================
def members_list(request):
    User = get_user_model()

    users_qs = (
        User.objects
        .select_related("profile")
        .filter(profile__isnull=False)
        .annotate(
            topic_count=Count(
                "community_topics",
                filter=Q(community_topics__is_deleted=False)
            ),
            answer_count=Count(
                "community_answers",
                filter=Q(community_answers__is_deleted=False)
            )
        )
        .filter(Q(topic_count__gt=0) | Q(answer_count__gt=0))
        .order_by("-answer_count", "-topic_count")
    )

    page_obj = paginate_items(request, users_qs, per_page=12)

    return render(request, "community/members_list.html", {
        "users": page_obj.object_list,
        "users_total": users_qs.count(),
        "page_obj": page_obj,
    })


# =====================================================
# PROFIL PUBLIC UTILISATEUR (AVEC GAMIFICATION)
# =====================================================
def public_profile(request, username):
    from django.db.models import Sum
    from django.db.models.functions import Coalesce

    User = get_user_model()

    user = get_object_or_404(
        User.objects.select_related("profile"),
        username=username
    )

    # Récupérer ou créer le profil accounts
    try:
        profile = user.profile
    except:
        from accounts.models import Profile
        profile = Profile.objects.create(user=user)

    # ========== GAMIFICATION ==========
    gamification = GamificationService.get_or_create_profile(user)
    badges = UserBadge.objects.filter(user=user).select_related("badge").order_by("-earned_at")
    # ==================================

    # Sujets
    topics = (
        user.community_topics
        .filter(is_deleted=False)
        .select_related("category")
        .annotate(answer_count=Count("answers"))
        .order_by("-created_at")
    )

    # Réponses
    answers = (
        user.community_answers
        .filter(is_deleted=False)
        .select_related("topic", "topic__category")
        .order_by("-created_at")
    )

    # Meilleures réponses
    best_answers = answers.order_by("-upvotes")[:5]

    # Domaines d'activité
    top_categories = (
        Category.objects
        .filter(topics__answers__author=user, topics__is_deleted=False)
        .annotate(answer_count=Count("topics__answers"))
        .order_by("-answer_count")[:5]
    )

    # Stats
    stats = {
        "topics": topics.count(),
        "answers": answers.count(),
        "accepted": answers.filter(accepted_for_topics__isnull=False).count(),
        "upvotes": answers.aggregate(total=Coalesce(Sum("upvotes"), 0))["total"],
        "views": profile.total_views_generated if hasattr(profile, 'total_views_generated') else 0,
        "reputation": profile.reputation if hasattr(profile, 'reputation') else 0,
    }

    context = {
        "page_title": f"Profil de {user.get_full_name() or user.username}",
        "meta_description": f"Consultez le profil public de {user.get_full_name() or user.username} sur la communaute ESFE.",
        "og_type": "profile",
        "profile_user": user,
        "profile": profile,
        "gamification": gamification,
        "badges": badges,
        "topics": topics[:10],
        "answers": answers[:10],
        "best_answers": best_answers,
        "top_categories": top_categories,
        "stats": stats,
    }

    return render(request, "community/public_profile.html", context)


def profile_activity(request, username):
    if not request.headers.get("HX-Request"):
        return redirect("community:public_profile", username=username)

    User = get_user_model()
    user = get_object_or_404(User.objects.select_related("profile"), username=username)

    answers = (
        user.community_answers
        .filter(is_deleted=False)
        .select_related("topic", "topic__category")
        .order_by("-created_at")[:10]
    )

    topics = (
        user.community_topics
        .filter(is_deleted=False)
        .select_related("category")
        .order_by("-created_at")[:5]
    )

    return render(
        request,
        "community/partials/profile/activity.html",
        {"profile_user": user, "answers": answers, "topics": topics},
    )


def profile_answers(request, username):
    if not request.headers.get("HX-Request"):
        return redirect("community:public_profile", username=username)

    User = get_user_model()
    user = get_object_or_404(User.objects.select_related("profile"), username=username)

    answers_qs = (
        user.community_answers
        .filter(is_deleted=False)
        .select_related("topic", "topic__category")
        .order_by("-created_at")
    )

    page_obj = paginate_items(request, answers_qs, per_page=10, page_param="answers_page")

    return render(
        request,
        "community/partials/profile/answers.html",
        {
            "profile_user": user,
            "answers": page_obj.object_list,
            "answers_page": page_obj,
        },
    )


def profile_topics(request, username):
    if not request.headers.get("HX-Request"):
        return redirect("community:public_profile", username=username)

    User = get_user_model()
    user = get_object_or_404(User.objects.select_related("profile"), username=username)

    topics_qs = (
        user.community_topics
        .filter(is_deleted=False)
        .select_related("category")
        .annotate(answers_count=Count("answers"))
        .order_by("-created_at")
    )

    page_obj = paginate_items(request, topics_qs, per_page=10, page_param="topics_page")

    return render(
        request,
        "community/partials/profile/topics.html",
        {
            "profile_user": user,
            "topics": page_obj.object_list,
            "topics_page": page_obj,
        },
    )


def profile_badges(request, username):
    if not request.headers.get("HX-Request"):
        return redirect("community:public_profile", username=username)

    User = get_user_model()
    user = get_object_or_404(User.objects.select_related("profile"), username=username)

    # Récupérer les badges gamification
    badges = UserBadge.objects.filter(user=user).select_related("badge").order_by("-earned_at")
    gamification = GamificationService.get_or_create_profile(user)

    return render(
        request,
        "community/partials/profile/badges.html",
        {
            "profile_user": user,
            "badges": badges,
            "gamification": gamification,
        },
    )


# =====================================================
# CLASSEMENT (LEADERBOARD)
# =====================================================
def leaderboard(request):
    """Affiche le classement des contributeurs"""
    category = request.GET.get("category") or request.GET.get("cat", "xp")

    # Classement principal
    top_users = GamificationService.get_leaderboard(category=category, limit=20)

    # Position de l'utilisateur connecté
    user_rank = None
    if request.user.is_authenticated:
        try:
            user_gam = request.user.gamification
            if category == "xp":
                user_rank = GamificationProfile.objects.filter(
                    total_xp__gt=user_gam.total_xp
                ).count() + 1
            elif category == "answers":
                user_rank = GamificationProfile.objects.filter(
                    answers_given__gt=user_gam.answers_given
                ).count() + 1
            elif category == "accepted":
                user_rank = GamificationProfile.objects.filter(
                    answers_accepted__gt=user_gam.answers_accepted
                ).count() + 1
        except GamificationProfile.DoesNotExist:
            pass

    context = {
        "leaderboard": top_users,
        "category": category,
        "user_rank": user_rank,
    }

    return render(request, "community/leaderboard.html", context)


# =====================================================
# ACCEPTER UNE RÉPONSE COMME SOLUTION
# =====================================================
@login_required
@require_POST
def accept_answer(request, answer_id):
    answer = get_object_or_404(
        Answer.objects.select_related("topic", "author"),
        id=answer_id,
        is_deleted=False
    )
    topic = answer.topic

    if topic.author != request.user:
        if request.headers.get("HX-Request"):
            return HttpResponse(
                '<span class="text-red-500 text-sm">Action non autorisée</span>',
                status=403
            )
        return HttpResponseBadRequest("Seul l'auteur du sujet peut accepter une réponse.")

    if topic.accepted_answer == answer:
        topic.accepted_answer = None
        topic.save(update_fields=["accepted_answer"])
        is_accepted = False
    else:
        topic.accepted_answer = answer
        topic.save(update_fields=["accepted_answer"])
        is_accepted = True

        # GAMIFICATION: XP pour réponse acceptée
        if answer.author != request.user:
            GamificationService.award_xp(answer.author, "answer_accepted")

        # Notification
        if answer.author != request.user:
            try:
                notify_accepted_answer(topic, answer)
            except Exception as exc:
                logger.exception("Echec notification accepted_answer topic=%s answer=%s: %s", topic.id, answer.id, exc)

    if request.headers.get("HX-Request"):
        html = render_to_string(
            "community/partials/accept_button.html",
            {"answer": answer, "topic": topic, "is_accepted": is_accepted},
            request=request
        )
        return HttpResponse(html)

    return redirect(topic.get_absolute_url())


# =====================================================
# SIGNALER UN SUJET
# =====================================================
@login_required
def report_topic(request, slug):
    topic = get_object_or_404(Topic, slug=slug, is_deleted=False)

    already_reported = Report.objects.filter(
        reporter=request.user,
        topic=topic
    ).exists()

    if already_reported:
        if request.headers.get("HX-Request"):
            return HttpResponse(
                '<div class="text-amber-600 text-sm p-4">Vous avez déjà signalé ce contenu.</div>'
            )
        messages.warning(request, "Vous avez déjà signalé ce contenu.")
        return redirect(topic.get_absolute_url())

    if request.method == "POST":
        form = ReportForm(request.POST)

        if form.is_valid():
            report = form.save(commit=False)
            report.reporter = request.user
            report.topic = topic
            report.save()

            if request.headers.get("HX-Request"):
                return HttpResponse(
                    '''<div class="bg-green-50 border border-green-200 rounded-xl p-4 text-center">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 mx-auto text-green-500 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                        </svg>
                        <p class="text-green-700 font-medium">Signalement envoyé</p>
                        <p class="text-green-600 text-sm">Notre équipe examinera ce contenu.</p>
                    </div>'''
                )

            messages.success(request, "Votre signalement a été envoyé.")
            return redirect(topic.get_absolute_url())
    else:
        form = ReportForm()

    context = {"form": form, "topic": topic, "content_type": "topic"}

    if request.headers.get("HX-Request"):
        return render(request, "community/partials/report_form.html", context)

    return render(request, "community/report.html", context)


# =====================================================
# SIGNALER UNE RÉPONSE
# =====================================================
@login_required
def report_answer(request, answer_id):
    answer = get_object_or_404(
        Answer.objects.select_related("topic"),
        id=answer_id,
        is_deleted=False
    )

    already_reported = Report.objects.filter(
        reporter=request.user,
        answer=answer
    ).exists()

    if already_reported:
        if request.headers.get("HX-Request"):
            return HttpResponse(
                '<div class="text-amber-600 text-sm p-4">Vous avez déjà signalé ce contenu.</div>'
            )
        messages.warning(request, "Vous avez déjà signalé ce contenu.")
        return redirect(answer.topic.get_absolute_url())

    if request.method == "POST":
        form = ReportForm(request.POST)

        if form.is_valid():
            report = form.save(commit=False)
            report.reporter = request.user
            report.answer = answer
            report.save()

            if request.headers.get("HX-Request"):
                return HttpResponse(
                    '''<div class="bg-green-50 border border-green-200 rounded-xl p-4 text-center">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 mx-auto text-green-500 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                        </svg>
                        <p class="text-green-700 font-medium">Signalement envoyé</p>
                        <p class="text-green-600 text-sm">Notre équipe examinera ce contenu.</p>
                    </div>'''
                )

            messages.success(request, "Votre signalement a été envoyé.")
            return redirect(answer.topic.get_absolute_url())
    else:
        form = ReportForm()

    context = {"form": form, "answer": answer, "topic": answer.topic, "content_type": "answer"}

    if request.headers.get("HX-Request"):
        return render(request, "community/partials/report_form.html", context)

    return render(request, "community/report.html", context)


# =====================================================
# VERROUILLER / DÉVERROUILLER UN SUJET
# =====================================================
@login_required
@require_POST
def lock_topic(request, slug):
    topic = get_object_or_404(Topic, slug=slug, is_deleted=False)

    can_lock = request.user.is_staff or topic.author == request.user

    if not can_lock:
        if request.headers.get("HX-Request"):
            return HttpResponse(
                '<span class="text-red-500 text-sm">Permission refusée</span>',
                status=403
            )
        return HttpResponseBadRequest("Vous n'avez pas la permission de verrouiller ce sujet.")

    topic.is_locked = not topic.is_locked
    topic.save(update_fields=["is_locked"])

    if request.headers.get("HX-Request"):
        html = render_to_string(
            "community/partials/lock_button.html",
            {"topic": topic},
            request=request
        )
        return HttpResponse(html)

    action = "verrouillé" if topic.is_locked else "déverrouillé"
    messages.success(request, f"Le sujet a été {action}.")

    return redirect(topic.get_absolute_url())


# =====================================================
# MODÉRATION STAFF
# =====================================================
@login_required
@require_POST
def moderate_delete_topic(request, slug):
    if not request.user.is_staff:
        return HttpResponseBadRequest("Permission refusée.")

    topic = get_object_or_404(Topic, slug=slug)
    topic.is_deleted = True
    topic.save(update_fields=["is_deleted"])

    messages.success(request, f"Le sujet '{topic.title}' a été supprimé.")
    return redirect("community:topic_list")


@login_required
@require_POST
def moderate_delete_answer(request, answer_id):
    if not request.user.is_staff:
        return HttpResponseBadRequest("Permission refusée.")

    answer = get_object_or_404(Answer, id=answer_id)
    topic = answer.topic

    answer.is_deleted = True
    answer.save(update_fields=["is_deleted"])

    if request.headers.get("HX-Request"):
        return HttpResponse(
            '<div class="bg-red-50 text-red-600 p-4 rounded-xl text-center text-sm">'
            'Réponse supprimée par un modérateur'
            '</div>'
        )

    messages.success(request, "La réponse a été supprimée.")
    return redirect(topic.get_absolute_url())
