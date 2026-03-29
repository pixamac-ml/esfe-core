from django.core.mail import send_mail

from core.emailing import send_templated_email


# ======================================================
# FONCTION GENERIQUE D'ENVOI D'EMAIL
# ======================================================

def send_institutional_email(subject, template, context, recipient):
    """
    Envoi d'un email institutionnel HTML + texte.
    """

    try:
        return send_templated_email(
            subject=subject,
            recipient=recipient,
            html_template=template,
            context=context,
            fail_silently=False,
        )
    except Exception:
        # Fallback text si le template HTML a un souci.
        send_mail(
            subject=subject,
            message=context.get("fallback_message", "Notification institutionnelle."),
            from_email=None,
            recipient_list=[recipient],
            fail_silently=False,
        )
        return True


# ======================================================
# EMAIL : CANDIDATURE ACCEPTÉE
# ======================================================

def send_application_accepted_email(candidature):

    subject = "[ESFE] Admission confirmée"

    context = {
        "title": "Votre candidature a été acceptée",
        "first_name": candidature.first_name,
        "programme": candidature.programme.title,
        "academic_year": candidature.academic_year,
        "candidature_reference": candidature.reference,
        "fallback_message": (
            f"Votre candidature ({candidature.reference}) a ete acceptee. "
            "Veuillez proceder a l'inscription."
        ),
    }

    send_institutional_email(
        subject,
        "emails/admission_accepted.html",
        context,
        candidature.email,
    )


def send_application_under_review_email(candidature):

    subject = "[ESFE] Candidature en cours d'analyse"

    context = {
        "title": "Votre candidature est en cours d'analyse",
        "first_name": candidature.first_name,
        "programme": candidature.programme.title,
        "academic_year": candidature.academic_year,
        "candidature_reference": candidature.reference,
        "fallback_message": (
            f"Votre candidature ({candidature.reference}) est en cours d'analyse. "
            "Nous revenons vers vous rapidement."
        ),
    }

    send_institutional_email(
        subject,
        "emails/admission_under_review.html",
        context,
        candidature.email,
    )


def send_application_accepted_with_reserve_email(candidature):

    subject = "[ESFE] Admission sous réserve"

    context = {
        "title": "Votre candidature est acceptee sous reserve",
        "first_name": candidature.first_name,
        "programme": candidature.programme.title,
        "academic_year": candidature.academic_year,
        "candidature_reference": candidature.reference,
        "comment": candidature.admin_comment or "Veuillez finaliser les conditions indiquees par l'administration.",
        "fallback_message": (
            f"Votre candidature ({candidature.reference}) est acceptee sous reserve. "
            "Veuillez consulter les conditions a remplir."
        ),
    }

    send_institutional_email(
        subject,
        "emails/admission_accepted_with_reserve.html",
        context,
        candidature.email,
    )


# ======================================================
# EMAIL : CANDIDATURE REFUSÉE
# ======================================================

def send_application_rejected_email(candidature):

    subject = "[ESFE] Décision concernant votre candidature"

    reason = candidature.admin_comment or "Votre dossier ne remplit pas les critères requis."

    context = {
        "title": "Décision concernant votre candidature",
        "first_name": candidature.first_name,
        "reason": reason,
        "candidature_reference": candidature.reference,
        "fallback_message": (
            f"Votre candidature ({candidature.reference}) n'a pas ete retenue. "
            f"Motif: {reason}"
        ),
    }

    send_institutional_email(
        subject,
        "emails/admission_rejected.html",
        context,
        candidature.email,
    )


# ======================================================
# EMAIL : DOSSIER À COMPLÉTER
# ======================================================

def send_application_to_complete_email(candidature):

    subject = "[ESFE] Votre dossier de candidature doit être complété"

    comment = candidature.admin_comment or "Veuillez vérifier les documents demandés."

    context = {
        "title": "Votre dossier doit être complété",
        "first_name": candidature.first_name,
        "comment": comment,
        "candidature_reference": candidature.reference,
        "fallback_message": (
            f"Votre candidature ({candidature.reference}) doit etre completee. "
            f"Commentaire: {comment}"
        ),
    }

    send_institutional_email(
        subject,
        "emails/admission_complete.html",
        context,
        candidature.email,
    )

