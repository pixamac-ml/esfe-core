from django.contrib.auth import get_user_model
from django.db.models import Q

from academics.models import AcademicEnrollment


STUDENT_ROLE_TOKENS = {"student", "students", "etudiant", "etudiants"}


def resolve_candidate_user_by_email(email):
    """Resolve an in-app candidate recipient without ever selecting staff.

    Candidature currently has no direct user foreign key, so email is only a
    lookup hint. A match is accepted only when it uniquely identifies an
    active student or an unprivileged public account. Ambiguous matches remain
    email-only notifications.
    """
    normalized_email = str(email or "").strip()
    if not normalized_email:
        return None

    User = get_user_model()
    eligible_users = list(
        User.objects.filter(
            email__iexact=normalized_email,
            is_active=True,
            is_staff=False,
            is_superuser=False,
        )
        .filter(
            Q(student_profile__isnull=False)
            | Q(profile__role="student")
            | Q(profile__position="student")
            | Q(
                profile__user_type="public",
                profile__role="",
                profile__position="",
            )
        )
        .distinct()
        .order_by("id")[:2]
    )
    return eligible_users[0] if len(eligible_users) == 1 else None


def restrict_candidate_channels(recipient, channels):
    """Keep in-app delivery only when a verified platform recipient exists."""
    from notifier.models import NotificationMessage

    resolved = tuple(channels or ())
    if recipient is not None:
        return resolved
    return tuple(
        channel
        for channel in resolved
        if channel != NotificationMessage.CHANNEL_IN_APP
        and channel != NotificationMessage.CHANNEL_WEBSOCKET
    )


def resolve_platform_users(
    *,
    audience_scope="all",
    branch_ids=None,
    programme_ids=None,
    cycle_ids=None,
    class_ids=None,
    role_tokens=None,
    user_types=None,
):
    User = get_user_model()
    users = User.objects.filter(is_active=True).select_related("profile")
    branch_ids = [item for item in (branch_ids or []) if item]
    programme_ids = [item for item in (programme_ids or []) if item]
    cycle_ids = [item for item in (cycle_ids or []) if item]
    class_ids = [item for item in (class_ids or []) if item]
    role_tokens = [str(item).strip() for item in (role_tokens or []) if str(item).strip()]
    user_types = [str(item).strip() for item in (user_types or []) if str(item).strip()]

    if audience_scope == "all":
        if role_tokens:
            users = users.filter(Q(profile__role__in=role_tokens) | Q(profile__position__in=role_tokens))
        if user_types:
            users = users.filter(profile__user_type__in=user_types)
        return users.distinct()

    if not any([branch_ids, programme_ids, cycle_ids, class_ids, role_tokens, user_types]):
        return users.none()

    recipient_ids = set()

    staff_users = users.filter(profile__isnull=False)
    if branch_ids:
        staff_users = staff_users.filter(profile__branch_id__in=branch_ids)
    if role_tokens:
        staff_users = staff_users.filter(Q(profile__role__in=role_tokens) | Q(profile__position__in=role_tokens))
    if user_types:
        staff_users = staff_users.filter(profile__user_type__in=user_types)
    if branch_ids or role_tokens or user_types:
        recipient_ids.update(staff_users.values_list("id", flat=True))

    enrollments = AcademicEnrollment.objects.filter(
        is_active=True,
        is_archived=False,
        status=AcademicEnrollment.STATUS_ACTIVE,
        student__is_active=True,
    )
    if branch_ids:
        enrollments = enrollments.filter(branch_id__in=branch_ids)
    if programme_ids:
        enrollments = enrollments.filter(programme_id__in=programme_ids)
    if cycle_ids:
        enrollments = enrollments.filter(programme__cycle_id__in=cycle_ids)
    if class_ids:
        enrollments = enrollments.filter(academic_class_id__in=class_ids)

    wants_students = not role_tokens or bool(STUDENT_ROLE_TOKENS.intersection(set(role_tokens)))
    if wants_students and any([branch_ids, programme_ids, cycle_ids, class_ids]):
        recipient_ids.update(enrollments.values_list("student_id", flat=True))

    return users.filter(id__in=recipient_ids).distinct()
