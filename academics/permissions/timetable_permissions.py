from __future__ import annotations

from django.core.exceptions import PermissionDenied

from academics.permissions import GLOBAL_POSITIONS, is_global_academic_user, user_has_branch_scope
from accounts.access import get_user_position


TIMETABLE_SCOPED_POSITIONS = {"director_of_studies"}


def is_global_timetable_user(user) -> bool:
    return is_global_academic_user(user)


def can_manage_timetable(user, branch) -> bool:
    if not user or not user.is_authenticated:
        return False
    if is_global_timetable_user(user):
        return True
    if get_user_position(user) not in TIMETABLE_SCOPED_POSITIONS:
        return False
    return user_has_branch_scope(user, branch)


def can_publish_timetable(user, branch) -> bool:
    return can_manage_timetable(user, branch)


def can_archive_timetable(user, branch) -> bool:
    return can_manage_timetable(user, branch)


def require_timetable_access(user, branch):
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentification requise.")
    if is_global_timetable_user(user):
        return None
    position = get_user_position(user)
    if position not in TIMETABLE_SCOPED_POSITIONS:
        raise PermissionDenied("Acces reserve au pilotage du planning.")
    if branch is None:
        raise PermissionDenied("Aucune annexe n'est rattachee a ce compte.")
    if not user_has_branch_scope(user, branch):
        raise PermissionDenied("Acces refuse a cette annexe.")
    return branch

