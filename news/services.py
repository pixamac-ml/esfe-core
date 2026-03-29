from django.utils import timezone
from django.db import transaction
from django.core.exceptions import ValidationError
from pathlib import Path

from .models import News, MediaItem


SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}


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


def _detect_media_type(uploaded_file):
    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()
    extension = Path(getattr(uploaded_file, "name", "")).suffix.lower()

    if content_type.startswith("image/") or extension in SUPPORTED_IMAGE_EXTENSIONS:
        return MediaItem.IMAGE
    if content_type.startswith("video/") or extension in SUPPORTED_VIDEO_EXTENSIONS:
        return MediaItem.VIDEO
    return None


def create_event_media_batch(event, files, *, is_featured=False, use_filename_caption=True, max_files=50):
    """Crée des MediaItem en lot et renvoie un rapport exploitable côté UI."""
    created_items = []
    errors = []

    uploads = list(files or [])
    if not uploads:
        return {"created": created_items, "errors": ["Aucun fichier reçu."]}

    if len(uploads) > max_files:
        errors.append(f"Lot limité à {max_files} fichiers. Les premiers seront traités.")
        uploads = uploads[:max_files]

    for uploaded_file in uploads:
        media_type = _detect_media_type(uploaded_file)
        file_name = getattr(uploaded_file, "name", "fichier")

        if not media_type:
            errors.append(f"Type non supporté: {file_name}")
            continue

        media_item = MediaItem(
            event=event,
            media_type=media_type,
            image=uploaded_file if media_type == MediaItem.IMAGE else None,
            video_file=uploaded_file if media_type == MediaItem.VIDEO else None,
            caption=Path(file_name).stem if use_filename_caption else "",
            is_featured=is_featured,
        )

        try:
            media_item.full_clean()
            media_item.save()
            created_items.append(media_item)
        except ValidationError as exc:
            text = "; ".join(exc.messages) if getattr(exc, "messages", None) else str(exc)
            errors.append(f"{file_name}: {text}")
        except Exception as exc:
            errors.append(f"{file_name}: {exc}")

    return {"created": created_items, "errors": errors}

