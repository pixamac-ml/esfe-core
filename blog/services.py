from django.utils import timezone
from .models import Comment


SENSITIVE_KEYWORDS = [
    'fraude', 'argent', 'paiement', 'corruption',
    'faux', 'escroquerie', 'arnaque'
]


def must_be_moderated(content: str) -> bool:
    content = content.lower()
    return any(word in content for word in SENSITIVE_KEYWORDS)


def create_comment(article, data, user=None):
    status = 'approved'

    if must_be_moderated(data['content']):
        status = 'pending'

    if not user:
        status = 'pending'

    comment = Comment.objects.create(
        article=article,
        author_name=data['author_name'],
        author_email=data.get('author_email'),
        content=data['content'],
        author_user=user,
        status=status
    )

    return comment


def approve_comment(comment, moderator):
    comment.status = 'approved'
    comment.approved_by = moderator
    comment.approved_at = timezone.now()
    comment.save()


from .models import CommentLike


def like_comment(comment, request):
    ip = request.META.get('REMOTE_ADDR')

    CommentLike.objects.get_or_create(
        comment=comment,
        user=request.user if request.user.is_authenticated else None,
        ip_address=ip
    )
