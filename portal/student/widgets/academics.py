from academics.models import AcademicEnrollment, EC


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

    status_labels = {
        "assigned": "Affecte",
        "pending": "En attente",
        "error": "Erreur",
    }

    return {
        "average": "Non disponible",
        "credits": str(total_credits),
        "status": status_labels.get(snapshot["academic_status"], "En attente"),
        "formation": getattr(snapshot["academic_programme"], "title", "Non disponible"),
        "classroom": str(academic_class) if academic_class else "Non disponible",
        "semester": ", ".join(f"S{number}" for number in semester_numbers) if semester_numbers else "Non disponible",
        "progress": 100 if snapshot["academic_status"] == "assigned" else 25,
        "status_message": snapshot["academic_status_message"],
    }

