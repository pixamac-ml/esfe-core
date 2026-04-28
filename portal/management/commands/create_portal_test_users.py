from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from accounts.models import Profile
from branches.models import Branch


class Command(BaseCommand):
    help = "Cree les utilisateurs de test pour les dashboards portail staff."

    DEFAULT_PASSWORD = "pass1234"

    USERS = (
        {
            "username": "directeur.etudes",
            "email": "directeur.etudes@esfe.local",
            "first_name": "Directeur",
            "last_name": "Etudes",
            "position": "director_of_studies",
            "role": "executive",
            "employee_code": "DIR-ETUDES-001",
        },
        {
            "username": "surveillant.general",
            "email": "surveillant.general@esfe.local",
            "first_name": "Surveillant",
            "last_name": "General",
            "position": "academic_supervisor",
            "role": "",
            "employee_code": "SURV-GEN-001",
        },
        {
            "username": "informaticien.portal",
            "email": "informaticien.portal@esfe.local",
            "first_name": "Support",
            "last_name": "Portal",
            "position": "it_support",
            "role": "",
            "employee_code": "IT-PORTAL-001",
        },
    )

    def handle(self, *args, **options):
        user_model = get_user_model()
        branch = Branch.objects.filter(is_active=True).order_by("name").first()
        if not branch:
            branch = Branch.objects.create(
                name="Annexe Portail Demo",
                code="APD",
                slug=slugify("Annexe Portail Demo"),
                city="Bamako",
                is_active=True,
            )
            self.stdout.write(self.style.SUCCESS(f"Annexe creee: {branch.name}"))

        self.stdout.write(f"Annexe utilisee: {branch.name} ({branch.code})")

        for item in self.USERS:
            user, created = user_model.objects.get_or_create(
                username=item["username"],
                defaults={
                    "email": item["email"],
                    "first_name": item["first_name"],
                    "last_name": item["last_name"],
                    "is_staff": True,
                    "is_active": True,
                },
            )
            if created or not user.check_password(self.DEFAULT_PASSWORD):
                user.set_password(self.DEFAULT_PASSWORD)
            user.email = item["email"]
            user.first_name = item["first_name"]
            user.last_name = item["last_name"]
            user.is_staff = True
            user.is_active = True
            user.save()

            profile, _ = Profile.objects.get_or_create(user=user)
            profile.role = item["role"]
            profile.user_type = "staff"
            profile.position = item["position"]
            profile.branch = branch
            profile.employee_code = item["employee_code"]
            profile.employment_status = "active"
            profile.is_public = False
            profile.save(
                update_fields=[
                    "role",
                    "user_type",
                    "position",
                    "branch",
                    "employee_code",
                    "employment_status",
                    "is_public",
                    "updated_at",
                ]
            )

            verb = "cree" if created else "mis a jour"
            self.stdout.write(
                self.style.SUCCESS(
                    f"{verb}: {user.username} / {self.DEFAULT_PASSWORD} / {profile.position}"
                )
            )
