from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.template.loader import render_to_string
from django.db.models import Prefetch, Count, F, Q
from django.views.decorators.http import require_POST
from django.utils import timezone

from .models import Topic, Category, Answer, Vote, TopicView


# =====================================================
# LISTE PAR CATÉGORIE (Domaine)
# =====================================================
def topic_by_category(request, slug):
    category = get_object_or_404(Category, slug=slug, is_active=True)

    topics = (
        Topic.objects
        .filter(category=category, is_published=True)
        .select_related("author", "category")
        .annotate(answer_count=Count("answers", filter=Q(answers__is_deleted=False)))
        .order_by("-last_activity_at")
    )

    categories = Category.objects.filter(is_active=True)

    return render(request, "community/topic_list.html", {
        "category": category,
        "topics": topics,
        "categories": categories,
    })


# =====================================================
# LISTE GÉNÉRALE
# =====================================================
def topic_list(request):
    topics = (
        Topic.objects
        .filter(is_published=True)
        .select_related("author", "category")
        .annotate(answer_count=Count("answers", filter=Q(answers__is_deleted=False)))
        .order_by("-last_activity_at")
    )

    categories = Category.objects.filter(is_active=True)

    return render(request, "community/topic_list.html", {
        "topics": topics,
        "categories": categories,
    })


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
@login_required
@require_POST
def add_answer(request, slug):
    topic = get_object_or_404(
        Topic,
        slug=slug,
        is_locked=False,
        is_published=True
    )

    content = request.POST.get("content")

    if not content or not content.strip():
        return HttpResponseBadRequest("Contenu invalide.")

    parent_id = request.POST.get("parent_id")
    parent = None

    if parent_id:
        parent = Answer.objects.filter(
            id=parent_id,
            topic=topic
        ).first()

    answer = Answer.objects.create(
        topic=topic,
        author=request.user,
        content=content.strip(),
        parent=parent
    )

    # Mise à jour activité du topic
    topic.last_activity_at = timezone.now()
    topic.save(update_fields=["last_activity_at"])

    if request.headers.get("HX-Request"):
        template_name = "community/partials/answer_item.html"
        if parent:
            template_name = "community/partials/reply_item.html"

        html = render_to_string(
            template_name,
            {"answer": answer},
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

from .models import Topic, Category, Answer, Vote, TopicView, Tag


# =====================================================
# LISTE PAR TAG
# =====================================================
def topic_by_tag(request, slug):
    tag = get_object_or_404(Tag, slug=slug)

    topics = (
        Topic.objects
        .filter(
            tags=tag,
            is_published=True
        )
        .select_related("author", "category")
        .annotate(
            answer_count=Count(
                "answers",
                filter=Q(answers__is_deleted=False)
            )
        )
        .order_by("-last_activity_at")
    )

    categories = Category.objects.filter(is_active=True)

    return render(request, "community/topic_list.html", {
        "tag": tag,
        "topics": topics,
        "categories": categories,
    })

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone

from .forms import TopicForm


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

            # 🔥 Si requête HTMX → redirection dynamique
            if request.headers.get("HX-Request"):
                response = HttpResponse()
                response["HX-Redirect"] = topic.get_absolute_url()
                return response

            # Fallback classique
            return redirect(topic.get_absolute_url())

        # 🔁 Si erreurs + HTMX → renvoyer uniquement le formulaire
        if request.headers.get("HX-Request"):
            html = render_to_string(
                "community/partials/topic_form.html",
                {"form": form},
                request=request
            )
            return HttpResponse(html)

    else:
        form = TopicForm()

    return render(request, "community/create_topic.html", {"form": form})


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