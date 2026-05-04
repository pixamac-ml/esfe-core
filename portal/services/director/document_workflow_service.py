from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from accounts.dashboards.helpers import get_user_branch
from portal.models import TeacherDocument


def build_director_document_context(*, branch, teacher_id=None):
    User = get_user_model()
    teacher_rows = list(
        User.objects.select_related("profile")
        .filter(is_active=True, profile__position="teacher", profile__branch=branch)
        .order_by("first_name", "last_name", "username")
    ) if branch else []

    selected_teacher = None
    if teacher_id:
        selected_teacher = next((teacher for teacher in teacher_rows if teacher.id == teacher_id), None)
    if selected_teacher is None and teacher_rows:
        selected_teacher = teacher_rows[0]

    teacher_documents = []
    if selected_teacher is not None:
        teacher_documents = list(
            TeacherDocument.objects.select_related("teacher", "uploaded_by", "verified_by")
            .filter(branch=branch, teacher=selected_teacher)
            .order_by("-created_at", "-id")
        )

    return {
        "document_teacher_rows": teacher_rows,
        "selected_document_teacher": selected_teacher,
        "teacher_documents": teacher_documents,
        "teacher_document_type_choices": TeacherDocument.DOCUMENT_CHOICES,
    }


def upload_teacher_document(*, user, teacher_id, document_type, file, note=""):
    branch = get_user_branch(user)
    if branch is None:
        raise ValidationError("Aucune annexe n'est rattachee a ce compte directeur.")
    if not file:
        raise ValidationError("Aucun fichier n'a ete fourni.")

    User = get_user_model()
    teacher = User.objects.select_related("profile").filter(
        id=teacher_id,
        profile__position="teacher",
        profile__branch=branch,
    ).first()
    if teacher is None:
        raise ValidationError("Enseignant introuvable pour cette annexe.")

    if document_type not in dict(TeacherDocument.DOCUMENT_CHOICES):
        raise ValidationError("Type de document invalide.")

    return TeacherDocument.objects.create(
        branch=branch,
        teacher=teacher,
        document_type=document_type,
        file=file,
        note=(note or "").strip(),
        uploaded_by=user,
    )


def review_teacher_document(*, user, document_id, verify=True):
    branch = get_user_branch(user)
    if branch is None:
        raise ValidationError("Aucune annexe n'est rattachee a ce compte directeur.")

    document = TeacherDocument.objects.select_related("teacher", "teacher__profile").filter(
        id=document_id,
        branch=branch,
        teacher__profile__branch=branch,
    ).first()
    if document is None:
        raise ValidationError("Document enseignant introuvable.")

    document.is_verified = bool(verify)
    document.verified_by = user if verify else None
    document.save(update_fields=["is_verified", "verified_by", "updated_at"])
    return document
