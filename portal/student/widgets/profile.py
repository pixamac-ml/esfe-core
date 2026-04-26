def get_profile_widget(user):
    if not user.is_authenticated:
        return {
            "full_name": "",
            "email": "",
            "phone": "",
            "matricule": "Non disponible",
            "formation": "Non disponible",
            "classroom": "Non disponible",
            "annexe": "Non disponible",
            "photo_url": None,
        }

    context = {
        "full_name": user.get_full_name() or getattr(user, "username", ""),
        "email": getattr(user, "email", ""),
        "phone": "",
        "matricule": "Non disponible",
        "formation": "Non disponible",
        "classroom": "Non disponible",
        "annexe": "Non disponible",
        "photo_url": None,
    }

    student = getattr(user, "student_profile", None)
    if student is None:
        return context

    candidature = student.inscription.candidature
    context.update(
        {
            "full_name": student.full_name,
            "email": student.email,
            "matricule": student.matricule,
            "formation": getattr(candidature.programme, "title", "Non disponible"),
            "annexe": getattr(candidature.branch, "name", "Non disponible"),
        }
    )

    enrollment = getattr(student.inscription, "academic_enrollment", None)
    if enrollment is not None:
        context["classroom"] = enrollment.academic_class.display_name

    return context
