# services.py
from django.utils import timezone

def publish_news(news, user):
    if news.status != 'draft':
        return False

    news.status = 'published'
    news.published_at = timezone.now()
    news.auteur = user
    news.save(update_fields=['status', 'published_at', 'auteur'])
    return True
