from django.conf import settings

from notifier.services import NotificationBus


def send_student_credentials_email(*, student, raw_password=None):
    user = student.user
    inscription = student.inscription
    candidature = inscription.candidature

    subject = "🎓 Bienvenue à l’ESFE – Vos accès étudiants"

    context = {
        "student": {
            "id": student.pk,
            "matricule": student.matricule,
        },
        "user": {
            "id": user.pk,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
        },
        "needs_password_reset": True,
        "password": raw_password,
        "temporary_password": raw_password,
        "username": user.username,
        "student_name": f"{user.first_name} {user.last_name}".strip(),
        "candidate_name": candidature.full_name,
        "recipient_name": candidature.full_name,
        "first_name": candidature.first_name,
        "public_link": inscription.get_public_url(),
        "login_url": settings.STUDENT_LOGIN_URL,
        "reference": inscription.public_token,
        "academic_year": candidature.academic_year,
        "programme": candidature.programme.title,
        "branch_name": getattr(candidature.branch, "name", ""),
        "inscription": {
            "id": inscription.pk,
            "candidature": {
                "programme": {
                    "title": candidature.programme.title,
                    "cycle": {
                        "title": getattr(candidature.programme.cycle, "title", ""),
                    },
                },
                "entry_year": candidature.entry_year,
            },
        },
    }

    NotificationBus.send_email(
        subject=subject,
        recipient=user,
        recipient_email=user.email,
        source_app="students",
        event_type="student_welcome_credentials",
        template_key="student_welcome_credentials",
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
        "payment": {
            "id": payment.pk,
            "reference": payment.reference,
            "amount": payment.amount,
            "receipt_number": payment.receipt_number,
        },
        "inscription": {
            "id": inscription.pk,
            "public_token": inscription.public_token,
        },
        "candidature": {
            "first_name": candidature.first_name,
            "last_name": candidature.last_name,
            "email": candidature.email,
        },
        "student": {
            "id": getattr(student, "pk", None),
            "matricule": getattr(student, "matricule", ""),
        } if student else None,
        "recipient_first_name": candidature.first_name,
        "candidate_name": candidature.full_name,
        "student_name": getattr(getattr(student, "user", None), "get_full_name", lambda: "")(),
        "payment_amount": payment.amount,
        "amount_due": inscription.amount_due,
        "amount_paid": inscription.amount_paid,
        "balance": inscription.balance,
        "public_link": inscription.get_public_url(),
        "reference": payment.reference or payment.pk,
        "academic_year": candidature.academic_year,
        "branch_name": getattr(candidature.branch, "name", ""),
    }

    NotificationBus.send_email(
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
