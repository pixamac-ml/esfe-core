from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from django.db.models import Count
from django.contrib.auth.decorators import login_required

from .models import Article, Comment, Category
from .forms import ArticleForm
from .services import create_comment, approve_comment, like_comment
from .decorators import staff_required


# ==========================================================
# LISTE DES ARTICLES
# ==========================================================

def article_list(request):
    articles = (
        Article.published
        .select_related('category')
        .annotate(comments_count=Count('comments'))
    )

    paginator = Paginator(articles, 6)
    page_number = request.GET.get('page')
    articles = paginator.get_page(page_number)

    return render(request, 'blog/article_list.html', {
        'articles': articles,
        'categories': Category.objects.filter(is_active=True)
    })


# ==========================================================
# DETAIL ARTICLE
# ==========================================================

def article_detail(request, slug):
    article = get_object_or_404(
        Article.objects.select_related('author', 'category'),
        slug=slug,
        status='published',
        is_deleted=False
    )

    comments = (
        article.comments
        .filter(status='approved')
        .annotate(likes_count=Count('likes'))
    )

    if request.method == 'POST' and article.allow_comments:

        # Honeypot anti-spam
        if request.POST.get("website"):
            return redirect(article.get_absolute_url())

        create_comment(
            article=article,
            data=request.POST,
            user=request.user if request.user.is_authenticated else None
        )

        return redirect(article.get_absolute_url())

    return render(request, 'blog/article_detail.html', {
        'article': article,
        'comments': comments
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
        .select_related('author')
    )

    paginator = Paginator(articles, 6)
    page_number = request.GET.get('page')
    articles = paginator.get_page(page_number)

    return render(request, 'blog/category_detail.html', {
        'category': category,
        'articles': articles
    })


# ==========================================================
# CRUD ARTICLE (STAFF UNIQUEMENT)
# ==========================================================

@staff_required
def article_create(request):
    form = ArticleForm(request.POST or None)

    if form.is_valid():
        article = form.save(commit=False)
        article.author = request.user
        article.save()
        form.save_m2m()
        return redirect(article.get_absolute_url())

    return render(request, 'blog/articles/article_form.html', {
        'form': form,
        'title': 'Créer un article'
    })


@staff_required
def article_edit(request, article_id):
    article = get_object_or_404(
        Article,
        id=article_id,
        is_deleted=False
    )

    form = ArticleForm(request.POST or None, instance=article)

    if form.is_valid():
        form.save()
        return redirect(article.get_absolute_url())

    return render(request, 'blog/articles/article_form.html', {
        'form': form,
        'title': 'Modifier l’article'
    })


@staff_required
def article_delete(request, article_id):
    article = get_object_or_404(Article, id=article_id)

    article.is_deleted = True
    article.save(update_fields=['is_deleted'])

    return redirect('blog:article_list')


# ==========================================================
# MODERATION COMMENTAIRES
# ==========================================================

@staff_required
def moderate_comments(request):
    comments = (
        Comment.objects
        .filter(status='pending')
        .select_related('article')
    )

    return render(request, 'blog/moderate_comments.html', {
        'comments': comments
    })


@staff_required
@require_POST
def approve_comment_view(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    approve_comment(comment, request.user)
    return redirect('blog:moderate_comments')


# ==========================================================
# LIKE COMMENTAIRE
# ==========================================================

@require_POST
def like_comment_view(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)

    # Empêche le like sur commentaire non approuvé
    if comment.status != 'approved':
        return redirect(comment.article.get_absolute_url())

    like_comment(comment, request)
    return redirect(comment.article.get_absolute_url())


# ==========================================================
# CUSTOM 404
# ==========================================================

def custom_404(request, exception):
    return render(request, '404.html', status=404)
