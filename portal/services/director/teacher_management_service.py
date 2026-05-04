from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify

from academics.models import AcademicClass, EC
from accounts.dashboards.helpers import get_user_branch
from portal.models import DirectorTeacherAssignment
from portal.services.it_support_service import create_temp_password, log_support_action


@dataclass
class TeacherCreationResult:
    teacher: object
    username: str
    password: str
    assignments: list[DirectorTeacherAssignment]
    class_labels: list[str]
    ec_labels: list[str]
    email_sent: bool


def _generate_unique_username(*, first_name: str, last_name: str) -> str:
    User = get_user_model()
    base = slugify(f"{first_name}.{last_name}").replace("-", ".") or "teacher"
    candidate = base
    cursor = 1
    while User.objects.filter(username=candidate).exists():
        cursor += 1
        candidate = f"{base}{cursor}"
    return candidate


def _generate_employee_code(branch) -> str:
    branch_code = slugify(getattr(branch, "name", "")).upper().replace("-", "")[:4] or "ESFE"
    stamp = timezone.now().strftime("%y%m%d%H%M%S")
    return f"ENS-{branch_code}-{stamp}"


def _normalize_assignment_inputs(*, branch, class_ids, ec_ids):
    classes = list(
        AcademicClass.objects.filter(
            id__in=class_ids,
            is_active=True,
            branch=branch,
        ).select_related("programme", "branch")
    )
    ecs = list(
        EC.objects.filter(
            id__in=ec_ids,
            ue__semester__academic_class__branch=branch,
            ue__semester__academic_class__is_active=True,
        ).select_related("ue", "ue__semester", "ue__semester__academic_class")
    )
    if len(classes) != len(set(class_ids)):
        raise ValidationError("Une ou plusieurs classes sont hors annexe ou introuvables.")
    if len(ecs) != len(set(ec_ids)):
        raise ValidationError("Une ou plusieurs matieres sont hors annexe ou introuvables.")
    return classes, ecs


@transaction.atomic
def create_teacher_with_account(data, user) -> TeacherCreationResult:
    branch = get_user_branch(user)
    if branch is None:
        raise ValidationError("Aucune annexe n'est rattachee a ce compte directeur.")
    if getattr(getattr(user, "profile", None), "position", "") != "director_of_studies":
        raise ValidationError("Seul le Directeur des etudes peut creer un enseignant.")

    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    specialty = (data.get("specialty") or "").strip()
    class_ids = [int(value) for value in data.get("class_ids", []) if str(value).isdigit()]
    ec_ids = [int(value) for value in data.get("ec_ids", []) if str(value).isdigit()]

    if not first_name or not last_name or not email:
        raise ValidationError("Nom, prenom et email sont obligatoires.")

    User = get_user_model()
    if User.objects.filter(email__iexact=email).exists():
        raise ValidationError("Cet email est deja utilise par un autre compte.")

    classes, ecs = _normalize_assignment_inputs(branch=branch, class_ids=class_ids, ec_ids=ec_ids)
    username = _generate_unique_username(first_name=first_name, last_name=last_name)
    password = create_temp_password()

    teacher = User.objects.create_user(
        username=username,
        first_name=first_name,
        last_name=last_name,
        email=email,
        password=password,
        is_active=True,
    )
    profile = teacher.profile
    profile.role = "teacher"
    profile.user_type = "staff"
    profile.position = "teacher"
    profile.branch = branch
    profile.employee_code = _generate_employee_code(branch)
    profile.employment_status = "active"
    profile.hire_date = timezone.localdate()
    profile.main_domain = specialty
    profile.location = phone
    profile.save(
        update_fields=[
            "role",
            "user_type",
            "position",
            "branch",
            "employee_code",
            "employment_status",
            "hire_date",
            "main_domain",
            "location",
        ]
    )

    assignments = []
    class_labels = []
    ec_labels = []
    if classes or ecs:
        if classes and ecs:
            for academic_class in classes:
                for ec in ecs:
                    if ec.ue.semester.academic_class_id != academic_class.id:
                        continue
                    assignments.append(
                        DirectorTeacherAssignment.objects.create(
                            branch=branch,
                            teacher=teacher,
                            academic_class=academic_class,
                            ec=ec,
                            created_by=user,
                        )
                    )
        else:
            for academic_class in classes:
                assignments.append(
                    DirectorTeacherAssignment.objects.create(
                        branch=branch,
                        teacher=teacher,
                        academic_class=academic_class,
                        created_by=user,
                    )
                )
            for ec in ecs:
                assignments.append(
                    DirectorTeacherAssignment.objects.create(
                        branch=branch,
                        teacher=teacher,
                        academic_class=ec.ue.semester.academic_class,
                        ec=ec,
                        created_by=user,
                    )
                )

        class_labels = list(dict.fromkeys(item.academic_class.display_name for item in assignments if item.academic_class_id))
        ec_labels = list(dict.fromkeys(item.ec.title for item in assignments if item.ec_id))

    send_payload = (
        "Votre compte enseignant ESFE a ete cree.\n"
        f"Identifiant: {username}\n"
        f"Mot de passe temporaire: {password}\n"
        f"Annexe: {branch.name}\n"
    )
    email_sent = False
    try:
        email_sent = bool(
            send_mail(
                subject="Acces enseignant ESFE",
                message=send_payload,
                from_email=None,
                recipient_list=[email],
                fail_silently=True,
            )
        )
    except Exception:
        email_sent = False

    log_support_action(
        actor=user,
        branch=branch,
        action_type="account_activated",
        target_user=teacher,
        target_label=f"{teacher.get_full_name()} ({teacher.username})",
        details=f"Creation enseignant + affectations: classes={', '.join(class_labels) or '-'} ; matieres={', '.join(ec_labels) or '-'}",
    )

    return TeacherCreationResult(
        teacher=teacher,
        username=username,
        password=password,
        assignments=assignments,
        class_labels=class_labels,
        ec_labels=ec_labels,
        email_sent=email_sent,
    )


def generate_teacher_contract(teacher):
    branch = getattr(getattr(teacher, "profile", None), "branch", None)
    assignments = list(
        DirectorTeacherAssignment.objects.select_related("academic_class", "ec", "branch")
        .filter(teacher=teacher, is_active=True)
        .order_by("academic_class__level", "academic_class__id", "ec__title", "id")
    )
    class_labels = list(dict.fromkeys(item.academic_class.display_name for item in assignments if item.academic_class_id))
    ec_labels = list(dict.fromkeys(item.ec.title for item in assignments if item.ec_id))
    context = {
        "teacher": teacher,
        "branch": branch,
        "class_labels": class_labels,
        "ec_labels": ec_labels,
        "generated_at": timezone.now(),
        "contract_start": getattr(getattr(teacher, "profile", None), "hire_date", None) or timezone.localdate(),
        "contract_duration": "Annee academique en cours",
    }
    return render_to_string("portal/staff/director/teacher_contract.html", context), context


def generate_teacher_contract_pdf(teacher) -> bytes:
    html_string, _ = generate_teacher_contract(teacher)
    from weasyprint import HTML

    return HTML(string=html_string).write_pdf()
