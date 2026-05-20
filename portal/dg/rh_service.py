from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils.crypto import get_random_string
from django.utils.text import slugify

from accounts.models import Profile
from portal.models import SupportAuditLog, SupportTicket


def _build_username(first_name, last_name):
    user_model = get_user_model()
    base = slugify(f"{first_name}.{last_name}") or "staff"
    username = base
    index = 1
    while user_model.objects.filter(username=username).exists():
        index += 1
        username = f"{base}{index}"
    return username


def create_staff_from_recruitment(*, actor, form):
    data = form.cleaned_data
    user_model = get_user_model()
    temporary_password = get_random_string(12)
    email = data.get("professional_email") or data.get("personal_email") or ""

    user = user_model.objects.create_user(
        username=_build_username(data["first_name"], data["last_name"]),
        email=email,
        password=temporary_password,
        first_name=data["first_name"],
        last_name=data["last_name"],
        is_staff=True,
        is_active=True,
    )

    profile, _created = Profile.objects.get_or_create(user=user)
    profile.role = form.profile_role()
    profile.user_type = "staff"
    profile.position = form.profile_position()
    profile.branch = data.get("branch")
    profile.phone = data.get("phone") or ""
    profile.salary_base = data.get("salary_base") or 0
    profile.employment_status = "active"
    profile.is_public = False
    profile.save(
        update_fields=[
            "role",
            "user_type",
            "position",
            "branch",
            "phone",
            "salary_base",
            "employment_status",
            "is_public",
            "updated_at",
        ]
    )

    ticket = None
    if data["position"] == "other":
        ticket = SupportTicket.objects.create(
            branch=data.get("branch"),
            title=f"Besoin metier DG - {data['first_name']} {data['last_name']}",
            description=(
                f"Description metier:\n{data.get('business_description')}\n\n"
                f"Responsabilites:\n{data.get('responsibilities')}\n\n"
                f"Dashboard souhaite:\n{data.get('expected_dashboard')}\n\n"
                f"Permissions necessaires:\n{data.get('required_permissions')}\n\n"
                f"Annexes concernees:\n{data.get('concerned_branches')}"
            ),
            category=SupportTicket.CATEGORY_ACCOUNT,
            priority=SupportTicket.PRIORITY_HIGH,
            requester_user=actor,
            created_by=actor,
        )

    SupportAuditLog.objects.create(
        branch=data.get("branch"),
        actor=actor,
        target_user=user,
        action_type=SupportAuditLog.ACTION_ACCOUNT_ACTIVATED,
        target_label=user.get_full_name() or user.username,
        details="Compte staff cree depuis le dashboard DG.",
    )

    if data.get("send_access_email") and email:
        send_mail(
            "Acces ESFE",
            (
                f"Bonjour {user.get_full_name() or user.username},\n\n"
                f"Votre compte ESFE a ete cree.\n"
                f"Identifiant: {user.username}\n"
                f"Mot de passe temporaire: {temporary_password}\n\n"
                "Merci de changer ce mot de passe apres connexion."
            ),
            None,
            [email],
            fail_silently=True,
        )

    return {
        "user": user,
        "profile": profile,
        "temporary_password": temporary_password,
        "ticket": ticket,
    }

