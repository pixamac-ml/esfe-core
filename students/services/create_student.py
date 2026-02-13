import secrets
from django.contrib.auth import get_user_model
from django.db import transaction
from students.models import Student

User = get_user_model()


def create_student_after_first_payment(inscription):
    candidature = inscription.candidature
    username = f"etu_esfe{inscription.id}"

    with transaction.atomic():

        existing_student = Student.objects.filter(inscription=inscription).first()
        if existing_student:
            return None

        user = User.objects.filter(username=username).first()

        raw_password = None

        if not user:
            raw_password = secrets.token_urlsafe(8)
            user = User.objects.create_user(
                username=username,
                email=candidature.email,
                password=raw_password,
                first_name=candidature.first_name,
                last_name=candidature.last_name,
            )

        student = Student.objects.create(
            user=user,
            inscription=inscription,
            matricule=f"ESFE-{inscription.id:05d}"
        )

    return {
        "student": student,
        "password": raw_password,
    }
