import logging

from django.contrib import messages
from django.contrib.auth.models import User
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.template.loader import render_to_string
from django.db.models import Prefetch, Count, F, Q
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.contrib.auth import get_user_model

from .forms import TopicForm, ReportForm
from .models import Topic, Category, Answer, Vote, TopicView, Tag, Notification, Report
from community.services.notifications import create_notification
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
def build_topic_queryset(sort="active", query=""):
    queryset = (
        Topic.objects
        .filter(is_published=True, is_deleted=False)
        .select_related("author", "category")
        .prefetch_related("tags")
        .annotate(
            answer_count=Count(
                "answers",
                filter=Q(answers__is_deleted=False)
            )
        )
    )

    if query:
        queryset = queryset.filter(
            Q(title__icontains=query) |
            Q(content__icontains=query) |
            Q(tags__name__icontains=query) |
            Q(author__username__icontains=query) |
            Q(category__name__icontains=query)
        ).distinct()

    sort_map = {
        "recent": "-created_at",
        "answers": "-answer_count",
        "views": "-view_count",
        "active": "-last_activity_at",
    }

    return queryset.order_by(sort_map.get(sort, "-last_activity_at"))

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


# =====================================================
# LISTE GÉNÉRALE
# =====================================================
def topic_list(request):
    sort = request.GET.get("sort", "active")
    query = request.GET.get("q", "").strip()

    topics_qs = build_topic_queryset(sort=sort, query=query)
    page_obj = paginate_items(request, topics_qs, per_page=12)

    context = {
        "topics": page_obj.object_list,
        "topics_total": topics_qs.count(),
        "page_obj": page_obj,
        "current_sort": sort,
        "query": query,
        **build_sidebar_context(request),
    }

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

    tag = get_object_or_404(Tag, slug=slug)

    topics_qs = build_topic_queryset(sort=sort, query=query).filter(tags=tag)
    page_obj = paginate_items(request, topics_qs, per_page=12)

    context = {
        "topics": page_obj.object_list,
        "topics_total": topics_qs.count(),
        "page_obj": page_obj,
        "tag": tag,
        "current_sort": sort,
        "query": query,
        **build_sidebar_context(request),
    }

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

    category = get_object_or_404(Category, slug=slug, is_active=True)

    topics_qs = build_topic_queryset(sort=sort, query=query).filter(category=category)
    page_obj = paginate_items(request, topics_qs, per_page=12)

    context = {
        "topics": page_obj.object_list,
        "topics_total": topics_qs.count(),
        "page_obj": page_obj,
        "category": category,
        "current_sort": sort,
        "query": query,
        **build_sidebar_context(request),
    }

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
    similar_topics = (
        Topic.objects
        .filter(
            category=topic.category,
            is_published=True,
            is_deleted=False
        )
        .exclude(pk=topic.pk)
        .select_related("author")
        .annotate(answer_count=Count("answers", filter=Q(answers__is_deleted=False)))
        .order_by("-view_count")[:5]
    )

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
        "similar_topics": similar_topics,
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

    # NOTIFICATIONS
    if topic.author != request.user:
        try:
            create_notification(
                user=topic.author,
                actor=request.user,
                topic=topic,
                answer=answer,
                notification_type="new_answer",
                send_email=False
            )
        except Exception as exc:
            logger.exception("Echec notification nouvelle reponse auteur topic=%s: %s", topic.id, exc)

    try:
        previous_responders = (
            Answer.objects
            .filter(topic=topic, is_deleted=False)
            .exclude(author=request.user)
            .exclude(author=topic.author)
            .values_list("author_id", flat=True)
            .distinct()
        )

        for responder_id in previous_responders:
            existing_notification = Notification.objects.filter(
                user_id=responder_id,
                actor=request.user,
                topic=topic,
                answer=answer,
                notification_type="new_answer"
            ).exists()

            if not existing_notification:
                try:
                    create_notification(
                        user_id=responder_id,
                        actor=request.user,
                        topic=topic,
                        answer=answer,
                        notification_type="new_answer",
                        send_email=False
                    )
                except Exception as exc:
                    logger.warning(
                        "Echec notification responder_id=%s topic=%s: %s",
                        responder_id,
                        topic.id,
                        exc,
                    )
    except Exception as exc:
        logger.exception("Echec boucle notifications reponse topic=%s: %s", topic.id, exc)

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
# NOTIFICATIONS
# =====================================================
@login_required
def notifications(request):

    notification_type = request.GET.get("type", "")
    is_read = request.GET.get("is_read", "")

    notifications_qs = (
        Notification.objects
        .filter(user=request.user)
        .select_related("actor", "topic", "topic__category", "answer", "answer__author")
    )

    if notification_type:
        notifications_qs = notifications_qs.filter(notification_type=notification_type)

    if is_read == "true":
        notifications_qs = notifications_qs.filter(is_read=True)
    elif is_read == "false":
        notifications_qs = notifications_qs.filter(is_read=False)

    paginator = Paginator(notifications_qs, 20)
    page = request.GET.get("page", 1)

    try:
        notifications_page = paginator.page(page)
    except PageNotAnInteger:
        notifications_page = paginator.page(1)
    except EmptyPage:
        notifications_page = paginator.page(paginator.num_pages)

    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    total_count = Notification.objects.filter(user=request.user).count()


    if request.headers.get("HX-Request"):
        return render(
            request,
            "community/partials/notifications_list.html",
            {"notifications": notifications_page, "page_obj": notifications_page}
        )

    return render(request, "community/notifications.html", {
        "notifications": notifications_page,
        "page_obj": notifications_page,
        "unread_count": unread_count,
        "total_count": total_count,
        "current_type": notification_type,
        "current_is_read": is_read,
    })


@login_required
def notifications_partial(request):
    notifications = (
        Notification.objects
        .filter(user=request.user)
        .select_related("actor", "topic", "topic__category", "answer")
        .order_by("-created_at")[:7]
    )

    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()

    return render(
        request,
        "community/partials/notifications_dropdown.html",
        {"notifications": notifications, "unread_count": unread_count}
    )


@login_required
@require_POST
def mark_notification_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.mark_as_read()

    if request.headers.get("HX-Request"):
        return render(
            request,
            "community/partials/notification_item.html",
            {"notification": notification}
        )

    return HttpResponse(status=204)


@login_required
@require_POST
def mark_all_notifications_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(
        is_read=True,
        read_at=timezone.now()
    )

    if request.headers.get("HX-Request"):
        return HttpResponse("")

    messages.success(request, "Toutes les notifications ont été marquées comme lues.")
    return redirect("community:notifications")


@login_required
@require_POST
def delete_notification(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.delete()

    if request.headers.get("HX-Request"):
        return HttpResponse("")

    return HttpResponse(status=204)


@login_required
def notifications_unread_count(request):
    count = Notification.objects.filter(user=request.user, is_read=False).count()

    if request.headers.get("HX-Request"):
        return HttpResponse(f'<span id="unread-count">{count}</span>')

    return JsonResponse({"unread_count": count})


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
                from community.services.notifications import notify_accepted_answer
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