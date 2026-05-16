from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, QuerySet
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

    AcademicClass.objects.filter(pk__in=class_ids, branch=branch).update(
        is_archived=False,
        archived_at=None,
        is_active=True,
    )
    AcademicEnrollment.objects.filter(pk__in=enrollment_ids, branch=branch).update(
        is_archived=False,
        archived_at=None,
        is_active=True,
    )
    Inscription.objects.filter(pk__in=inscription_ids, candidature__branch=branch).update(
        is_archived=False,
        archived_at=None,
    )
    Student.objects.filter(pk__in=student_ids, inscription__candidature__branch=branch).update(is_active=True)

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
    return {
        "batch": batch,
        "classes": AcademicClass.objects.select_related("programme", "academic_year").filter(pk__in=class_ids),
        "enrollments": AcademicEnrollment.objects.select_related(
            "student__student_profile__inscription__candidature",
            "academic_class",
            "programme",
        ).filter(pk__in=enrollment_ids),
        "inscriptions": Inscription.objects.select_related("candidature", "academic_class").filter(pk__in=inscription_ids),
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
    return {
        "class_ids": class_ids,
        "enrollment_ids": enrollment_ids,
        "inscription_ids": inscription_ids,
        "student_ids": student_ids,
        "classes_count": len(class_ids),
        "enrollments_count": len(enrollment_ids),
        "inscriptions_count": len(inscription_ids),
        "students_count": len(student_ids),
        "grades_count": ECGrade.objects.filter(enrollment_id__in=enrollment_ids).count(),
        "payments_count": Payment.objects.filter(inscription_id__in=inscription_ids).count(),
    }
