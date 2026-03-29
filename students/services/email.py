from django.conf import settings

from core.emailing import send_templated_email


def send_student_credentials_email(*, student, raw_password):
    user = student.user
    inscription = student.inscription

    subject = "🎓 Bienvenue à l’ESFE – Vos accès étudiants"

    context = {
        "student": student,
        "user": user,
        "password": raw_password,
        "public_link": inscription.get_public_url(),
        "login_url": settings.STUDENT_LOGIN_URL,
        "reference": inscription.public_token,
    }

    send_templated_email(
        subject=subject,
        recipient=user.email,
        text_template="emails/student_welcome.txt",
        html_template="emails/student_welcome.html",
        context=context,
        fail_silently=False,
    )


def send_payment_confirmation_email(*, payment):
    """
    Email envoyé pour chaque paiement validé
    après le premier.
    """

    inscription = payment.inscription
    candidature = inscription.candidature
    student = getattr(inscription, "student", None)

    subject = "💳 Confirmation de paiement – ESFE"

    context = {
        "payment": payment,
        "inscription": inscription,
        "candidature": candidature,
        "student": student,
        "recipient_first_name": candidature.first_name,
        "amount_due": inscription.amount_due,
        "amount_paid": inscription.amount_paid,
        "balance": inscription.balance,
        "public_link": inscription.get_public_url(),
        "reference": payment.reference or payment.pk,
    }

    send_templated_email(
        subject=subject,
        recipient=candidature.email,
        text_template="emails/payment_confirmation.txt",
        html_template="emails/payment_confirmation.html",
        context=context,
        fail_silently=False,
    )
