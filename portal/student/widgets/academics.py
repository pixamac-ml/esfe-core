from decimal import Decimal

from academics.models import AcademicEnrollment, EC, ECGrade


def _format_decimal(value):
    if value is None:
        return "0"
    if isinstance(value, Decimal):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def get_student_academic_snapshot(user):
    if not getattr(user, "is_authenticated", False):
        return {
            "student": None,
            "academic_enrollment": None,
            "academic_class": None,
            "academic_programme": None,
            "academic_year": None,
            "academic_level": None,
            "academic_ecs": [],
            "academic_status": "pending",
            "academic_status_message": "Connexion requise pour afficher votre situation academique.",
        }

    student = getattr(user, "student_profile", None)
    if student is None:
        return {
            "student": None,
            "academic_enrollment": None,
            "academic_class": None,
            "academic_programme": None,
            "academic_year": None,
            "academic_level": None,
            "academic_ecs": [],
            "academic_status": "pending",
            "academic_status_message": "Votre compte etudiant est en cours de finalisation.",
        }

    enrollment = (
        AcademicEnrollment.objects.select_related(
            "academic_class",
            "academic_year",
            "programme",
            "branch",
        )
        .filter(student=user, is_active=True)
        .order_by("-created_at", "-id")
        .first()
    )

    if enrollment is None:
        return {
            "student": student,
            "academic_enrollment": None,
            "academic_class": None,
            "academic_programme": None,
            "academic_year": None,
            "academic_level": None,
            "academic_ecs": [],
            "academic_status": "pending",
            "academic_status_message": "Affectation academique en cours ou requise.",
        }

    academic_class = enrollment.academic_class
    ecs = list(
        EC.objects.select_related(
            "ue",
            "ue__semester",
        )
        .filter(ue__semester__academic_class=academic_class)
        .order_by("ue__semester__number", "ue__code", "id")
    )

    if academic_class is None or enrollment.programme is None or enrollment.academic_year is None:
        return {
            "student": student,
            "academic_enrollment": enrollment,
            "academic_class": academic_class,
            "academic_programme": enrollment.programme,
            "academic_year": enrollment.academic_year,
            "academic_level": getattr(academic_class, "level", None),
            "academic_ecs": ecs,
            "academic_status": "error",
            "academic_status_message": "Vos donnees academiques sont incompletes ou incoherentes.",
        }

    return {
        "student": student,
        "academic_enrollment": enrollment,
        "academic_class": academic_class,
        "academic_programme": enrollment.programme,
        "academic_year": enrollment.academic_year,
        "academic_level": academic_class.level,
        "academic_ecs": ecs,
        "academic_status": "assigned",
        "academic_status_message": "Votre affectation academique est active.",
    }


def get_academics_widget(user):
    snapshot = get_student_academic_snapshot(user)
    academic_class = snapshot["academic_class"]
    ecs = snapshot["academic_ecs"]
    total_credits = sum((ec.credit_required or 0) for ec in ecs)
    semester_numbers = sorted({ec.ue.semester.number for ec in ecs if getattr(ec.ue, "semester", None)})
    enrollment = snapshot["academic_enrollment"]
    grades = list(ECGrade.objects.filter(enrollment=enrollment).select_related("ec", "ec__ue", "ec__ue__semester")) if enrollment else []
    scored = [grade.final_score for grade in grades if grade.final_score is not None]
    average = sum(scored) / len(scored) if scored else None
    credits_obtained = sum((grade.credit_obtained or Decimal("0")) for grade in grades)
    validated_count = sum(1 for grade in grades if grade.is_validated)
    failed_count = sum(1 for grade in grades if grade.final_score is not None and not grade.is_validated)
    pending_count = max(len(ecs) - len(scored), 0)
    validation_rate = round((validated_count / len(ecs)) * 100) if ecs else 0
    grade_by_ec_id = {grade.ec_id: grade for grade in grades}
    active_semester = None
    if academic_class is not None:
        active_semester = (
            academic_class.semesters.exclude(status="FINALIZED")
            .order_by("number")
            .first()
            or academic_class.semesters.order_by("-number").first()
        )
    semester_rows = []
    for number in semester_numbers:
        semester_ecs = [ec for ec in ecs if ec.ue.semester.number == number]
        semester_grades = [grade_by_ec_id.get(ec.id) for ec in semester_ecs if grade_by_ec_id.get(ec.id)]
        semester_scores = [grade.final_score for grade in semester_grades if grade.final_score is not None]
        semester_average = sum(semester_scores) / len(semester_scores) if semester_scores else None
        semester_validated = sum(1 for grade in semester_grades if grade.is_validated)
        semester_rows.append(
            {
                "label": f"S{number}",
                "average": f"{semester_average:.2f}/20" if semester_average is not None else "En attente",
                "validated": f"{semester_validated}/{len(semester_ecs)} EC",
                "progress": round((semester_validated / len(semester_ecs)) * 100) if semester_ecs else 0,
            }
        )
    grade_rows = []
    for ec in ecs[:12]:
        grade = grade_by_ec_id.get(ec.id)
        grade_rows.append(
            {
                "semester": f"S{ec.ue.semester.number}",
                "code": ec.ue.code,
                "title": ec.title,
                "score": f"{grade.final_score:.2f}/20" if grade and grade.final_score is not None else "En attente",
                "credits": f"{(grade.credit_obtained or Decimal('0')):.2f}/{(ec.credit_required or Decimal('0')):.2f}".replace(".00", "") if grade else f"0/{ec.credit_required}",
                "is_validated": bool(grade and grade.is_validated),
            }
        )

    status_labels = {
        "assigned": "Affecte",
        "pending": "En attente",
        "error": "Erreur",
    }
    status_tones = {
        "assigned": "success",
        "pending": "warning",
        "error": "danger",
    }

    return {
        "average": f"{average:.2f}/20" if average is not None else "Non disponible",
        "credits": f"{_format_decimal(credits_obtained)}/{_format_decimal(total_credits)}",
        "credits_obtained": _format_decimal(credits_obtained),
        "credits_required": _format_decimal(total_credits),
        "validated_count": validated_count,
        "failed_count": failed_count,
        "pending_count": pending_count,
        "validation_rate": validation_rate,
        "semester_rows": semester_rows,
        "grade_rows": grade_rows,
        "status": status_labels.get(snapshot["academic_status"], "En attente"),
        "status_tone": status_tones.get(snapshot["academic_status"], "warning"),
        "formation": getattr(snapshot["academic_programme"], "title", "Non disponible"),
        "level": getattr(academic_class, "level", None) or "Non disponible",
        "academic_year": str(snapshot["academic_year"]) if snapshot["academic_year"] else "Non disponible",
        "classroom": str(academic_class) if academic_class else "Non disponible",
        "active_semester": f"S{active_semester.number}" if active_semester else "Non disponible",
        "semester": ", ".join(f"S{number}" for number in semester_numbers) if semester_numbers else "Non disponible",
        "progress": 100 if snapshot["academic_status"] == "assigned" else 25,
        "status_message": snapshot["academic_status_message"],
    }

