from django.core.exceptions import PermissionDenied


def is_secretary(user):
    if not getattr(user, "is_authenticated", False):
        return False

    if getattr(user, "is_superuser", False):
        return True

    explicit_role = getattr(user, "role", None)
    if explicit_role == "secretary":
        return True

    profile = getattr(user, "profile", None)
    profile_role = getattr(profile, "role", None)
    if profile_role in {"secretary", "admissions"}:
        return True

    groups = set(user.groups.values_list("name", flat=True))
    return bool({"secretary", "secretaries", "admissions", "admissions_managers"} & groups)


def ensure_secretary_access(user):
    if not is_secretary(user):
        raise PermissionDenied("Acces reserve au secretariat.")
