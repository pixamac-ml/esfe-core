from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from academics.models import AcademicBulletin, AcademicDebt, AcademicDecisionLog, AcademicDiplomaAward, AcademicEnrollment, Semester
from academics.services.reporting import build_student_semester_report, format_decimal
from academics.services.semester import compute_semester_result
from academics.services.workflow import get_semester_permissions
from academics.services.year import DECISION_VALIDE, DECISION_ADMISSIBLE, DECISION_NON_ADMIS, compute_annual_decision


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


def _serialize_semester_result(result):
    return {
        "average": str(result.get("average")) if result.get("average") is not None else None,
        "percentage": str(result.get("percentage") or "0"),
        "credit_required": str(result.get("credit_required") or "0"),
        "credit_obtained": str(result.get("credit_obtained") or "0"),
        "is_validated": bool(result.get("is_validated")),
        "is_complete": bool(result.get("is_complete")),
        "status": result.get("status"),
        "missing_grades": result.get("missing_grades", 0),
        "ues": [
            {
                "code": ue_result["ue"].code,
                "title": ue_result["ue"].title,
                "average": str(ue_result.get("average")) if ue_result.get("average") is not None else None,
                "credit_required": str(ue_result.get("credit_required") or "0"),
                "credit_obtained": str(ue_result.get("credit_obtained") or "0"),
                "status": ue_result.get("status"),
                "ecs": [
                    {
                        "title": row["ec"].title,
                        "note": str(row.get("note")) if row.get("note") is not None else None,
                        "credit_required": str(row.get("credit_required") or "0"),
                        "credit_obtained": str(row.get("credit_obtained") or "0"),
                        "is_validated": bool(row.get("is_validated")),
                    }
                    for row in ue_result.get("rows", [])
                ],
            }
            for ue_result in result.get("ue_results", [])
        ],
    }


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
    student = _student_for_enrollment(enrollment)
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
            "snapshot": _serialize_semester_result(result),
            "generated_by": actor if getattr(actor, "is_authenticated", False) else None,
            "generated_at": now,
            "published_by": actor if publish and getattr(actor, "is_authenticated", False) else None,
            "published_at": now if publish else None,
        },
    )
    return bulletin


def generate_semester_bulletins_for_class(*, academic_class, semester, actor=None, publish=False):
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
    semesters = list(enrollment.academic_class.semesters.all().order_by("number"))
    for semester in semesters:
        if not get_semester_permissions(semester)["can_generate_reports"]:
            raise ValidationError("Le bulletin annuel est disponible apres publication de tous les semestres.")

    decision = compute_annual_decision(enrollment)
    student = _student_for_enrollment(enrollment)
    status = AcademicBulletin.STATUS_PUBLISHED if publish else AcademicBulletin.STATUS_GENERATED
    now = timezone.now()
    semester_results = [
        _serialize_semester_result(sr)
        for sr in decision.get("semester_results", [])
    ]
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
            "total_credits": decision.get("annual_result", {}).get("credit_required") or Decimal("0.00"),
            "credits_obtained": decision.get("annual_result", {}).get("credit_obtained") or Decimal("0.00"),
            "decision": decision.get("decision", ""),
            "mention": "",
            "snapshot": {
                "decision": {
                    "code": decision.get("decision"),
                    "rule_code": decision.get("rule_code"),
                    "rule_label": decision.get("rule_label"),
                    "threshold": str(decision.get("threshold") or ""),
                    "admissibility_gap": str(decision.get("admissibility_gap") or ""),
                    "requires_academic_debt": decision.get("requires_academic_debt"),
                    "debt_subjects": [
                        {
                            "semester": d.get("semester"),
                            "ue": d.get("ue"),
                            "ec": d.get("ec"),
                            "score": d.get("score"),
                        }
                        for d in decision.get("debt_subjects", [])
                    ],
                    "reasons": decision.get("reasons", []),
                },
                "semesters": semester_results,
            },
            "generated_by": actor if getattr(actor, "is_authenticated", False) else None,
            "generated_at": now,
            "published_by": actor if publish and getattr(actor, "is_authenticated", False) else None,
            "published_at": now if publish else None,
        },
    )
    return bulletin


def _create_decision_log(*, academic_class, actor, enrollment_decisions, publish=False):
    """
    Cree un AcademicDecisionLog a partir des decisions de tous les etudiants d'une classe.
    """
    threshold = None
    gap = None
    rule_codes = set()
    validated = admissible = non_admis = 0

    for d in enrollment_decisions:
        code = d.get("decision", "")
        if code == DECISION_VALIDE:
            validated += 1
        elif code == DECISION_ADMISSIBLE:
            admissible += 1
        elif code == DECISION_NON_ADMIS:
            non_admis += 1
        rule_code = d.get("rule_code")
        if rule_code:
            rule_codes.add(rule_code)
        if threshold is None:
            threshold = d.get("threshold")
            gap = d.get("admissibility_gap")

    total = validated + admissible + non_admis
    if total == 0:
        return None

    return AcademicDecisionLog.objects.create(
        academic_class=academic_class,
        academic_year=academic_class.academic_year,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        threshold=threshold or Decimal("0"),
        admissibility_gap=gap or Decimal("0"),
        total_students=total,
        validated_count=validated,
        admissible_count=admissible,
        non_admis_count=non_admis,
        rule_codes_used=sorted(rule_codes),
        details={
            "publish": bool(publish),
        },
    )


def generate_annual_bulletins_for_class(*, academic_class, actor=None, publish=False):
    created = []
    enrollment_decisions = []
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
        bulletin = generate_annual_bulletin(enrollment=enrollment, actor=actor, publish=publish)
        created.append(bulletin)
        decision = compute_annual_decision(enrollment)
        enrollment_decisions.append(decision)
    _create_decision_log(academic_class=academic_class, actor=actor, enrollment_decisions=enrollment_decisions, publish=publish)
    return created


def build_bulletin_context(bulletin):
    if bulletin.bulletin_type == AcademicBulletin.TYPE_SEMESTER and bulletin.semester_id:
        context = build_student_semester_report(bulletin.student_id, bulletin.semester_id)
        context.update(
            {
                "average_display": format_decimal(bulletin.average),
            }
        )
    else:
        context = {
            "student": bulletin.student,
            "enrollment": bulletin.enrollment,
            "academic_class": bulletin.academic_class,
            "academic_year": bulletin.academic_year,
            "average_display": None,
        }
    context.update(
        {
            "bulletin": bulletin,
            "student_full_name": getattr(bulletin.student, "full_name", str(bulletin.student)),
            "student_matricule": bulletin.student.matricule,
            "total_credits_display": format_decimal(bulletin.total_credits),
            "credits_obtained_display": format_decimal(bulletin.credits_obtained),
        }
    )
    return context


@transaction.atomic
def prepare_diploma_award(*, enrollment, actor=None, publish=False):
    decision = compute_annual_decision(enrollment)
    if decision.get("decision") != DECISION_VALIDE:
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
    semester_results = decision.get("semester_results", [])
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
            "decision": decision.get("decision", ""),
            "awarded_at": timezone.localdate() if publish else None,
            "prepared_by": actor if getattr(actor, "is_authenticated", False) else None,
            "delivered_by": actor if publish and getattr(actor, "is_authenticated", False) else None,
            "delivered_at": now if publish else None,
            "snapshot": {
                "decision": decision.get("decision"),
                "rule_code": decision.get("rule_code"),
                "final_average": str(final_average) if final_average is not None else None,
                "credit_required": str(decision.get("annual_result", {}).get("credit_required") or "0"),
                "credit_obtained": str(decision.get("annual_result", {}).get("credit_obtained") or "0"),
            },
        },
    )
    return award


def prepare_diploma_awards_for_class(*, academic_class, actor=None, publish=False):
    awards = []
    skipped = []
    enrollments = AcademicEnrollment.objects.select_related(
        "student__student_profile",
        "academic_class",
        "academic_year",
        "programme__diploma_awarded",
        "branch",
    ).filter(
        academic_class=academic_class,
        academic_year=academic_class.academic_year,
        is_active=True,
    )
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
