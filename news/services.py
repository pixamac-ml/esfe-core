from django.utils import timezone
from django.db import transaction

from .models import News


@transaction.atomic
def publish_news(news: News, user) -> bool:
    """
    Publie une actualité si elle est en brouillon.
    Retourne True si publication réussie, sinon False.
    """

    if news.status != News.STATUS_DRAFT:
        return False

    news.status = News.STATUS_PUBLISHED
    news.published_at = timezone.now()
    news.auteur = user

    news.save(update_fields=["status", "published_at", "auteur"])

    return True


@transaction.atomic
def archive_news(news: News) -> bool:
    """
    Archive une actualité publiée.
    """

    if news.status != News.STATUS_PUBLISHED:
        return False

    news.status = News.STATUS_ARCHIVED
    news.save(update_fields=["status"])

    return True
