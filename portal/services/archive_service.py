from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, QuerySet
from django.utils.dateparse import parse_datetime
from django.utils import timezone

from academics.models import AcademicClass, AcademicEnrollment, AcademicYear, ECGrade
from inscriptions.models import Inscription
from payments.models import Payment
from portal.models import ArchiveBatch
from students.models import Student


def archive_batches_for_branch(*, branch) -> QuerySet[ArchiveBatch]:
    queryset = ArchiveBatch.objects.select_related(
        "branch",
        "academic_year",
        "academic_class",
        "created_by",
        "restored_by",
    )
    if branch:
        queryset = queryset.filter(branch=branch)
    return queryset.order_by("-created_at", "-id")


def archive_candidates_for_branch(*, branch):
    years = AcademicYear.objects.filter(academic_classes__branch=branch).distinct().order_by("-start_date", "-id")
    classes = (
        AcademicClass.objects.select_related("programme", "academic_year", "branch")
        .filter(branch=branch, is_archived=False)
        .annotate(active_enrollments_count=Count("enrollments", distinct=True))
        .order_by("-academic_year__start_date", "programme__title", "level")
    )
    return {"academic_years": list(years), "classes": list(classes)}


def preview_archive(*, branch, academic_year_id=None, class_id=None):
    classes = _resolve_classes(branch=branch, academic_year_id=academic_year_id, class_id=class_id)
    return _build_snapshot(classes)


@transaction.atomic
def archive_class(*, branch, class_id, actor, reason):
    academic_class = AcademicClass.objects.select_for_update().filter(pk=class_id, branch=branch).first()
    if academic_class is None:
        raise ValidationError("Classe introuvable.")
    return _archive_classes(
        branch=branch,
        academic_year=academic_class.academic_year,
        classes=[academic_class],
        actor=actor,
        reason=reason,
        archive_type=ArchiveBatch.TYPE_CLASS,
        academic_class=academic_class,
    )


@transaction.atomic
def archive_year(*, branch, academic_year_id, actor, reason):
    academic_year = AcademicYear.objects.filter(pk=academic_year_id).first()
    if academic_year is None:
        raise ValidationError("Annee academique introuvable.")
    classes = list(
        AcademicClass.objects.select_for_update()
        .filter(branch=branch, academic_year=academic_year, is_archived=False)
        .order_by("programme__title", "level", "id")
    )
    return _archive_classes(
        branch=branch,
        academic_year=academic_year,
        classes=classes,
        actor=actor,
        reason=reason,
        archive_type=ArchiveBatch.TYPE_YEAR,
        academic_class=None,
    )


@transaction.atomic
def restore_archive_batch(*, branch, batch_id, actor):
    batch = ArchiveBatch.objects.select_for_update().filter(pk=batch_id, branch=branch).first()
    if batch is None:
        raise ValidationError("Archive introuvable.")
    if batch.status == ArchiveBatch.STATUS_RESTORED:
        raise ValidationError("Cette archive est deja restauree.")

    class_ids = batch.snapshot.get("class_ids", [])
    enrollment_ids = batch.snapshot.get("enrollment_ids", [])
    inscription_ids = batch.snapshot.get("inscription_ids", [])
    student_ids = batch.snapshot.get("student_ids", [])
    state = batch.snapshot.get("state") or {}

    _restore_academic_classes(
        class_ids=class_ids,
        branch=branch,
        state_map=state.get("classes") or {},
    )
    _restore_academic_enrollments(
        enrollment_ids=enrollment_ids,
        branch=branch,
        state_map=state.get("enrollments") or {},
    )
    _restore_inscriptions(
        inscription_ids=inscription_ids,
        branch=branch,
        state_map=state.get("inscriptions") or {},
    )
    _restore_students(
        student_ids=student_ids,
        branch=branch,
        state_map=state.get("students") or {},
    )

    batch.status = ArchiveBatch.STATUS_RESTORED
    batch.restored_by = actor
    batch.restored_at = timezone.now()
    batch.save(update_fields=["status", "restored_by", "restored_at"])
    return batch


def archive_detail(*, branch, batch_id):
    batch = archive_batches_for_branch(branch=branch).filter(pk=batch_id).first()
    if batch is None:
        raise ValidationError("Archive introuvable.")
    class_ids = batch.snapshot.get("class_ids", [])
    enrollment_ids = batch.snapshot.get("enrollment_ids", [])
    inscription_ids = batch.snapshot.get("inscription_ids", [])
    student_ids = batch.snapshot.get("student_ids", [])
    return {
        "batch": batch,
        "classes": AcademicClass.objects.select_related("programme", "academic_year").filter(pk__in=class_ids),
        "enrollments": AcademicEnrollment.objects.select_related(
            "student__student_profile__inscription__candidature",
            "academic_class",
            "programme",
        ).filter(pk__in=enrollment_ids),
        "inscriptions": Inscription.objects.select_related("candidature", "academic_class").filter(pk__in=inscription_ids),
        "students": Student.objects.select_related("user", "inscription__candidature").filter(pk__in=student_ids),
        "payments": Payment.objects.select_related("inscription", "agent").filter(inscription_id__in=inscription_ids),
        "grades": ECGrade.objects.select_related("enrollment", "ec", "ec__ue").filter(enrollment_id__in=enrollment_ids),
    }


def _resolve_classes(*, branch, academic_year_id=None, class_id=None):
    queryset = AcademicClass.objects.filter(branch=branch, is_archived=False)
    if class_id:
        queryset = queryset.filter(pk=class_id)
    elif academic_year_id:
        queryset = queryset.filter(academic_year_id=academic_year_id)
    else:
        return []
    return list(queryset.select_related("programme", "academic_year"))


def _archive_classes(*, branch, academic_year, classes, actor, reason, archive_type, academic_class):
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("La raison d'archivage est obligatoire.")
    if not classes:
        raise ValidationError("Aucune classe active a archiver.")

    snapshot = _build_snapshot(classes)
    now = timezone.now()
    class_ids = snapshot["class_ids"]
    enrollment_ids = snapshot["enrollment_ids"]
    inscription_ids = snapshot["inscription_ids"]
    student_ids = snapshot["student_ids"]

    AcademicClass.objects.filter(pk__in=class_ids, branch=branch).update(
        is_active=False,
        is_archived=True,
        archived_at=now,
    )
    AcademicEnrollment.objects.filter(pk__in=enrollment_ids, branch=branch).update(
        is_active=False,
        is_archived=True,
        archived_at=now,
    )
    Inscription.objects.filter(pk__in=inscription_ids, candidature__branch=branch).update(
        is_archived=True,
        archived_at=now,
    )
    Student.objects.filter(pk__in=student_ids, inscription__candidature__branch=branch).update(is_active=False)

    return ArchiveBatch.objects.create(
        archive_type=archive_type,
        branch=branch,
        academic_year=academic_year,
        academic_class=academic_class,
        reason=reason,
        snapshot=snapshot,
        classes_count=snapshot["classes_count"],
        enrollments_count=snapshot["enrollments_count"],
        inscriptions_count=snapshot["inscriptions_count"],
        students_count=snapshot["students_count"],
        grades_count=snapshot["grades_count"],
        payments_count=snapshot["payments_count"],
        created_by=actor,
    )


def _build_snapshot(classes):
    class_ids = [item.id for item in classes]
    enrollments = list(AcademicEnrollment.objects.filter(academic_class_id__in=class_ids))
    enrollment_ids = [item.id for item in enrollments]
    inscription_ids = list({item.inscription_id for item in enrollments if item.inscription_id})
    student_user_ids = [item.student_id for item in enrollments if item.student_id]
    students = list(Student.objects.filter(user_id__in=student_user_ids))
    student_ids = [item.id for item in students]
    inscriptions = list(Inscription.objects.filter(pk__in=inscription_ids))
    return {
        "class_ids": class_ids,
        "enrollment_ids": enrollment_ids,
        "inscription_ids": inscription_ids,
        "student_ids": student_ids,
        "class_labels": {str(item.id): item.display_name for item in classes},
        "state": {
            "classes": {
                str(item.id): {
                    "is_active": item.is_active,
                    "is_archived": item.is_archived,
                    "archived_at": item.archived_at.isoformat() if item.archived_at else None,
                }
                for item in classes
            },
            "enrollments": {
                str(item.id): {
                    "is_active": item.is_active,
                    "is_archived": item.is_archived,
                    "archived_at": item.archived_at.isoformat() if item.archived_at else None,
                }
                for item in enrollments
            },
            "inscriptions": {
                str(item.id): {
                    "is_archived": item.is_archived,
                    "archived_at": item.archived_at.isoformat() if item.archived_at else None,
                }
                for item in inscriptions
            },
            "students": {
                str(item.id): {
                    "is_active": item.is_active,
                }
                for item in students
            },
        },
        "classes_count": len(class_ids),
        "enrollments_count": len(enrollment_ids),
        "inscriptions_count": len(inscription_ids),
        "students_count": len(student_ids),
        "grades_count": ECGrade.objects.filter(enrollment_id__in=enrollment_ids).count(),
        "payments_count": Payment.objects.filter(inscription_id__in=inscription_ids).count(),
    }


def _ids_for_state(ids, state_map, field_name, expected, default):
    resolved_ids = []
    for object_id in ids:
        item_state = state_map.get(str(object_id), {})
        if item_state.get(field_name, default) is expected:
            resolved_ids.append(object_id)
    return resolved_ids


def _snapshot_datetime(value):
    return parse_datetime(value) if value else None


def _restore_academic_classes(*, class_ids, branch, state_map):
    for academic_class in AcademicClass.objects.filter(pk__in=class_ids, branch=branch):
        item_state = state_map.get(str(academic_class.pk), {})
        academic_class.is_active = item_state.get("is_active", True)
        academic_class.is_archived = item_state.get("is_archived", False)
        academic_class.archived_at = _snapshot_datetime(item_state.get("archived_at"))
        academic_class.save(update_fields=["is_active", "is_archived", "archived_at"])


def _restore_academic_enrollments(*, enrollment_ids, branch, state_map):
    for enrollment in AcademicEnrollment.objects.filter(pk__in=enrollment_ids, branch=branch):
        item_state = state_map.get(str(enrollment.pk), {})
        enrollment.is_active = item_state.get("is_active", True)
        enrollment.is_archived = item_state.get("is_archived", False)
        enrollment.archived_at = _snapshot_datetime(item_state.get("archived_at"))
        enrollment.save(update_fields=["is_active", "is_archived", "archived_at"])


def _restore_inscriptions(*, inscription_ids, branch, state_map):
    for inscription in Inscription.objects.filter(pk__in=inscription_ids, candidature__branch=branch):
        item_state = state_map.get(str(inscription.pk), {})
        inscription.is_archived = item_state.get("is_archived", False)
        inscription.archived_at = _snapshot_datetime(item_state.get("archived_at"))
        inscription.save(update_fields=["is_archived", "archived_at"])


def _restore_students(*, student_ids, branch, state_map):
    queryset = Student.objects.filter(pk__in=student_ids, inscription__candidature__branch=branch)
    active_ids = _ids_for_state(student_ids, state_map, "is_active", True, True)
    inactive_ids = [object_id for object_id in student_ids if object_id not in set(active_ids)]
    queryset.filter(pk__in=active_ids).update(is_active=True)
    queryset.filter(pk__in=inactive_ids).update(is_active=False)
