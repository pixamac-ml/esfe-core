"""Shared staff account drawer context.

Generalizes the Director of Studies account panel (profile / edit /
security / preferences) so every certified staff dashboard reuses the same
experience without leaving its workspace.
"""

from django.urls import reverse
from django.utils import timezone

from accounts.access import get_user_position
from accounts.models import Profile


def build_staff_account_context(request, *, panel_url_name, drawer_content_target):
    """Build the context consumed by the shared account drawer partials."""

    profile, _ = Profile.objects.get_or_create(user=request.user)
    position = get_user_position(request.user)
    position_label = dict(Profile.POSITION_CHOICES).get(profile.position, profile.position or "")
    role_label = dict(Profile.ROLE_CHOICES).get(profile.role, profile.role or "")
    status_label = dict(Profile.EMPLOYMENT_STATUS_CHOICES).get(
        profile.employment_status, profile.employment_status or ""
    )
    extra_fields = []
    if profile.employee_code:
        extra_fields.append({"label": "Code employe", "value": profile.employee_code})
    if profile.location:
        extra_fields.append({"label": "Localisation", "value": profile.location})
    if profile.main_domain:
        extra_fields.append({"label": "Domaine", "value": profile.main_domain})
    if profile.website:
        extra_fields.append({"label": "Site web", "value": profile.website})
    if position_label:
        extra_fields.append({"label": "Fonction", "value": position_label})
    if role_label:
        extra_fields.append({"label": "Groupe", "value": role_label})

    panel_url = reverse(panel_url_name)
    account_actions = [
        {
            "label": "Modifier",
            "icon": "pencil",
            "hx_get": f"{panel_url}?view=edit",
            "hx_target": drawer_content_target,
            "hx_swap": "innerHTML",
        },
        {
            "label": "Securite",
            "icon": "shield",
            "hx_get": f"{panel_url}?view=security",
            "hx_target": drawer_content_target,
            "hx_swap": "innerHTML",
        },
        {
            "label": "Preferences",
            "icon": "settings",
            "hx_get": f"{panel_url}?view=preferences",
            "hx_target": drawer_content_target,
            "hx_swap": "innerHTML",
        },
    ]
    return {
        "profile": profile,
        "display_name": request.user.get_full_name() or request.user.username,
        "avatar_url": profile.avatar_url,
        "email": request.user.email,
        "role": position_label or role_label or "Compte institutionnel",
        "branch": profile.branch.name if profile.branch else "Annexe non definie",
        "status": profile.employment_status,
        "status_label": status_label or "Actif",
        "phone": profile.phone,
        "address": profile.address,
        "created_at": (
            timezone.localtime(profile.created_at).strftime("%d/%m/%Y")
            if profile.created_at
            else ""
        ),
        "last_seen": (
            timezone.localtime(profile.last_seen).strftime("%d/%m/%Y %H:%M")
            if profile.last_seen
            else ""
        ),
        "bio": profile.bio,
        "extra_fields": extra_fields,
        "account_actions": account_actions,
        "is_system_account": bool(position),
    }
