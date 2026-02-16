from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from django.db.models import Count, F, Q
from django.contrib import messages

from .models import Article, Comment, Category, CommentLike
from .forms import ArticleForm
from .services import create_comment, approve_comment, react_to_comment
from .decorators import staff_required


# ==========================================================
# LISTE DES ARTICLES
# ==========================================================

def article_list(request):

    query = request.GET.get("q")

    articles = (
        Article.published
        .select_related("category", "author")
        .annotate(
            comments_count=Count(
                "comments",
                filter=Q(comments__status=Comment.STATUS_APPROVED)
            )
        )
    )

    if query:
        articles = articles.filter(
            Q(title__icontains=query) |
            Q(excerpt__icontains=query) |
            Q(content__icontains=query)
        )

    paginator = Paginator(articles, 6)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "blog/article_list.html", {
        "articles": page_obj,
        "categories": Category.objects.filter(is_active=True),
        "query": query,
    })


# ==========================================================
# DETAIL ARTICLE
# ==========================================================

def article_detail(request, slug):

    article = get_object_or_404(
        Article.objects.select_related("author", "category"),
        slug=slug,
        status="published",
        is_deleted=False
    )

    # Incrément compteur vues (thread-safe)
    Article.objects.filter(id=article.id).update(
        views_count=F("views_count") + 1
    )
    article.refresh_from_db()

    comments = (
        article.comments
        .filter(status=Comment.STATUS_APPROVED)
        .select_related("author_user")
        .annotate(
            like_count=Count(
                "reactions",
                filter=Q(reactions__reaction_type=CommentLike.REACTION_LIKE)
            ),
            dislike_count=Count(
                "reactions",
                filter=Q(reactions__reaction_type=CommentLike.REACTION_DISLIKE)
            )
        )
    )

    # Création commentaire
    if request.method == "POST" and article.allow_comments:

        if request.POST.get("website"):
            return redirect(article.get_absolute_url())

        try:
            create_comment(
                article=article,
                data=request.POST,
                user=request.user if request.user.is_authenticated else None
            )
            messages.success(request, "Votre commentaire a été publié.")
        except Exception as e:
            messages.error(request, str(e))

        return redirect(article.get_absolute_url())

    return render(request, "blog/article_detail.html", {
        "article": article,
        "comments": comments
    })


# ==========================================================
# FILTRE PAR CATEGORIE
# ==========================================================

def category_detail(request, slug):

    category = get_object_or_404(
        Category,
        slug=slug,
        is_active=True
    )

    articles = (
        Article.published
        .filter(category=category)
        .select_related("author", "category")
        .annotate(
            comments_count=Count(
                "comments",
                filter=Q(comments__status=Comment.STATUS_APPROVED)
            )
        )
    )

    paginator = Paginator(articles, 6)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "blog/category_detail.html", {
        "category": category,
        "articles": page_obj,
        "categories": Category.objects.filter(is_active=True)
    })


# ==========================================================
# CRUD ARTICLE
# ==========================================================

@staff_required
def article_create(request):

    form = ArticleForm(request.POST or None, request.FILES or None)

    if form.is_valid():
        article = form.save(commit=False)
        article.author = request.user
        article.save()
        form.save_m2m()
        messages.success(request, "Article créé avec succès.")
        return redirect(article.get_absolute_url())

    return render(request, "blog/articles/article_form.html", {
        "form": form,
        "title": "Créer un article"
    })


@staff_required
def article_edit(request, article_id):

    article = get_object_or_404(
        Article,
        id=article_id,
        is_deleted=False
    )

    form = ArticleForm(request.POST or None, request.FILES or None, instance=article)

    if form.is_valid():
        form.save()
        messages.success(request, "Article modifié avec succès.")
        return redirect(article.get_absolute_url())

    return render(request, "blog/articles/article_form.html", {
        "form": form,
        "title": "Modifier l’article"
    })


@staff_required
def article_delete(request, article_id):

    article = get_object_or_404(Article, id=article_id)

    article.is_deleted = True
    article.save(update_fields=["is_deleted"])

    messages.warning(request, "Article supprimé.")

    return redirect("blog:article_list")


# ==========================================================
# MODERATION COMMENTAIRES
# ==========================================================

@staff_required
def moderate_comments(request):

    comments = (
        Comment.objects
        .filter(status=Comment.STATUS_PENDING)
        .select_related("article", "author_user")
    )

    return render(request, "blog/moderate_comments.html", {
        "comments": comments
    })


@staff_required
@require_POST
def approve_comment_view(request, comment_id):

    comment = get_object_or_404(Comment, id=comment_id)

    approve_comment(comment, request.user)

    messages.success(request, "Commentaire approuvé.")

    return redirect("blog:moderate_comments")


# ==========================================================
# REACTION COMMENTAIRE (LIKE / DISLIKE)
# ==========================================================

from django.http import JsonResponse

@require_POST
def react_comment_view(request, comment_id):

    comment = get_object_or_404(Comment, id=comment_id)

    reaction_type = request.POST.get("reaction_type")

    try:
        react_to_comment(comment, request, reaction_type)
    except Exception:
        return JsonResponse({"error": "Invalid"}, status=400)

    # Recalcule compteurs
    like_count = comment.reactions.filter(
        reaction_type=CommentLike.REACTION_LIKE
    ).count()

    dislike_count = comment.reactions.filter(
        reaction_type=CommentLike.REACTION_DISLIKE
    ).count()

    return JsonResponse({
        "like_count": like_count,
        "dislike_count": dislike_count
    })


# ==========================================================
# CUSTOM 404
# ==========================================================

def custom_404(request, exception):
    return render(request, "404.html", status=404)
