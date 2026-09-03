from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.text import slugify

from accounts.models import Profile
from accounts.position_registry import get_position_definition
from accounts.services.institutional_access import compatibility_role_for_position
from core.emailing import get_email_branding_context, get_formatted_from_email
from portal.models import SupportAuditLog
from portal.services.it_support_service import reactivate_account, suspend_account


PROTECTED_EXECUTIVE_POSITIONS = {
    "executive_director",
    "deputy_executive_director",
    "super_admin",
}


def get_dg_staff_profile(profile_id, *, branch_ids=None):
    queryset = Profile.objects.select_related("user", "branch").filter(
        pk=profile_id,
        user_type="staff",
    )
    if branch_ids is not None:
        queryset = queryset.filter(Q(branch_id__in=branch_ids) | Q(branch__isnull=True))
    return queryset.first()


def _locked_staff_profile(profile_id):
    return (
        Profile.objects.select_for_update()
        .select_related("user", "branch")
        .filter(pk=profile_id, user_type="staff")
        .first()
    )


def _assert_dg_can_manage_staff(*, actor, profile):
    if profile is None:
        raise ValidationError("Membre du personnel introuvable.")
    if profile.user_id == actor.id:
        raise ValidationError("Vous ne pouvez pas modifier votre propre accès depuis le dashboard DG.")
    if profile.position in PROTECTED_EXECUTIVE_POSITIONS:
        raise ValidationError("Cette fonction exécutive nécessite le circuit institutionnel dédié.")


def _staff_label(profile):
    return profile.user.get_full_name() or profile.user.username


@transaction.atomic
def apply_staff_lifecycle_action(*, actor, form, allowed_branch_ids=None):
    """Apply a DG-authorised staff decision without deleting institutional history."""

    data = form.cleaned_data
    action = data["action"]
    reason = (data.get("reason") or "").strip()
    profile = _locked_staff_profile(data["profile_id"])
    _assert_dg_can_manage_staff(actor=actor, profile=profile)
    if allowed_branch_ids is not None and profile.branch_id is not None and profile.branch_id not in allowed_branch_ids:
        raise ValidationError("Ce membre du personnel est hors du contexte DG actif.")
    target_user = profile.user
    previous_status = profile.employment_status
    previous_branch = profile.branch

    if action == "suspend":
        if profile.employment_status == "suspended" and not target_user.is_active:
            return {"ok": True, "message": f"{_staff_label(profile)} est déjà suspendu.", "close_modal": True}
        profile.employment_status = "suspended"
        profile.save(update_fields=["employment_status", "updated_at"])
        suspend_account(
            actor=actor,
            branch=profile.branch,
            target_user=target_user,
            reason=reason,
            audit_details=(
                f"Décision DG : statut RH {previous_status or 'non défini'} → suspendu. "
                f"Motif : {reason}"
            ),
        )
        return {"ok": True, "message": f"Accès suspendu pour {_staff_label(profile)}.", "close_modal": True}

    if action == "reactivate":
        if profile.employment_status == "active" and target_user.is_active:
            return {"ok": True, "message": f"{_staff_label(profile)} est déjà actif.", "close_modal": True}
        profile.employment_status = "active"
        profile.save(update_fields=["employment_status", "updated_at"])
        reactivate_account(
            actor=actor,
            branch=profile.branch,
            target_user=target_user,
            audit_details=(
                f"Décision DG : statut RH {previous_status or 'non défini'} → actif. "
                f"Motif : {reason or 'Réactivation autorisée par la Direction générale.'}"
            ),
        )
        return {"ok": True, "message": f"Accès réactivé pour {_staff_label(profile)}.", "close_modal": True}

    if action == "revoke":
        if profile.employment_status == "inactive" and not target_user.is_active:
            return {"ok": True, "message": f"{_staff_label(profile)} est déjà révoqué.", "close_modal": True}
        support_state = getattr(target_user, "support_state", None)
        if support_state and support_state.is_suspended:
            support_state.is_suspended = False
            support_state.updated_by = actor
            support_state.save(update_fields=["is_suspended", "updated_by", "updated_at"])
        profile.employment_status = "inactive"
        profile.save(update_fields=["employment_status", "updated_at"])
        target_user.is_active = False
        target_user.save(update_fields=["is_active"])
        SupportAuditLog.objects.create(
            branch=profile.branch,
            actor=actor,
            target_user=target_user,
            action_type=SupportAuditLog.ACTION_ACCOUNT_DEACTIVATED,
            target_label=_staff_label(profile),
            details=(
                f"Décision DG : affectation conservée, accès révoqué. "
                f"Statut RH {previous_status or 'non défini'} → inactif. Motif : {reason}"
            ),
        )
        return {"ok": True, "message": f"Accès révoqué pour {_staff_label(profile)} ; l'historique est conservé.", "close_modal": True}

    if action == "reassign":
        branch = data.get("branch")
        if allowed_branch_ids is not None and branch is not None and branch.id not in allowed_branch_ids:
            raise ValidationError("L'annexe de destination est hors du contexte DG actif.")
        definition = get_position_definition(profile.position)
        if definition and definition.branch_required and branch is None:
            raise ValidationError("Une annexe active est obligatoire pour cette fonction.")
        if branch == previous_branch:
            return {"ok": True, "message": "Cette affectation est déjà en place.", "close_modal": True}
        profile.branch = branch
        profile.save(update_fields=["branch", "updated_at"])
        SupportAuditLog.objects.create(
            branch=branch or previous_branch,
            actor=actor,
            target_user=target_user,
            action_type=SupportAuditLog.ACTION_STAFF_ASSIGNED,
            target_label=_staff_label(profile),
            details=(
                f"Décision DG : affectation {getattr(previous_branch, 'name', 'globale')} → "
                f"{getattr(branch, 'name', 'globale')}. Motif : {reason}"
            ),
        )
        return {"ok": True, "message": f"Affectation mise à jour pour {_staff_label(profile)}.", "close_modal": True}

    if action == "update_assignment":
        branch = data.get("branch")
        position = data.get("position")
        if allowed_branch_ids is not None and branch is not None and branch.id not in allowed_branch_ids:
            raise ValidationError("L'annexe de destination est hors du contexte DG actif.")
        if not get_position_definition(position) or position in PROTECTED_EXECUTIVE_POSITIONS:
            raise ValidationError("Ce rôle ne peut pas être attribué depuis le workflow RH courant.")

        previous_position = profile.position
        if position == previous_position and branch == previous_branch:
            return {"ok": True, "message": "Ce rôle et cette affectation sont déjà en place.", "close_modal": True}

        profile.position = position
        profile.role = compatibility_role_for_position(position)
        profile.branch = branch
        profile.save(update_fields=["position", "role", "branch", "updated_at"])
        SupportAuditLog.objects.create(
            branch=branch or previous_branch,
            actor=actor,
            target_user=target_user,
            action_type=SupportAuditLog.ACTION_STAFF_ASSIGNED,
            target_label=_staff_label(profile),
            details=(
                f"Décision DG : rôle {previous_position or 'non défini'} → {position}; "
                f"affectation {getattr(previous_branch, 'name', 'sans annexe')} → "
                f"{getattr(branch, 'name', 'sans annexe')}. Motif : {reason}"
            ),
        )
        return {
            "ok": True,
            "message": f"Rôle et affectation mis à jour pour {_staff_label(profile)}.",
            "close_modal": True,
        }

    raise ValidationError("Action RH DG inconnue.")


def _build_username(first_name, last_name):
    user_model = get_user_model()
    base = slugify(f"{first_name}.{last_name}") or "staff"
    username = base
    index = 1
    while user_model.objects.filter(username=username).exists():
        index += 1
        username = f"{base}{index}"
    return username


def _send_staff_activation_invitation(*, user, position, recipient, request):
    """Deliver the existing one-time password setup link with institution data."""

    activation_url = request.build_absolute_uri(
        reverse(
            "accounts_portal:dg_staff_activation",
            kwargs={
                "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
                "token": default_token_generator.make_token(user),
            },
        )
    )
    branding = get_email_branding_context()
    institution_name = branding["institution_name"]
    definition = get_position_definition(position)
    position_label = definition.label if definition else position
    recipient_name = user.get_full_name() or user.username
    send_mail(
        f"Activez votre accès {institution_name}",
        (
            f"Bonjour {recipient_name},\n\n"
            f"Votre compte {institution_name} a été créé pour le poste : {position_label}.\n\n"
            "Définissez votre mot de passe personnel depuis ce lien sécurisé à usage unique :\n"
            f"{activation_url}\n\n"
            f"Votre identifiant de connexion : {user.username}\n\n"
            "Ne partagez pas ce lien."
        ),
        get_formatted_from_email(),
        [recipient],
        fail_silently=False,
    )


def create_staff_from_recruitment(*, actor, form, request):
    """Create the authoritative record first; an SMTP failure cannot roll it back."""

    data = form.cleaned_data
    user_model = get_user_model()
    email = data.get("professional_email") or data.get("personal_email") or ""
    generate_access = bool(data.get("generate_access"))

    with transaction.atomic():
        user = user_model.objects.create_user(
            username=_build_username(data["first_name"], data["last_name"]),
            email=email,
            password=None,
            first_name=data["first_name"],
            last_name=data["last_name"],
            is_staff=True,
            is_active=generate_access,
        )
        profile, _created = Profile.objects.get_or_create(user=user)
        profile.role = form.profile_role()
        profile.user_type = "staff"
        profile.position = form.profile_position()
        profile.branch = data.get("branch")
        profile.phone = data.get("phone") or ""
        profile.salary_base = data.get("salary_base") or 0
        profile.teacher_hourly_rate = data.get("teacher_hourly_rate") or 0
        profile.employment_status = "active"
        profile.is_public = False
        profile.save(
            update_fields=[
                "role", "user_type", "position", "branch", "phone", "salary_base",
                "teacher_hourly_rate", "employment_status", "is_public", "updated_at",
            ]
        )
        SupportAuditLog.objects.create(
            branch=data.get("branch"),
            actor=actor,
            target_user=user,
            action_type=(SupportAuditLog.ACTION_ACCOUNT_ACTIVATED if generate_access else SupportAuditLog.ACTION_ACCOUNT_DEACTIVATED),
            target_label=user.get_full_name() or user.username,
            details=(
                "Dossier RH créé depuis le dashboard DG. Invitation de première connexion à remettre."
                if generate_access
                else "Dossier RH créé depuis le dashboard DG sans accès actif."
            ),
        )

    access_delivery = "not_requested"
    if generate_access:
        try:
            _send_staff_activation_invitation(
                user=user,
                position=profile.position,
                recipient=email,
                request=request,
            )
        except Exception:
            access_delivery = "activation_email_failed"
            SupportAuditLog.objects.create(
                branch=profile.branch,
                actor=actor,
                target_user=user,
                action_type=SupportAuditLog.ACTION_ACCOUNT_ACTIVATED,
                target_label=user.get_full_name() or user.username,
                details="Dossier RH créé ; l'envoi de l'invitation sécurisée est à relancer.",
            )
        else:
            access_delivery = "activation_email_sent"

    return {
        "user": user,
        "profile": profile,
        "ticket": None,
        "access_delivery": access_delivery,
        "access_delivery_label": (
            "Lien sécurisé de première connexion envoyé par email."
            if access_delivery == "activation_email_sent"
            else "Le compte est créé, mais l'invitation email n'a pas pu être envoyée. Relancez-la depuis l'administration."
            if access_delivery == "activation_email_failed"
            else "Aucun accès actif n'a été demandé ; le dossier RH a été créé."
        ),
    }
