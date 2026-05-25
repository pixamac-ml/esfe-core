GLOBAL_CYCLE_POSITIONS = {"super_admin", "executive_director", "deputy_executive_director"}
CLOSURE_POSITIONS = GLOBAL_CYCLE_POSITIONS | {"director_of_studies"}
CORRECTION_POSITIONS = GLOBAL_CYCLE_POSITIONS | {"it_support", "director_of_studies"}
MANAGER_POSITIONS = GLOBAL_CYCLE_POSITIONS | {"branch_manager", "finance_manager", "payment_agent"}


def get_profile(user):
    return getattr(user, "profile", None)


def is_global_cycle_user(user):
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = get_profile(user)
    return bool(profile and profile.position in GLOBAL_CYCLE_POSITIONS)


def user_branch(user):
    profile = get_profile(user)
    return getattr(profile, "branch", None)


def has_branch_scope(user, branch):
    if is_global_cycle_user(user):
        return True
    scoped_branch = user_branch(user)
    return bool(scoped_branch and branch and scoped_branch.pk == branch.pk)


def can_close_branch_cycle(user, branch_cycle):
    if not user or not user.is_authenticated:
        return False
    if is_global_cycle_user(user):
        return True
    profile = get_profile(user)
    return bool(profile and profile.position in CLOSURE_POSITIONS and has_branch_scope(user, branch_cycle.branch))


def can_handle_correction(user, correction):
    if not user or not user.is_authenticated:
        return False
    if is_global_cycle_user(user):
        return True
    profile = get_profile(user)
    return bool(profile and profile.position in CORRECTION_POSITIONS and has_branch_scope(user, correction.branch))


def can_manage_reenrollment(user, branch):
    if not user or not user.is_authenticated:
        return False
    if is_global_cycle_user(user):
        return True
    profile = get_profile(user)
    return bool(profile and profile.position in MANAGER_POSITIONS and has_branch_scope(user, branch))
