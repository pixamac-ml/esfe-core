from django.utils import timezone
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Comment, CommentLike


# ==========================================================
# CONFIGURATION MODERATION
# ==========================================================

SENSITIVE_KEYWORDS = [
    "fraude", "argent", "paiement", "corruption",
    "faux", "escroquerie", "arnaque"
]

MAX_COMMENT_LENGTH = 2000
MIN_COMMENT_LENGTH = 3
FLOOD_DELAY_SECONDS = 60


# ==========================================================
# UTILITAIRE : Détection mots sensibles
# ==========================================================

def must_be_flagged(content: str) -> bool:
    if not content:
        return True

    content = content.lower()
    return any(word in content for word in SENSITIVE_KEYWORDS)


# ==========================================================
# VALIDATION INTERNE COMMENTAIRE
# ==========================================================

def validate_comment_content(content: str):
    if not content:
        raise ValidationError("Le commentaire ne peut pas être vide.")

    if len(content) < MIN_COMMENT_LENGTH:
        raise ValidationError("Commentaire trop court.")

    if len(content) > MAX_COMMENT_LENGTH:
        raise ValidationError("Commentaire trop long.")


# ==========================================================
# ANTI-FLOOD SIMPLE
# ==========================================================

def is_flooding(article, content, user):
    threshold = timezone.now() - timezone.timedelta(seconds=FLOOD_DELAY_SECONDS)

    filters = {
        "article": article,
        "content": content,
        "created_at__gte": threshold,
    }

    if user and user.is_authenticated:
        filters["author_user"] = user

    return Comment.objects.filter(**filters).exists()


# ==========================================================
# CREATION COMMENTAIRE
# ==========================================================

def create_comment(article, data, user=None):

    content = (data.get("content") or "").strip()
    author_name = (data.get("author_name") or "").strip()
    author_email = (data.get("author_email") or "").strip()

    validate_comment_content(content)

    if not author_name:
        author_name = "Utilisateur"

    if is_flooding(article, content, user):
        raise ValidationError("Vous venez déjà de publier ce commentaire.")

    flagged = must_be_flagged(content)

    comment = Comment.objects.create(
        article=article,
        author_name=author_name,
        author_email=author_email or None,
        content=content,
        author_user=user if user and user.is_authenticated else None,
        status=Comment.STATUS_APPROVED,
        flagged=flagged
    )

    return comment


# ==========================================================
# APPROBATION COMMENTAIRE
# ==========================================================

def approve_comment(comment, moderator):
    if comment.status == Comment.STATUS_APPROVED:
        return comment

    comment.status = Comment.STATUS_APPROVED
    comment.approved_by = moderator
    comment.approved_at = timezone.now()
    comment.save(update_fields=["status", "approved_by", "approved_at"])
    return comment


# ==========================================================
# REJET COMMENTAIRE
# ==========================================================

def reject_comment(comment, moderator):
    comment.status = Comment.STATUS_REJECTED
    comment.approved_by = moderator
    comment.approved_at = timezone.now()
    comment.save(update_fields=["status", "approved_by", "approved_at"])
    return comment


# ==========================================================
# UTILITAIRE IP ROBUSTE
# ==========================================================

def get_client_ip(request):
    """
    Récupération IP compatible reverse proxy / production.
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


# ==========================================================
# REACTION COMMENTAIRE (LIKE / DISLIKE)
# ==========================================================

@transaction.atomic
def react_to_comment(comment, request, reaction_type):

    if comment.status != Comment.STATUS_APPROVED:
        return None

    if reaction_type not in [
        CommentLike.REACTION_LIKE,
        CommentLike.REACTION_DISLIKE
    ]:
        raise ValidationError("Type de réaction invalide.")

    ip = get_client_ip(request)
    user = request.user if request.user.is_authenticated else None

    if not ip:
        return None

    # ===============================
    # Recherche réaction existante
    # ===============================

    if user:
        existing = CommentLike.objects.filter(
            comment=comment,
            user=user
        ).first()
    else:
        existing = CommentLike.objects.filter(
            comment=comment,
            user__isnull=True,
            ip_address=ip
        ).first()

    # ===============================
    # Toggle logique
    # ===============================

    if existing:
        # Même réaction → on supprime (toggle off)
        if existing.reaction_type == reaction_type:
            existing.delete()
            return None

        # Réaction différente → on met à jour
        existing.reaction_type = reaction_type
        existing.save(update_fields=["reaction_type"])
        return existing

    # ===============================
    # Nouvelle réaction
    # ===============================

    return CommentLike.objects.create(
        comment=comment,
        user=user,
        ip_address=ip,
        reaction_type=reaction_type
    )