from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings


# ======================================================
# FONCTION GENERIQUE D'ENVOI D'EMAIL
# ======================================================

def send_institutional_email(subject, template, context, recipient):
    """
    Envoi d'un email institutionnel HTML + texte.
    """

    html_content = render_to_string(template, context)

    email = EmailMultiAlternatives(
        subject=subject,
        body="",
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
    )

    email.attach_alternative(html_content, "text/html")
    email.send()


# ======================================================
# EMAIL : CANDIDATURE ACCEPTÉE
# ======================================================

def send_application_accepted_email(candidature):

    subject = "Admission confirmée - École de Santé Félix Houphouët-Boigny"

    context = {
        "title": "Votre candidature a été acceptée",
        "first_name": candidature.first_name,
        "programme": candidature.programme,
        "academic_year": candidature.academic_year,
    }

    send_institutional_email(
        subject,
        "emails/admission_accepted.html",
        context,
        candidature.email,
    )


# ======================================================
# EMAIL : CANDIDATURE REFUSÉE
# ======================================================

def send_application_rejected_email(candidature):

    subject = "Décision concernant votre candidature"

    reason = candidature.admin_comment or "Votre dossier ne remplit pas les critères requis."

    context = {
        "title": "Décision concernant votre candidature",
        "first_name": candidature.first_name,
        "reason": reason,
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

    subject = "Votre dossier de candidature doit être complété"

    comment = candidature.admin_comment or "Veuillez vérifier les documents demandés."

    context = {
        "title": "Votre dossier doit être complété",
        "first_name": candidature.first_name,
        "comment": comment,
    }

    send_institutional_email(
        subject,
        "emails/admission_complete.html",
        context,
        candidature.email,
    )