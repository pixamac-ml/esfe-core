from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string


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
    }

    message = render_to_string("emails/student_welcome.txt", context)
    html_message = render_to_string("emails/student_welcome.html", context)

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
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
        "amount_due": inscription.amount_due,
        "amount_paid": inscription.amount_paid,
        "balance": inscription.balance,
        "public_link": inscription.get_public_url(),
    }

    message = render_to_string(
        "emails/payment_confirmation.txt",
        context
    )

    html_message = render_to_string(
        "emails/payment_confirmation.html",
        context
    )

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[candidature.email],
        html_message=html_message,
        fail_silently=False,
    )
