from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from academics.models import AcademicClass, AcademicEnrollment, AcademicYear, EC, Semester, UE
from formations.models import Programme
from inscriptions.models import Inscription
from students.models import Student


def _group_programmes_by_cycle():
    grouped = {}
    programmes = Programme.objects.select_related("cycle").order_by(
        "cycle__min_duration_years",
        "cycle__name",
        "title",
        "id",
    )[:300]
    for programme in programmes:
        cycle_name = programme.cycle.name if programme.cycle_id else "Sans cycle"
        grouped.setdefault(cycle_name, []).append(programme)
    return [{"cycle": cycle, "programmes": items} for cycle, items in grouped.items()]


def _academic_class_name(*, programme, branch, academic_year, level):
    return f"{level} {programme.title} - {branch.name} ({academic_year.name})"[:100]


def build_academic_structure_context(*, branch, selected_class_id=None, student_query="", section="classes"):
    section = (section or "classes").strip().lower()
    if section not in {"classes", "maquettes", "affectations"}:
        section = "classes"

    classes = list(
        AcademicClass.objects.select_related("programme", "academic_year", "branch")
        .filter(branch=branch)
        .filter(is_archived=False)
        .order_by("-is_active", "programme__title", "level", "id")
    )
    selected_class = next((item for item in classes if str(item.id) == str(selected_class_id)), None)
    if selected_class is None and classes:
        selected_class = classes[0]

    semesters = []
    ue_rows = []
    ec_count = 0
    if selected_class is not None:
        semesters = list(selected_class.semesters.prefetch_related("ues__ecs").order_by("number"))
        for semester in semesters:
            semester_ues = list(semester.ues.all().order_by("code", "id"))
            ue_rows.append(
                {
                    "semester": semester,
                    "ues": semester_ues,
                }
            )
            ec_count += sum(ue.ecs.count() for ue in semester_ues)

    unassigned_students = (
        Student.objects.select_related("user", "inscription__candidature", "inscription__candidature__programme")
        .filter(
            inscription__candidature__branch=branch,
            inscription__status__in=[Inscription.STATUS_PARTIAL, Inscription.STATUS_ACTIVE],
            inscription__is_archived=False,
            user__academic_enrollments__isnull=True,
        )
        .order_by("inscription__candidature__last_name", "inscription__candidature__first_name", "matricule")
    )
    if student_query:
        unassigned_students = unassigned_students.filter(
            Q(inscription__candidature__last_name__icontains=student_query)
            | Q(inscription__candidature__first_name__icontains=student_query)
            | Q(matricule__icontains=student_query)
        )

    return {
        "branch": branch,
        "classes": classes,
        "selected_class": selected_class,
        "section": section,
        "semesters": semesters,
        "ue_rows": ue_rows,
        "programmes_by_cycle": _group_programmes_by_cycle(),
        "academic_years": list(AcademicYear.objects.order_by("-start_date")[:20]),
        "unassigned_students": list(unassigned_students[:80]),
        "student_query": student_query,
        "metrics": {
            "classes": len(classes),
            "ues": sum(semester.ues.count() for semester in semesters) if selected_class else 0,
            "ecs": ec_count,
            "students_without_class": unassigned_students.count(),
        },
    }


@transaction.atomic
def save_academic_class(*, branch, class_id=None, programme_id=None, academic_year_id=None, level="", threshold="", actor=None):
    level = (level or "").strip().upper()
    if not programme_id:
        raise ValidationError("Programme obligatoire.")
    if not academic_year_id:
        raise ValidationError("Annee academique obligatoire.")
    if not level:
        raise ValidationError("Niveau de classe obligatoire.")

    programme = Programme.objects.filter(pk=programme_id).first()
    academic_year = AcademicYear.objects.filter(pk=academic_year_id).first()
    if programme is None or academic_year is None:
        raise ValidationError("Programme ou annee academique invalide.")

    validation_threshold = None
    if str(threshold or "").strip():
        try:
            validation_threshold = Decimal(str(threshold).replace(",", "."))
        except (InvalidOperation, TypeError):
            raise ValidationError("Seuil de validation invalide.")

    duplicate_class = AcademicClass.objects.select_for_update().filter(
        programme=programme,
        branch=branch,
        academic_year=academic_year,
        level=level,
    )

    if class_id:
        duplicate_class = duplicate_class.exclude(pk=class_id).first()
        if duplicate_class is not None:
            raise ValidationError("Une classe existe deja pour ce programme, cette annee et ce niveau.")
        academic_class = AcademicClass.objects.select_for_update().filter(pk=class_id, branch=branch).first()
    else:
        academic_class = duplicate_class.first() or AcademicClass(branch=branch)

    if academic_class is None:
        raise ValidationError("Classe introuvable.")

    academic_class.programme = programme
    academic_class.academic_year = academic_year
    academic_class.level = level
    academic_class.study_level = _infer_study_level(level)
    academic_class.validation_threshold = validation_threshold
    academic_class.name = _academic_class_name(
        programme=programme,
        branch=branch,
        academic_year=academic_year,
        level=level,
    )
    academic_class.is_active = True
    academic_class.is_archived = False
    academic_class.archived_at = None
    academic_class.save()

    for number in (1, 2):
        Semester.objects.get_or_create(academic_class=academic_class, number=number)
    return academic_class


def archive_academic_class(*, branch, class_id):
    academic_class = AcademicClass.objects.filter(pk=class_id, branch=branch).first()
    if academic_class is None:
        raise ValidationError("Classe introuvable.")
    academic_class.is_active = False
    academic_class.is_archived = True
    academic_class.archived_at = timezone.now()
    academic_class.save(update_fields=["is_active", "is_archived", "archived_at"])
    return academic_class


def save_ue(*, branch, ue_id=None, semester_id=None, code="", title=""):
    code = (code or "").strip().upper()
    title = (title or "").strip()
    if not semester_id:
        raise ValidationError("Semestre obligatoire.")
    if not code or not title:
        raise ValidationError("Code UE et intitule obligatoires.")

    semester = Semester.objects.select_related("academic_class").filter(
        pk=semester_id,
        academic_class__branch=branch,
    ).first()
    if semester is None:
        raise ValidationError("Semestre invalide.")

    ue = (
        UE.objects.filter(pk=ue_id, semester__academic_class__branch=branch).first()
        if ue_id
        else UE(semester=semester)
    )
    if ue is None:
        raise ValidationError("UE introuvable.")
    ue.semester = semester
    ue.code = code
    ue.title = title
    ue.save()
    return ue


def save_ec(*, branch, ec_id=None, ue_id=None, title="", coefficient="", credit_required=""):
    title = (title or "").strip()
    if not ue_id:
        raise ValidationError("UE obligatoire.")
    if not title:
        raise ValidationError("Intitule EC obligatoire.")
    try:
        coefficient_value = Decimal(str(coefficient).replace(",", "."))
        credit_value = Decimal(str(credit_required).replace(",", "."))
    except (InvalidOperation, TypeError):
        raise ValidationError("Coefficient ou credit invalide.")

    ue = UE.objects.select_related("semester", "semester__academic_class").filter(
        pk=ue_id,
        semester__academic_class__branch=branch,
    ).first()
    if ue is None:
        raise ValidationError("UE invalide.")

    ec = (
        EC.objects.filter(pk=ec_id, ue__semester__academic_class__branch=branch).first()
        if ec_id
        else EC(ue=ue)
    )
    if ec is None:
        raise ValidationError("EC introuvable.")
    ec.ue = ue
    ec.title = title
    ec.coefficient = coefficient_value
    ec.credit_required = credit_value
    ec.save()
    return ec


def delete_ec(*, branch, ec_id):
    ec = EC.objects.select_related("ue", "ue__semester", "ue__semester__academic_class").filter(
        pk=ec_id,
        ue__semester__academic_class__branch=branch,
    ).first()
    if ec is None:
        raise ValidationError("EC introuvable.")
    if ec.grades.exists() or ec.schedule_events.exists() or ec.weekly_schedule_slots.exists() or ec.lesson_logs.exists() or ec.chapters.exists():
        raise ValidationError("Suppression impossible: cet EC est deja utilise dans le systeme.")
    ec.delete()


@transaction.atomic
def assign_student_to_class(*, branch, student_id, class_id):
    student = Student.objects.select_related("user", "inscription__candidature").filter(
        pk=student_id,
        inscription__candidature__branch=branch,
    ).first()
    academic_class = AcademicClass.objects.select_related("programme", "academic_year", "branch").filter(
        pk=class_id,
        branch=branch,
        is_active=True,
    ).first()
    if student is None or academic_class is None:
        raise ValidationError("Etudiant ou classe invalide.")
    if student.inscription.status not in {Inscription.STATUS_PARTIAL, Inscription.STATUS_ACTIVE}:
        raise ValidationError("L'etudiant doit avoir une inscription administrative active ou partielle.")
    if student.inscription.candidature.programme_id != academic_class.programme_id:
        raise ValidationError("La classe ne correspond pas au programme de l'etudiant.")

    enrollment, _created = AcademicEnrollment.objects.update_or_create(
        inscription=student.inscription,
        defaults={
            "student": student.user,
            "programme": academic_class.programme,
            "branch": branch,
            "academic_year": academic_class.academic_year,
            "academic_class": academic_class,
            "is_active": True,
        },
    )
    student.inscription.academic_class = academic_class
    student.inscription.academic_level = academic_class.level
    student.inscription.save(update_fields=["academic_class", "academic_level", "updated_at"])
    return enrollment


def _infer_study_level(level):
    level = (level or "").upper()
    if level.startswith("M"):
        return "MASTER"
    if level.startswith("L"):
        return "LICENCE"
    if level.startswith("B"):
        return "BAC"
    return "LICENCE"
