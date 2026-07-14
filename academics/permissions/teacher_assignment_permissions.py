from django.core.exceptions import PermissionDenied

from accounts.access import get_user_annexe, get_user_position


GLOBAL_TEACHER_ASSIGNMENT_POSITIONS = {"super_admin", "executive_director", "deputy_executive_director"}
SCOPED_TEACHER_ASSIGNMENT_POSITIONS = {"director_of_studies"}


def is_global_teacher_assignment_user(user):
    if not user or not user.is_authenticated:
        return False
    return bool(user.is_superuser or get_user_position(user) in GLOBAL_TEACHER_ASSIGNMENT_POSITIONS)


def can_manage_teacher_assignments(user, branch):
    if not user or not user.is_authenticated or branch is None:
        return False
    if is_global_teacher_assignment_user(user):
        return True
    if get_user_position(user) not in SCOPED_TEACHER_ASSIGNMENT_POSITIONS:
        return False
    user_branch = get_user_annexe(user)
    return bool(user_branch and user_branch.pk == branch.pk)


def require_teacher_assignment_access(user, branch):
    if not can_manage_teacher_assignments(user, branch):
        raise PermissionDenied("Acces refuse a la gestion des affectations de cette annexe.")
    return True
