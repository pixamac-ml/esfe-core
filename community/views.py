from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.template.loader import render_to_string
from django.db.models import Prefetch, Count, F, Q
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import Topic, Category, Answer, Vote, TopicView


from django.shortcuts import render, get_object_or_404
from django.db.models import Count, Q
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.contrib.auth import get_user_model

from .models import Topic, Category, Tag

User = get_user_model()


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
            Q(tags__name__icontains=query)
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
def build_sidebar_context():

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

    top_users = (
        User.objects
        .select_related("profile")
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
    }


# =====================================================
# LISTE GÉNÉRALE
# =====================================================
def topic_list(request):

    sort = request.GET.get("sort", "active")
    query = request.GET.get("q", "").strip()

    topics = build_topic_queryset(sort=sort, query=query)

    context = {
        "topics": topics,
        "current_sort": sort,
        "query": query,
        **build_sidebar_context(),
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

    topics = build_topic_queryset(sort=sort, query=query).filter(tags=tag)

    context = {
        "topics": topics,
        "tag": tag,
        "current_sort": sort,
        "query": query,
        **build_sidebar_context(),
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

    topics = build_topic_queryset(sort=sort, query=query).filter(category=category)

    context = {
        "topics": topics,
        "category": category,
        "current_sort": sort,
        "query": query,
        **build_sidebar_context(),
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
# DÉTAIL D’UN SUJET
# =====================================================
def topic_detail(request, slug):
    topic = get_object_or_404(
        Topic.objects.select_related("author", "category"),
        slug=slug,
        is_published=True
    )

    # ==============================
    # Anti-refresh intelligent
    # ==============================
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

    # ==============================
    # Réponses principales
    # ==============================
    root_answers = (
        Answer.objects
        .filter(topic=topic, parent__isnull=True, is_deleted=False)
        .select_related("author")
        .prefetch_related(
            Prefetch(
                "replies",
                queryset=Answer.objects
                .filter(is_deleted=False)
                .select_related("author")
                .order_by("-upvotes", "created_at")
            )
        )
        .order_by("-upvotes", "created_at")
    )

    # ==============================
    # Mettre accepted_answer en premier
    # ==============================
    if topic.accepted_answer:
        accepted = topic.accepted_answer
        root_answers = sorted(
            root_answers,
            key=lambda a: a.id != accepted.id
        )

    return render(request, "community/topic_detail.html", {
        "topic": topic,
        "answers": root_answers,
    })


# =====================================================
# AJOUT RÉPONSE (HTMX)
# =====================================================
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, HttpResponseBadRequest
from django.template.loader import render_to_string
from django.utils import timezone

@login_required
@require_POST
def add_answer(request, slug):

    # ===============================
    # Récupération du sujet
    # ===============================
    topic = get_object_or_404(
        Topic.objects.select_related("author", "category"),
        slug=slug,
        is_locked=False,
        is_published=True
    )

    # ===============================
    # Récupération contenu
    # ===============================
    content = request.POST.get("content", "").strip()

    if not content:
        return HttpResponseBadRequest("Contenu vide ou invalide.")

    # ===============================
    # Gestion réponse ou sous-réponse
    # ===============================
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

    # ===============================
    # Création réponse
    # ===============================
    answer = Answer.objects.create(
        topic=topic,
        author=request.user,
        content=content,
        parent=parent
    )

    # ===============================
    # Mise à jour activité du sujet
    # ===============================
    Topic.objects.filter(pk=topic.pk).update(
        last_activity_at=timezone.now()
    )

    # ===============================
    # Préchargement auteur pour template
    # ===============================
    answer = (
        Answer.objects
        .select_related("author")
        .get(pk=answer.pk)
    )

    # ===============================
    # Réponse HTMX
    # ===============================
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

    # ===============================
    # Fallback (sécurité)
    # ===============================
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



from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone

from .forms import TopicForm
from community.services.notifications import create_notification


@login_required
def create_topic(request):

    # ==================================================
    # POST : création du sujet
    # ==================================================

    if request.method == "POST":

        form = TopicForm(request.POST, request.FILES)

        if form.is_valid():

            topic = form.save(commit=False)
            topic.author = request.user
            topic.last_activity_at = timezone.now()
            topic.save()

            form.save_m2m()

            category = topic.category

            # ==================================================
            # AUTO-ABONNEMENT OPTIONNEL
            # ==================================================

            if form.cleaned_data.get("subscribe"):
                try:
                    category.subscribers.add(request.user)
                except Exception:
                    pass

            # ==================================================
            # NOTIFICATIONS DES ABONNÉS
            # ==================================================

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

                except Exception:
                    # sécurité : ne jamais casser la création du topic
                    pass

            # ==================================================
            # REDIRECTION HTMX
            # ==================================================

            if request.headers.get("HX-Request"):

                response = HttpResponse()
                response["HX-Redirect"] = topic.get_absolute_url()
                return response

            # ==================================================
            # REDIRECTION CLASSIQUE
            # ==================================================

            return redirect(topic.get_absolute_url())

        # ==================================================
        # ERREURS FORMULAIRE (HTMX)
        # ==================================================

        if request.headers.get("HX-Request"):

            html = render_to_string(
                "community/partials/topic_form.html",
                {"form": form},
                request=request
            )

            return HttpResponse(html)

    # ==================================================
    # GET : affichage du formulaire
    # ==================================================

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


from django.contrib.auth import get_user_model
from django.db.models import Count, Q



def members_list(request):

    users = (
        User.objects
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

    return render(request, "community/members_list.html", {
        "users": users
    })




# ==========================================
# PROFIL PUBLIC UTILISATEUR
# ==========================================

from django.shortcuts import render, get_object_or_404
from django.contrib.auth import get_user_model
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce

from .models import Category

User = get_user_model()


def public_profile(request, username):

    user = get_object_or_404(
        User.objects.select_related("profile"),
        username=username
    )

    profile = user.profile

    # ======================================
    # SUJETS DE L'UTILISATEUR
    # ======================================

    topics = (
        user.community_topics
        .filter(is_deleted=False)
        .select_related("category")
        .annotate(answer_count=Count("answers"))
        .order_by("-created_at")
    )

    # ======================================
    # RÉPONSES UTILISATEUR
    # ======================================

    answers = (
        user.community_answers
        .filter(is_deleted=False)
        .select_related("topic")
        .order_by("-created_at")
    )

    # ======================================
    # CONTRIBUTIONS POPULAIRES
    # ======================================

    best_answers = answers.order_by("-upvotes")[:5]

    # ======================================
    # DOMAINES D'ACTIVITÉ
    # ======================================

    top_categories = (
        Category.objects
        .filter(topics__answers__author=user)
        .annotate(
            answer_count=Count("topics__answers")
        )
        .order_by("-answer_count")[:5]
    )

    # ======================================
    # STATISTIQUES
    # ======================================

    total_upvotes = answers.aggregate(
        total=Coalesce(Sum("upvotes"), 0)
    )["total"]

    total_downvotes = answers.aggregate(
        total=Coalesce(Sum("downvotes"), 0)
    )["total"]

    score = total_upvotes - total_downvotes

    stats = {
        "topics": profile.total_topics,
        "answers": profile.total_answers,
        "accepted": profile.total_accepted_answers,
        "upvotes": total_upvotes,
        "views": profile.total_views_generated,
        "reputation": score,
    }

    # ======================================
    # ACTIVITÉ RÉCENTE
    # ======================================

    recent_activity = list(answers[:5]) + list(topics[:5])
    recent_activity = sorted(
        recent_activity,
        key=lambda x: x.created_at,
        reverse=True
    )[:8]

    # ======================================
    # CONTEXTE TEMPLATE
    # ======================================

    context = {
        "profile_user": user,
        "profile": profile,

        "topics": topics[:5],
        "answers": answers[:5],

        "best_answers": best_answers,
        "top_categories": top_categories,

        "recent_activity": recent_activity,

        "stats": stats,
    }

    return render(
        request,
        "community/public_profile.html",
        context
    )

def profile_activity(request, username):

    if not request.htmx:
        return redirect("community:public_profile", username=username)

    user = get_object_or_404(
        User.objects.select_related("profile"),
        username=username
    )

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
        {
            "profile_user": user,
            "answers": answers,
            "topics": topics,
        },
    )

def profile_answers(request, username):

    if not request.htmx:
        return redirect("community:public_profile", username=username)

    user = get_object_or_404(
        User.objects.select_related("profile"),
        username=username
    )

    answers = (
        user.community_answers
        .filter(is_deleted=False)
        .select_related("topic", "topic__category")
        .order_by("-created_at")
    )

    return render(
        request,
        "community/partials/profile/answers.html",
        {
            "profile_user": user,
            "answers": answers,
        },
    )

from django.db.models import Count


def profile_topics(request, username):

    if not request.htmx:
        return redirect("community:public_profile", username=username)

    user = get_object_or_404(
        User.objects.select_related("profile"),
        username=username
    )

    topics = (
        user.community_topics
        .filter(is_deleted=False)
        .select_related("category")
        .annotate(
            answers_count=Count("answers")
        )
        .order_by("-created_at")
    )

    return render(
        request,
        "community/partials/profile/topics.html",
        {
            "profile_user": user,
            "topics": topics,
        },
    )


from django.db.models import Count
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import get_user_model

User = get_user_model()


def profile_badges(request, username):

    if not request.htmx:
        return redirect("community:public_profile", username=username)

    user = get_object_or_404(
        User.objects.select_related("profile"),
        username=username
    )

    answers = (
        user.community_answers
        .filter(is_deleted=False)
    )

    topics = (
        user.community_topics
        .filter(is_deleted=False)
    )

    # statistiques
    answers_count = answers.count()

    accepted_answers = answers.filter(
        accepted_for_topics__isnull=False
    ).count()

    upvotes = answers.aggregate(
        total=Count("votes")
    )["total"] or 0

    # logique badges

    badges = {

        "beginner": {
            "title": "Débutant",
            "description": "Première réponse publiée",
            "icon": "award",
            "earned": answers_count >= 1,
            "progress": min(answers_count, 1),
            "target": 1,
        },

        "contributor": {
            "title": "Contributeur",
            "description": "10 réponses utiles",
            "icon": "star",
            "earned": answers_count >= 10,
            "progress": min(answers_count, 10),
            "target": 10,
        },

        "expert": {
            "title": "Expert",
            "description": "50 réponses utiles",
            "icon": "medal",
            "earned": answers_count >= 50,
            "progress": min(answers_count, 50),
            "target": 50,
        },

        "specialist": {
            "title": "Spécialiste",
            "description": "Réponse acceptée comme solution",
            "icon": "brain",
            "earned": accepted_answers >= 5,
            "progress": min(accepted_answers, 5),
            "target": 5,
        },

    }

    return render(
        request,
        "community/partials/profile/badges.html",
        {
            "profile_user": user,
            "badges": badges,
        },
    )

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.db.models import Prefetch
from django.utils import timezone

from .models import Notification


@login_required
def notifications(request):

    # ==============================
    # Récupération optimisée
    # ==============================

    notifications = (
        Notification.objects
        .filter(user=request.user)
        .select_related(
            "actor",
            "topic",
            "answer"
        )
        .order_by("-created_at")
    )

    # ==============================
    # Statistiques rapides
    # ==============================

    unread_count = notifications.filter(is_read=False).count()

    # ==============================
    # Marquer comme lues
    # ==============================

    notifications.filter(is_read=False).update(
        is_read=True
    )

    # ==============================
    # Contexte
    # ==============================

    context = {
        "notifications": notifications,
        "unread_count": unread_count,
    }

    return render(
        request,
        "community/notifications.html",
        context
    )