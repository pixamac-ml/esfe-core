from decimal import Decimal
from types import SimpleNamespace

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from academic_cycle.models import StudentYearDecision
from academics.models import AcademicBulletin, AcademicDebt, AcademicDiplomaAward, AcademicEnrollment, Semester
from academics.services.annual_deliberation import get_annual_semesters, get_final_annual_decision
from academics.services.reporting import format_decimal
from academics.services.semester import compute_semester_result
from academics.services.workflow import get_semester_permissions
from academics.services.year import DECISION_VALIDE


def _mention(average):
    if average is None:
        return ""
    average = Decimal(str(average))
    if average >= Decimal("16"):
        return "Tres bien"
    if average >= Decimal("14"):
        return "Bien"
    if average >= Decimal("12"):
        return "Assez bien"
    if average >= Decimal("10"):
        return "Passable"
    return "Insuffisant"


def _student_for_enrollment(enrollment):
    return enrollment.student.student_profile


def _reference(prefix, enrollment, suffix=""):
    parts = [
        prefix,
        str(enrollment.academic_year.name).replace("-", ""),
        str(enrollment.branch.code).upper(),
        str(enrollment.pk).zfill(5),
    ]
    if suffix:
        parts.append(str(suffix).upper())
    return "-".join(parts)


def _official_session_label(grade):
    """Expose la session qui a effectivement fourni la note finale figée."""
    if grade is None or grade.retake_score is None:
        return "Normale"
    if grade.normal_score is None or grade.retake_score > grade.normal_score:
        return "Rattrapage"
    return "Normale"


def _serialize_semester_result(result, enrollment):
    grade_by_ec_id = {
        grade.ec_id: grade
        for grade in enrollment.ec_grades.all()
    }
    return {
        "semester_number": getattr(result.get("semester"), "number", None),
        "average": str(result.get("average")) if result.get("average") is not None else None,
        "percentage": str(result.get("percentage") or "0"),
        "credit_required": str(result.get("credit_required") or "0"),
        "credit_obtained": str(result.get("credit_obtained") or "0"),
        "total_coefficients": str(result.get("total_coefficients") or "0"),
        "is_validated": bool(result.get("is_validated")),
        "is_complete": bool(result.get("is_complete")),
        "status": result.get("status"),
        "missing_grades": result.get("missing_grades", 0),
        "ues": [
            {
                "code": ue_result["ue"].code,
                "title": ue_result["ue"].title,
                "average": str(ue_result.get("average")) if ue_result.get("average") is not None else None,
                "coefficient": str(ue_result.get("total_coefficients") or "0"),
                "total_note_coefficients": str(ue_result.get("total_note_coefficients") or "0"),
                "credit_required": str(ue_result.get("credit_required") or "0"),
                "credit_obtained": str(ue_result.get("credit_obtained") or "0"),
                "status": ue_result.get("status"),
                "ecs": [
                    {
                        "title": row["ec"].title,
                        "coefficient": str(row["ec"].coefficient or "0"),
                        "note": str(row.get("note")) if row.get("note") is not None else None,
                        "note_coefficient": str(row.get("note_coefficient") or "0"),
                        "credit_required": str(row.get("credit_required") or "0"),
                        "credit_obtained": str(row.get("credit_obtained") or "0"),
                        "is_validated": bool(row.get("is_validated")),
                        "session": _official_session_label(grade_by_ec_id.get(row["ec"].id)),
                    }
                    for row in ue_result.get("rows", [])
                ],
            }
            for ue_result in result.get("ue_results", [])
        ],
    }


def _identity_snapshot(enrollment):
    student = _student_for_enrollment(enrollment)
    candidature = getattr(getattr(student, "inscription", None), "candidature", None)
    programme = enrollment.programme
    birth_date = getattr(candidature, "birth_date", None)
    birth_place = (getattr(candidature, "birth_place", "") or "").strip()
    birth_parts = []
    if birth_date:
        birth_parts.append(birth_date.strftime("%d/%m/%Y"))
    if birth_place:
        birth_parts.append(birth_place)
    return {
        "student": {
            "matricule": student.matricule,
            "full_name": getattr(student, "full_name", str(student)),
            "last_name": (getattr(candidature, "last_name", "") or "").strip(),
            "first_name": (getattr(candidature, "first_name", "") or "").strip(),
            "birth_info": " a ".join(birth_parts) if birth_parts else "Non renseigne",
        },
        "academic": {
            "academic_year": str(enrollment.academic_year),
            "academic_class": enrollment.academic_class.display_name,
            "programme_name": getattr(programme, "title", "") or "",
            "department_name": getattr(getattr(programme, "filiere", None), "name", "") or "",
            "domain_name": getattr(getattr(programme, "cycle", None), "name", "") or "",
            "branch_name": getattr(enrollment.branch, "name", "") or "",
        },
    }


def _build_semester_bulletin_snapshot(enrollment, result):
    snapshot = {
        "version": 2,
        **_identity_snapshot(enrollment),
        "result": _serialize_semester_result(result, enrollment),
    }
    snapshot["document"] = {
        "decision": "Valide" if result.get("is_validated") else "Non valide",
        "mention": _mention(result.get("average")),
    }
    return snapshot


def _build_annual_bulletin_snapshot(enrollment, synthesis):
    return {
        "version": 2,
        **_identity_snapshot(enrollment),
        "document": {
            "decision": synthesis.get("academic_decision", ""),
            "mention": "",
        },
        "decision": {
            "code": synthesis.get("academic_decision"),
            "rule_code": synthesis.get("rule_code"),
            "rule_label": synthesis.get("rule_label"),
            "threshold": str(synthesis.get("threshold") or ""),
            "admissibility_gap": str(synthesis.get("admissibility_gap") or ""),
            "requires_academic_debt": synthesis.get("requires_academic_debt"),
            "debt_subjects": [
                {
                    "semester": item.get("semester"),
                    "ue": item.get("ue"),
                    "ec": item.get("ec"),
                    "score": item.get("score"),
                }
                for item in synthesis.get("debt_subjects", [])
            ],
            "reasons": synthesis.get("reasons", []),
        },
        "semesters": synthesis.get("semesters", []),
    }


def _optional_decimal(value):
    if value in (None, ""):
        return None
    return Decimal(str(value))


def _display_optional(value):
    if value in (None, ""):
        return "-"
    return format_decimal(value)


def _semester_result_from_snapshot(snapshot, bulletin):
    result_data = snapshot.get("result", snapshot)
    semester_number = result_data.get("semester_number") or getattr(bulletin.semester, "number", None)
    ue_results = []
    for ue_data in result_data.get("ues", []):
        rows = []
        for ec_data in ue_data.get("ecs", []):
            note = _optional_decimal(ec_data.get("note"))
            note_coefficient = _optional_decimal(ec_data.get("note_coefficient"))
            coefficient = _optional_decimal(ec_data.get("coefficient"))
            credit_required = _optional_decimal(ec_data.get("credit_required")) or Decimal("0")
            credit_obtained = _optional_decimal(ec_data.get("credit_obtained")) or Decimal("0")
            rows.append({
                "ec": SimpleNamespace(
                    title=ec_data.get("title", ""),
                    coefficient=coefficient,
                ),
                "note": note,
                "note_display": _display_optional(note),
                "note_coefficient": note_coefficient,
                "note_coefficient_display": _display_optional(note_coefficient),
                "credit_required": credit_required,
                "credit_required_display": format_decimal(credit_required),
                "credit_obtained": credit_obtained,
                "credit_obtained_display": format_decimal(credit_obtained),
                "ec_coefficient_display": _display_optional(coefficient),
                "is_validated": bool(ec_data.get("is_validated")),
                "session": ec_data.get("session") or "Normale",
            })
        ue_average = _optional_decimal(ue_data.get("average"))
        ue_coefficient = _optional_decimal(ue_data.get("coefficient")) or Decimal("0")
        ue_note_coefficients = _optional_decimal(ue_data.get("total_note_coefficients"))
        ue_credit_required = _optional_decimal(ue_data.get("credit_required")) or Decimal("0")
        ue_credit_obtained = _optional_decimal(ue_data.get("credit_obtained")) or Decimal("0")
        ue_results.append({
            "ue": SimpleNamespace(
                code=ue_data.get("code", ""),
                title=ue_data.get("title", ""),
                coefficient=ue_coefficient,
            ),
            "rows": rows,
            "average": ue_average,
            "average_display": _display_optional(ue_average),
            "total_coefficients": ue_coefficient,
            "total_coefficients_display": format_decimal(ue_coefficient),
            "total_note_coefficients": ue_note_coefficients,
            "total_note_coefficients_display": _display_optional(ue_note_coefficients),
            "credit_required": ue_credit_required,
            "credit_required_display": format_decimal(ue_credit_required),
            "credit_obtained": ue_credit_obtained,
            "credit_obtained_display": format_decimal(ue_credit_obtained),
            "is_validated": ue_data.get("status") == "validated",
        })

    average = _optional_decimal(result_data.get("average"))
    percentage = _optional_decimal(result_data.get("percentage")) or Decimal("0")
    credit_required = _optional_decimal(result_data.get("credit_required")) or Decimal("0")
    credit_obtained = _optional_decimal(result_data.get("credit_obtained")) or Decimal("0")
    total_coefficients = _optional_decimal(result_data.get("total_coefficients")) or Decimal("0")
    return {
        "semester": SimpleNamespace(number=semester_number),
        "ue_results": ue_results,
        "average": average,
        "average_display": _display_optional(average),
        "percentage": percentage,
        "percentage_display": format_decimal(percentage),
        "credit_required": credit_required,
        "credit_required_display": format_decimal(credit_required),
        "credit_obtained": credit_obtained,
        "credit_obtained_display": format_decimal(credit_obtained),
        "total_coefficients": total_coefficients,
        "total_coefficients_display": format_decimal(total_coefficients),
        "is_validated": bool(result_data.get("is_validated")),
        "is_complete": bool(result_data.get("is_complete")),
        "status": result_data.get("status", ""),
    }


def render_bulletin_pdf_bytes(bulletin):
    try:
        from weasyprint import HTML
    except Exception as exc:  # pragma: no cover - dependances systeme
        raise ValidationError(
            "WeasyPrint ou ses dependances systeme ne sont pas disponibles."
        ) from exc

    context = build_bulletin_context(bulletin)
    context.update({
        "pdf_mode": True,
        "pdf_logo_uri": (settings.BASE_DIR / "static" / "institution" / "logo_esfe.png").as_uri(),
    })
    html = render_to_string("academics/reports/bulletin_esfe.html", context)
    return HTML(string=html, base_url=settings.BASE_DIR.as_uri()).write_pdf()


def _persist_bulletin_pdf(bulletin):
    pdf_bytes = render_bulletin_pdf_bytes(bulletin)
    filename = f"bulletin-{bulletin.reference}.pdf"
    bulletin.pdf_file.save(filename, ContentFile(pdf_bytes), save=False)
    bulletin.save(
        update_fields=["pdf_file", "updated_at"],
        allow_published_update=True,
    )
    return bulletin


def get_enrollment_for_student_year(student, academic_year):
    return (
        AcademicEnrollment.objects.select_related("student__student_profile", "academic_class", "academic_year", "programme", "branch")
        .filter(student=student.user, academic_year=academic_year, is_active=True)
        .order_by("-created_at", "-id")
        .first()
    )


@transaction.atomic
def generate_semester_bulletin(*, enrollment, semester, actor=None, publish=False):
    if semester.academic_class_id != enrollment.academic_class_id:
        raise ValidationError("Le semestre ne correspond pas a l'inscription academique.")
    if not get_semester_permissions(semester)["can_generate_reports"]:
        raise ValidationError("Le bulletin semestriel est disponible apres publication du semestre.")

    result = compute_semester_result(semester, enrollment)
    if not result.get("is_complete"):
        raise ValidationError("Toutes les notes doivent etre completes avant de generer le bulletin.")
    if Decimal(str(result.get("credit_required") or 0)) != Decimal(
        str(semester.total_required_credits or 0)
    ):
        raise ValidationError(
            "Le total des credits configures ne correspond pas au total requis du semestre."
        )
    student = _student_for_enrollment(enrollment)
    published_bulletin = (
        AcademicBulletin.objects.select_for_update()
        .filter(
            student=student,
            enrollment=enrollment,
            bulletin_type=AcademicBulletin.TYPE_SEMESTER,
            semester=semester,
            status=AcademicBulletin.STATUS_PUBLISHED,
        )
        .first()
    )
    if published_bulletin is not None:
        if publish and not published_bulletin.pdf_file:
            _persist_bulletin_pdf(published_bulletin)
        return published_bulletin
    status = AcademicBulletin.STATUS_PUBLISHED if publish else AcademicBulletin.STATUS_GENERATED
    now = timezone.now()
    bulletin, _ = AcademicBulletin.objects.update_or_create(
        student=student,
        enrollment=enrollment,
        bulletin_type=AcademicBulletin.TYPE_SEMESTER,
        semester=semester,
        defaults={
            "academic_year": enrollment.academic_year,
            "academic_class": enrollment.academic_class,
            "branch": enrollment.branch,
            "reference": _reference("BUL-S", enrollment, semester.number),
            "status": status,
            "average": result.get("average"),
            "total_credits": result.get("credit_required") or Decimal("0.00"),
            "credits_obtained": result.get("credit_obtained") or Decimal("0.00"),
            "decision": "Valide" if result.get("is_validated") else "Non valide",
            "mention": _mention(result.get("average")),
            "snapshot": _build_semester_bulletin_snapshot(enrollment, result),
            "generated_by": actor if getattr(actor, "is_authenticated", False) else None,
            "generated_at": now,
            "published_by": actor if publish and getattr(actor, "is_authenticated", False) else None,
            "published_at": now if publish else None,
        },
    )
    if publish:
        _persist_bulletin_pdf(bulletin)
    return bulletin


@transaction.atomic
def generate_semester_bulletins_for_class(*, academic_class, semester, actor=None, publish=False):
    semester = Semester.objects.select_for_update().get(pk=semester.pk)
    if semester.academic_class_id != academic_class.id:
        raise ValidationError("Le semestre ne correspond pas a la classe.")
    created = []
    enrollments = AcademicEnrollment.objects.select_related(
        "student__student_profile",
        "academic_class",
        "academic_year",
        "programme",
        "branch",
    ).filter(
        academic_class=academic_class,
        academic_year=academic_class.academic_year,
        is_active=True,
    )
    for enrollment in enrollments:
        created.append(generate_semester_bulletin(enrollment=enrollment, semester=semester, actor=actor, publish=publish))
    return created


@transaction.atomic
def generate_annual_bulletin(*, enrollment, actor=None, publish=False):
    semesters = get_annual_semesters(enrollment.academic_class)
    for semester in semesters:
        if not get_semester_permissions(semester)["can_generate_reports"]:
            raise ValidationError("Le bulletin annuel est disponible apres publication de tous les semestres.")

    official_decision = get_final_annual_decision(enrollment=enrollment)
    synthesis = official_decision.synthesis_snapshot
    student = _student_for_enrollment(enrollment)
    published_bulletin = (
        AcademicBulletin.objects.select_for_update()
        .filter(
            student=student,
            enrollment=enrollment,
            bulletin_type=AcademicBulletin.TYPE_ANNUAL,
            semester__isnull=True,
            status=AcademicBulletin.STATUS_PUBLISHED,
        )
        .first()
    )
    if published_bulletin is not None:
        return published_bulletin
    status = AcademicBulletin.STATUS_PUBLISHED if publish else AcademicBulletin.STATUS_GENERATED
    now = timezone.now()
    bulletin, _ = AcademicBulletin.objects.update_or_create(
        student=student,
        enrollment=enrollment,
        bulletin_type=AcademicBulletin.TYPE_ANNUAL,
        semester=None,
        defaults={
            "academic_year": enrollment.academic_year,
            "academic_class": enrollment.academic_class,
            "branch": enrollment.branch,
            "reference": _reference("BUL-A", enrollment),
            "status": status,
            "average": None,
            "total_credits": Decimal(str(synthesis.get("credits", {}).get("required") or "0")),
            "credits_obtained": Decimal(str(synthesis.get("credits", {}).get("obtained") or "0")),
            "decision": synthesis.get("academic_decision", ""),
            "mention": "",
            "snapshot": _build_annual_bulletin_snapshot(enrollment, synthesis),
            "generated_by": actor if getattr(actor, "is_authenticated", False) else None,
            "generated_at": now,
            "published_by": actor if publish and getattr(actor, "is_authenticated", False) else None,
            "published_at": now if publish else None,
        },
    )
    if publish:
        _persist_bulletin_pdf(bulletin)
    return bulletin


def _is_snapshot_subset(expected, current):
    if isinstance(expected, dict):
        return isinstance(current, dict) and all(
            key in current and _is_snapshot_subset(value, current[key])
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(current, list)
            and len(expected) == len(current)
            and all(_is_snapshot_subset(left, right) for left, right in zip(expected, current))
        )
    return expected == current


@transaction.atomic
def backfill_published_bulletin(bulletin):
    """Fige les anciens bulletins publies sans reecrire un contenu divergent."""

    bulletin = (
        AcademicBulletin.objects.select_for_update()
        .get(pk=bulletin.pk)
    )
    if bulletin.status != AcademicBulletin.STATUS_PUBLISHED:
        raise ValidationError("Seuls les bulletins publies peuvent etre figes.")

    snapshot_updated = False
    if (bulletin.snapshot or {}).get("version") != 2:
        old_snapshot = bulletin.snapshot or {}
        if bulletin.bulletin_type == AcademicBulletin.TYPE_SEMESTER:
            if not bulletin.semester_id:
                raise ValidationError("Bulletin semestriel sans semestre.")
            result = compute_semester_result(bulletin.semester, bulletin.enrollment)
            serialized = _serialize_semester_result(result, bulletin.enrollment)
            old_result = old_snapshot.get("result", old_snapshot)
            if not result.get("is_complete") or not _is_snapshot_subset(old_result, serialized):
                raise ValidationError("Les donnees actuelles divergent du snapshot historique.")
            if (
                bulletin.average != result.get("average")
                or bulletin.total_credits != result.get("credit_required")
                or bulletin.credits_obtained != result.get("credit_obtained")
            ):
                raise ValidationError("Les totaux actuels divergent du bulletin publie.")
            bulletin.snapshot = _build_semester_bulletin_snapshot(bulletin.enrollment, result)
        else:
            official_decision = get_final_annual_decision(enrollment=bulletin.enrollment)
            current_snapshot = _build_annual_bulletin_snapshot(
                bulletin.enrollment,
                official_decision.synthesis_snapshot,
            )
            if bulletin.decision != official_decision.synthesis_snapshot.get("academic_decision"):
                raise ValidationError("La decision officielle diverge du bulletin publie.")
            bulletin.snapshot = current_snapshot

        bulletin.save(
            update_fields=["snapshot", "updated_at"],
            allow_published_update=True,
        )
        snapshot_updated = True

    pdf_created = False
    if not bulletin.pdf_file:
        _persist_bulletin_pdf(bulletin)
        pdf_created = True

    return bulletin, snapshot_updated, pdf_created


@transaction.atomic
def generate_annual_bulletins_for_class(*, academic_class, actor=None, publish=False):
    semesters = get_annual_semesters(academic_class)
    if any(not get_semester_permissions(semester)["can_generate_reports"] for semester in semesters):
        raise ValidationError(
            "Les bulletins annuels sont disponibles après publication de tous les semestres de la maquette."
        )
    created = []
    enrollment_ids = list(StudentYearDecision.objects.filter(
        current_class=academic_class,
        academic_year=academic_class.academic_year,
        is_final=True,
        source_enrollment__isnull=False,
    ).exclude(synthesis_snapshot={}).values_list("source_enrollment_id", flat=True))
    active_enrollment_count = AcademicEnrollment.objects.filter(
        academic_class=academic_class,
        academic_year=academic_class.academic_year,
        is_active=True,
    ).count()
    if not enrollment_ids or len(enrollment_ids) != active_enrollment_count:
        raise ValidationError(
            "Les bulletins annuels sont disponibles après la délibération annuelle officielle de toute la classe."
        )
    enrollments = AcademicEnrollment.objects.select_related(
        "student__student_profile",
        "academic_class",
        "academic_year",
        "programme",
        "branch",
    ).filter(pk__in=enrollment_ids)
    for enrollment in enrollments:
        bulletin = generate_annual_bulletin(enrollment=enrollment, actor=actor, publish=publish)
        created.append(bulletin)
    return created


def build_bulletin_context(bulletin):
    snapshot = bulletin.snapshot or {}
    identity = snapshot.get("student", {})
    academic = snapshot.get("academic", {})
    document = snapshot.get("document", {})
    student = bulletin.student
    candidature = getattr(getattr(student, "inscription", None), "candidature", None)
    programme = bulletin.enrollment.programme
    if bulletin.bulletin_type == AcademicBulletin.TYPE_SEMESTER and bulletin.semester_id:
        context = {
            "semester_result": _semester_result_from_snapshot(snapshot, bulletin),
            "semester": bulletin.semester,
            "average_display": format_decimal(bulletin.average),
        }
    else:
        context = {
            "average_display": None,
        }
    context.update(
        {
            "student": student,
            "enrollment": bulletin.enrollment,
            "academic_class": bulletin.academic_class,
            "academic_year": bulletin.academic_year,
            "bulletin": bulletin,
            "student_full_name": identity.get("full_name") or getattr(student, "full_name", str(student)),
            "student_matricule": identity.get("matricule") or student.matricule,
            "student_last_name": identity.get("last_name") or (getattr(candidature, "last_name", "") or ""),
            "student_first_name": identity.get("first_name") or (getattr(candidature, "first_name", "") or ""),
            "student_birth_info": identity.get("birth_info") or "Non renseigne",
            "academic_year_display": academic.get("academic_year") or str(bulletin.academic_year),
            "class_display": academic.get("academic_class") or bulletin.academic_class.display_name,
            "programme_name": academic.get("programme_name") or getattr(programme, "title", ""),
            "department_name": academic.get("department_name") or getattr(getattr(programme, "filiere", None), "name", ""),
            "domain_name": academic.get("domain_name") or getattr(getattr(programme, "cycle", None), "name", ""),
            "branch_name": academic.get("branch_name") or getattr(bulletin.branch, "name", ""),
            "decision_display": document.get("decision") or bulletin.decision,
            "mention_display": document.get("mention") or bulletin.mention,
            "total_credits_display": format_decimal(bulletin.total_credits),
            "credits_obtained_display": format_decimal(bulletin.credits_obtained),
        }
    )
    return context


@transaction.atomic
def prepare_diploma_award(*, enrollment, actor=None, publish=False):
    official_decision = get_final_annual_decision(enrollment=enrollment)
    synthesis = official_decision.synthesis_snapshot
    if synthesis.get("academic_decision") != DECISION_VALIDE:
        raise ValidationError("Le diplome ne peut etre prepare que pour un cycle termine (decision VALIDE).")

    pending_debts = AcademicDebt.objects.filter(
        enrollment=enrollment,
        status=AcademicDebt.STATUS_PENDING,
    )
    if pending_debts.exists():
        subjects = ", ".join(
            str(d.ec) for d in pending_debts.select_related("ec")[:5]
        )
        raise ValidationError(
            f"Diplome bloque : {pending_debts.count()} dette(s) academique(s) non soldee(s) "
            f"({subjects}{'...' if pending_debts.count() > 5 else ''}). "
            "Toutes les dettes doivent etre soldees avant l'obtention du diplome."
        )

    student = _student_for_enrollment(enrollment)
    status = AcademicDiplomaAward.STATUS_DELIVERED if publish else AcademicDiplomaAward.STATUS_READY
    now = timezone.now()
    final_average = None
    semester_results = synthesis.get("semesters", [])
    if semester_results:
        averages = [
            Decimal(str(sr.get("average")))
            for sr in semester_results
            if sr.get("average") is not None
        ]
        if averages:
            final_average = (sum(averages) / len(averages)).quantize(Decimal("0.01"))
    award, _ = AcademicDiplomaAward.objects.update_or_create(
        student=student,
        programme=enrollment.programme,
        academic_year=enrollment.academic_year,
        defaults={
            "enrollment": enrollment,
            "academic_class": enrollment.academic_class,
            "branch": enrollment.branch,
            "diploma": enrollment.programme.diploma_awarded,
            "reference": _reference("DIP", enrollment),
            "status": status,
            "final_average": final_average,
            "mention": _mention(final_average),
            "decision": synthesis.get("academic_decision", ""),
            "awarded_at": timezone.localdate() if publish else None,
            "prepared_by": actor if getattr(actor, "is_authenticated", False) else None,
            "delivered_by": actor if publish and getattr(actor, "is_authenticated", False) else None,
            "delivered_at": now if publish else None,
            "snapshot": {
                "decision": synthesis.get("academic_decision"),
                "rule_code": synthesis.get("rule_code"),
                "final_average": str(final_average) if final_average is not None else None,
                "credit_required": str(synthesis.get("credits", {}).get("required") or "0"),
                "credit_obtained": str(synthesis.get("credits", {}).get("obtained") or "0"),
            },
        },
    )
    return award


def prepare_diploma_awards_for_class(*, academic_class, actor=None, publish=False):
    awards = []
    skipped = []
    enrollment_ids = StudentYearDecision.objects.filter(
        current_class=academic_class,
        academic_year=academic_class.academic_year,
        is_final=True,
        source_enrollment__isnull=False,
    ).exclude(synthesis_snapshot={}).values_list("source_enrollment_id", flat=True)
    enrollments = AcademicEnrollment.objects.select_related(
        "student__student_profile",
        "academic_class",
        "academic_year",
        "programme__diploma_awarded",
        "branch",
    ).filter(pk__in=enrollment_ids)
    for enrollment in enrollments:
        try:
            awards.append(prepare_diploma_award(enrollment=enrollment, actor=actor, publish=publish))
        except ValidationError as exc:
            skipped.append({"enrollment_id": enrollment.id, "message": " ".join(exc.messages)})
    return {"awards": awards, "skipped": skipped}


def build_diploma_context(award):
    return {
        "award": award,
        "student": award.student,
        "student_full_name": getattr(award.student, "full_name", str(award.student)),
        "student_matricule": award.student.matricule,
        "academic_year": award.academic_year,
        "programme": award.programme,
        "diploma": award.diploma,
        "average_display": format_decimal(award.final_average),
    }
