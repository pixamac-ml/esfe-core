from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from academics.models import AcademicClass, AcademicEnrollment, AcademicScheduleEvent, ECGrade, Semester
from academics.services.schedule_service import get_director_schedule_overview
from inscriptions.models import Inscription
from students.models import Student
from portal.services.it_support_service import (
    build_diagnostic_payload,
    get_recent_support_logs,
    get_scoped_staff_queryset,
    search_support_entities,
)


def _build_alert(level, alert_type, message):
    return {
        "level": level,
        "type": alert_type,
        "message": message,
    }


def build_it_dashboard_context(request, *, branch, base_context_builder):
    user_model = get_user_model()
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=7)
    overview = get_director_schedule_overview(branch, week_start) if branch else {
        "stats": {},
        "quality": {"score": 0, "status": "critical", "warnings": []},
        "alerts": [],
        "timetable": [],
    }

    staff_users = get_scoped_staff_queryset(branch=branch)
    students_users = user_model.objects.filter(student_profile__isnull=False)
    active_classes = AcademicClass.objects.select_related("branch", "programme", "academic_year").filter(is_active=True)
    enrollments = AcademicEnrollment.objects.select_related(
        "student__student_profile__inscription__candidature",
        "academic_class",
        "branch",
        "academic_year",
    ).filter(is_active=True)
    inscriptions = Inscription.objects.select_related("candidature__branch", "candidature__programme")
    students = Student.objects.select_related("user", "inscription__candidature__branch", "inscription__candidature__programme")
    semesters = Semester.objects.select_related("academic_class", "academic_class__branch")
    grade_entries = ECGrade.objects.select_related("enrollment__branch", "ec__ue__semester")
    recent_events = AcademicScheduleEvent.objects.select_related("branch", "academic_class", "teacher").filter(
        start_datetime__date__gte=week_start,
        start_datetime__date__lt=week_end,
    )

    if branch:
        students_users = students_users.filter(student_profile__inscription__candidature__branch=branch)
        active_classes = active_classes.filter(branch=branch)
        enrollments = enrollments.filter(branch=branch)
        inscriptions = inscriptions.filter(candidature__branch=branch)
        students = students.filter(inscription__candidature__branch=branch)
        semesters = semesters.filter(academic_class__branch=branch)
        grade_entries = grade_entries.filter(enrollment__branch=branch)
        recent_events = recent_events.filter(branch=branch)

    students_without_class = students.filter(
        user__academic_enrollments__isnull=True,
    ).distinct()
    active_students_without_active_enrollment = students.filter(
        is_active=True,
    ).exclude(
        user__academic_enrollments__is_active=True,
    ).distinct()
    inscriptions_without_assignment = inscriptions.filter(
        status__in=[Inscription.STATUS_PARTIAL, Inscription.STATUS_ACTIVE],
        academic_enrollment__isnull=True,
    )
    staff_missing_position = staff_users.filter(Q(profile__position="") | Q(profile__position__isnull=True))
    staff_missing_branch = staff_users.filter(profile__branch__isnull=True)
    staff_missing_employee_code = staff_users.filter(Q(profile__employee_code="") | Q(profile__employee_code__isnull=True))
    inactive_accounts = staff_users.filter(is_active=False).count() + students_users.filter(is_active=False).count()
    pending_semesters = semesters.exclude(status__in=[Semester.STATUS_FINALIZED, Semester.STATUS_PUBLISHED])
    enrollments_without_grades = enrollments.filter(ec_grades__isnull=True).distinct()

    quality = overview.get("quality", {"score": 0, "status": "critical", "warnings": []})
    alerts = [
        *_build_dashboard_alerts(
            inscriptions_without_assignment_count=inscriptions_without_assignment.count(),
            active_students_without_active_enrollment_count=active_students_without_active_enrollment.count(),
            staff_missing_position_count=staff_missing_position.count(),
            inactive_accounts_count=inactive_accounts,
            quality=quality,
        ),
    ]
    search_query = (request.GET.get("q") or "").strip()
    selected_kind = (request.GET.get("kind") or "").strip()
    selected_id_raw = (request.GET.get("id") or "").strip()
    selected_id = int(selected_id_raw) if selected_id_raw.isdigit() else None
    support_feedback = request.session.pop("it_support_feedback", None)
    search_results = search_support_entities(branch=branch, query=search_query)
    diagnostic_payload = build_diagnostic_payload(branch=branch, kind=selected_kind, object_id=selected_id) if selected_kind and selected_id else None

    return {
        **base_context_builder(
            request,
            page_title="Dashboard Informaticien",
            module_cards=[
                "Gestion des notes",
                "Diagnostic etudiants",
                "Acces et comptes",
                "Sante du portail",
            ],
        ),
        "dashboard_kind": "Support technique",
        "branch": branch,
        "week_start": week_start,
        "week_end": week_end,
        "total_users": staff_users.count() + students_users.count(),
        "total_active_staff": staff_users.filter(is_active=True).count(),
        "total_students": students.count(),
        "quality": quality,
        "alerts": alerts[:8],
        "recent_events": list(recent_events.order_by("-updated_at", "-created_at")[:8]),
        "classes": list(active_classes.order_by("branch__name", "level")[:6]),
        "sidebar_links": [
            {"label": "Vue generale", "href": "#overview"},
            {"label": "Notes", "href": "#grades"},
            {"label": "Diagnostics", "href": "#diagnostics"},
            {"label": "Sante", "href": "#health"},
            {"label": "Activite", "href": "#activity"},
        ],
        "support_actions": [
            {
                "title": "Gestion des notes",
                "detail": "Acceder a la saisie, aux releves et aux tableaux complets existants.",
                "href": reverse("accounts_portal:admin_grade_dashboard"),
            },
            {
                "title": "Verifier les affectations",
                "detail": f"{inscriptions_without_assignment.count()} inscription(s) active(s) sans affectation academique.",
            },
            {
                "title": "Controler les comptes staff",
                "detail": f"{staff_missing_position.count()} profil(s) sans position et {staff_missing_employee_code.count()} sans code employe.",
            },
            {
                "title": "Suivre la sante portail",
                "detail": f"Score actuel {quality.get('score', 0)} avec {len(quality.get('warnings', []))} avertissement(s).",
            },
        ],
        "grades_dashboard_url": reverse("accounts_portal:admin_grade_dashboard"),
        "grade_metrics": {
            "active_classes": active_classes.count(),
            "pending_semesters": pending_semesters.count(),
            "enrollments_without_grades": enrollments_without_grades.count(),
            "grade_entries": grade_entries.count(),
        },
        "access_metrics": {
            "inactive_accounts": inactive_accounts,
            "staff_missing_position": staff_missing_position.count(),
            "staff_missing_branch": staff_missing_branch.count(),
            "staff_missing_employee_code": staff_missing_employee_code.count(),
        },
        "diagnostic_metrics": {
            "inscriptions_without_assignment": inscriptions_without_assignment.count(),
            "students_without_class": students_without_class.count(),
            "active_students_without_active_enrollment": active_students_without_active_enrollment.count(),
        },
        "diagnostic_rows": _build_diagnostic_rows(
            inscriptions_without_assignment=inscriptions_without_assignment,
            active_students_without_active_enrollment=active_students_without_active_enrollment,
        ),
        "support_feedback": support_feedback,
        "support_search": search_results,
        "diagnostic_payload": diagnostic_payload,
        "recent_support_logs": get_recent_support_logs(branch=branch, limit=8),
    }


def _build_dashboard_alerts(
    *,
    inscriptions_without_assignment_count,
    active_students_without_active_enrollment_count,
    staff_missing_position_count,
    inactive_accounts_count,
    quality,
):
    alerts = []
    if inscriptions_without_assignment_count:
        alerts.append(
            _build_alert(
                "critical",
                "affectation",
                f"{inscriptions_without_assignment_count} inscription(s) active(s) n'ont pas encore d'affectation academique.",
            )
        )
    if active_students_without_active_enrollment_count:
        alerts.append(
            _build_alert(
                "warning",
                "diagnostic_etudiant",
                f"{active_students_without_active_enrollment_count} etudiant(s) actif(s) n'ont aucune inscription academique active.",
            )
        )
    if staff_missing_position_count:
        alerts.append(
            _build_alert(
                "warning",
                "acces_staff",
                f"{staff_missing_position_count} compte(s) staff n'ont pas de position metier renseignee.",
            )
        )
    if inactive_accounts_count:
        alerts.append(
            _build_alert(
                "info",
                "comptes_inactifs",
                f"{inactive_accounts_count} compte(s) utilisateur(s) sont actuellement inactifs.",
            )
        )
    for warning in quality.get("warnings", []):
        alerts.append(_build_alert("warning", "sante_portail", warning))
    if not alerts:
        alerts.append(_build_alert("info", "support", "Aucune anomalie technique prioritaire detectee."))
    return alerts


def _build_diagnostic_rows(*, inscriptions_without_assignment, active_students_without_active_enrollment):
    rows = []
    for inscription in inscriptions_without_assignment.order_by("-updated_at")[:4]:
        candidature = inscription.candidature
        rows.append(
            {
                "label": f"{candidature.first_name} {candidature.last_name}",
                "issue": "Inscription sans affectation academique",
                "context": f"{candidature.programme.title} - {candidature.branch.name}",
            }
        )
    for student in active_students_without_active_enrollment.order_by("-created_at")[:4]:
        rows.append(
            {
                "label": student.full_name,
                "issue": "Etudiant actif sans inscription academique active",
                "context": f"{student.matricule} - {student.inscription.candidature.branch.name}",
            }
        )
    return rows[:6]
