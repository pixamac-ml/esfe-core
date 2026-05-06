from django.conf import settings

from communication.services import EmailService


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

    EmailService.send_transactional(
        subject=subject,
        recipient=user,
        recipient_email=user.email,
        source_app="students",
        event_type="student_welcome_credentials",
        html_template="emails/student_welcome.html",
        text_template="emails/student_welcome.txt",
        context=context,
        dispatch_on_commit=False,
        legacy_source="students.send_student_credentials_email",
        legacy_object_id=getattr(student, "pk", ""),
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

    EmailService.send_transactional(
        subject=subject,
        recipient=getattr(student, "user", None),
        recipient_email=candidature.email,
        source_app="payments",
        event_type="payment_confirmation",
        html_template="emails/payment_confirmation.html",
        text_template="emails/payment_confirmation.txt",
        context=context,
        dispatch_on_commit=False,
        legacy_source="students.send_payment_confirmation_email",
        legacy_object_id=getattr(payment, "pk", ""),
    )
