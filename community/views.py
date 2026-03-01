from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.template.loader import render_to_string
from django.db.models import Prefetch, Count, F
from django.views.decorators.http import require_POST

from .models import Topic, Category, Answer, Vote


# ==========================
# LISTE PAR CATÉGORIE
# ==========================
def topic_by_category(request, slug):
    category = get_object_or_404(Category, slug=slug)

    topics = (
        Topic.objects
        .filter(category=category, is_published=True)
        .select_related("author", "category")
        .annotate(answer_count=Count("answers"))
        .order_by("-created_at")
    )

    categories = Category.objects.all()

    return render(request, "community/topic_list.html", {
        "category": category,
        "topics": topics,
        "categories": categories,
    })


# ==========================
# LISTE GÉNÉRALE
# ==========================
def topic_list(request):
    topics = (
        Topic.objects
        .filter(is_published=True)
        .select_related("author", "category")
        .annotate(answer_count=Count("answers"))
        .order_by("-created_at")
    )

    categories = Category.objects.all()

    return render(request, "community/topic_list.html", {
        "topics": topics,
        "categories": categories,
    })


# ==========================
# DÉTAIL D’UN SUJET
# ==========================
def topic_detail(request, slug):
    topic = get_object_or_404(
        Topic.objects.select_related("author", "category"),
        slug=slug,
        is_published=True
    )

    # Incrément propre du compteur de vues
    Topic.objects.filter(pk=topic.pk).update(view_count=F("view_count") + 1)
    topic.refresh_from_db(fields=["view_count"])

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
            )
        )
        .order_by("-upvotes", "created_at")
    )

    return render(request, "community/topic_detail.html", {
        "topic": topic,
        "answers": root_answers,
    })


# ==========================
# AJOUT RÉPONSE (HTMX)
# ==========================
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


# ==========================
# VOTE RÉPONSE (HTMX)
# ==========================
@login_required
@require_POST
def vote_answer(request, answer_id):
    answer = get_object_or_404(Answer, id=answer_id)

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
            f'<div class="vote-count fw-bold fs-5 text-success">{answer.upvotes}</div>'
        )

    return HttpResponse(status=204)