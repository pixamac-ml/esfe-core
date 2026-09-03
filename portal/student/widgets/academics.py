from decimal import Decimal

from academics.models import AcademicBulletin, AcademicEnrollment, AcademicYear, EC, ECGrade, Semester


def _format_decimal(value):
    if value is None:
        return "0"
    if isinstance(value, Decimal):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def get_student_academic_snapshot(user, academic_year_id=None):
    """Return the student's real annual context.

    By default this preserves the existing active-year behavior.  A selected
    year is always constrained to the requesting student's own enrollments,
    including archived historical enrollments.
    """
    requested_year_id = int(academic_year_id) if str(academic_year_id or "").isdigit() else None
    base_context = {
        "available_academic_years": [],
        "selected_academic_year_id": None,
        "is_historical_context": False,
    }
    if not getattr(user, "is_authenticated", False):
        return {
            **base_context,
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
            **base_context,
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

    enrollment_queryset = (
        AcademicEnrollment.objects.select_related(
            "academic_class",
            "academic_year",
            "programme",
            "branch",
        )
        .filter(student=user)
    )
    available_academic_years = list(
        AcademicYear.objects.filter(academic_enrollments__student=user)
        .distinct()
        .order_by("-start_date", "-id")
    )
    base_context["available_academic_years"] = available_academic_years
    if requested_year_id is not None:
        enrollment = enrollment_queryset.filter(academic_year_id=requested_year_id).order_by("-created_at", "-id").first()
    else:
        enrollment = enrollment_queryset.filter(
            status=AcademicEnrollment.STATUS_ACTIVE,
            is_active=True,
            is_archived=False,
        ).order_by("-created_at", "-id").first()

    if enrollment is None:
        return {
            **base_context,
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
            **base_context,
            "student": student,
            "academic_enrollment": enrollment,
            "academic_class": academic_class,
            "academic_programme": enrollment.programme,
            "academic_year": enrollment.academic_year,
            "academic_level": getattr(academic_class, "level", None),
            "academic_ecs": ecs,
            "academic_status": "error",
            "academic_status_message": "Vos donnees academiques sont incompletes ou incoherentes.",
            "selected_academic_year_id": enrollment.academic_year_id,
            "is_historical_context": not enrollment.is_active,
        }

    return {
        **base_context,
        "student": student,
        "academic_enrollment": enrollment,
        "academic_class": academic_class,
        "academic_programme": enrollment.programme,
        "academic_year": enrollment.academic_year,
        "academic_level": academic_class.level,
        "academic_ecs": ecs,
        "academic_status": "assigned",
        "academic_status_message": "Votre affectation academique est active.",
        "selected_academic_year_id": enrollment.academic_year_id,
        "is_historical_context": not enrollment.is_active,
    }


def get_academics_widget(user, academic_year_id=None):
    snapshot = get_student_academic_snapshot(user, academic_year_id=academic_year_id)
    academic_class = snapshot["academic_class"]
    ecs = snapshot["academic_ecs"]
    total_credits = sum((ec.credit_required or 0) for ec in ecs)
    semester_numbers = sorted({ec.ue.semester.number for ec in ecs if getattr(ec.ue, "semester", None)})
    enrollment = snapshot["academic_enrollment"]
    grades = list(
        ECGrade.objects.filter(
            enrollment=enrollment,
            ec__ue__semester__status=Semester.STATUS_PUBLISHED,
        ).select_related("ec", "ec__ue", "ec__ue__semester")
    ) if enrollment else []
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
            academic_class.semesters.exclude(
                status__in=[Semester.STATUS_FINALIZED, Semester.STATUS_PUBLISHED]
            )
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

    published_bulletins = list(
        AcademicBulletin.objects.filter(
            enrollment=enrollment,
            student=snapshot["student"],
            bulletin_type=AcademicBulletin.TYPE_SEMESTER,
            status=AcademicBulletin.STATUS_PUBLISHED,
        ).select_related("semester", "academic_year").order_by("semester__number", "bulletin_type")
    ) if enrollment and snapshot["student"] else []
    published_annual_bulletin = (
        AcademicBulletin.objects.filter(
            enrollment=enrollment,
            student=snapshot["student"],
            bulletin_type=AcademicBulletin.TYPE_ANNUAL,
            status=AcademicBulletin.STATUS_PUBLISHED,
        )
        .select_related("academic_year")
        .order_by("-published_at", "-id")
        .first()
        if enrollment and snapshot["student"] else None
    )

    published_transcripts = []
    published_by_semester_number = {}
    for bulletin in published_bulletins:
        result_snapshot = (bulletin.snapshot or {}).get("result", {})
        session_labels = {
            ec.get("session")
            for ue in result_snapshot.get("ues", [])
            for ec in ue.get("ecs", [])
            if ec.get("session")
        }
        session_label = "Rattrapage" if session_labels == {"Rattrapage"} else (
            "Normale / rattrapage" if "Rattrapage" in session_labels else "Normale"
        )
        row = {
            "bulletin": bulletin,
            "semester": bulletin.semester,
            "average": f"{_format_decimal(bulletin.average)}/20",
            "credits": f"{_format_decimal(bulletin.credits_obtained)}/{_format_decimal(bulletin.total_credits)}",
            "decision": (bulletin.snapshot or {}).get("document", {}).get("decision") or bulletin.decision,
            "session": session_label,
        }
        published_transcripts.append(row)
        published_by_semester_number[bulletin.semester.number] = row

    semester_rows = []
    for number in semester_numbers:
        official_row = published_by_semester_number.get(number)
        if official_row:
            semester_rows.append({
                "label": f"S{number}",
                "average": official_row["average"],
                "validated": f"{official_row['decision']} · {official_row['credits']} crédits",
                "progress": 100,
            })
        else:
            semester_rows.append({
                "label": f"S{number}",
                "average": "Résultats non publiés",
                "validated": "Consultation indisponible avant publication officielle",
                "progress": 0,
            })

    return {
        "selected_academic_year_id": snapshot["selected_academic_year_id"],
        "is_historical_context": snapshot["is_historical_context"],
        "average": published_transcripts[-1]["average"] if published_transcripts else "Non disponible",
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
        "published_bulletins": published_bulletins,
        "published_transcripts": published_transcripts,
        "published_annual_bulletin": published_annual_bulletin,
    }

