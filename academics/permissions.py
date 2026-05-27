from accounts.access import get_user_annexe, get_user_position


GLOBAL_POSITIONS = {"super_admin", "executive_director", "deputy_executive_director"}
REPORT_POSITIONS = GLOBAL_POSITIONS | {"director_of_studies", "academic_supervisor", "it_support"}
IMPORT_POSITIONS = GLOBAL_POSITIONS | {"director_of_studies", "it_support"}
BULLETIN_MANAGEMENT_POSITIONS = {"super_admin", "director_of_studies"}
DIPLOMA_MANAGEMENT_POSITIONS = {"executive_director", "deputy_executive_director"}


def is_global_academic_user(user):
    if not user or not user.is_authenticated:
        return False
    return bool(user.is_superuser or get_user_position(user) in GLOBAL_POSITIONS)


def user_has_branch_scope(user, branch):
    if is_global_academic_user(user):
        return True
    user_branch = get_user_annexe(user)
    return bool(user_branch and branch and user_branch.pk == branch.pk)


def can_view_academic_class(user, academic_class):
    if not user or not user.is_authenticated:
        return False
    if is_global_academic_user(user):
        return True
    position = get_user_position(user)
    if position in REPORT_POSITIONS and user_has_branch_scope(user, academic_class.branch):
        return True
    student_profile = getattr(user, "student_profile", None)
    if student_profile:
        return user.academic_enrollments.filter(academic_class=academic_class, is_active=True).exists()
    return False


def can_view_student_academic_report(user, student, academic_class=None, academic_year=None):
    if not user or not user.is_authenticated or not student:
        return False
    if getattr(student, "user_id", None) == user.pk:
        return True
    if is_global_academic_user(user):
        return True
    position = get_user_position(user)
    if position not in REPORT_POSITIONS:
        return False
    branch = None
    if academic_class is not None:
        branch = academic_class.branch
    elif academic_year is not None:
        enrollment = student.user.academic_enrollments.filter(academic_year=academic_year).select_related("branch").first()
        branch = enrollment.branch if enrollment else None
    if branch is None:
        branch = getattr(getattr(student.inscription, "candidature", None), "branch", None)
    return user_has_branch_scope(user, branch)


def can_import_grades_for_class(user, academic_class):
    if not user or not user.is_authenticated:
        return False
    if is_global_academic_user(user):
        return True
    position = get_user_position(user)
    return bool(position in IMPORT_POSITIONS and user_has_branch_scope(user, academic_class.branch))


def can_manage_bulletins(user, academic_class):
    if not user or not user.is_authenticated:
        return False
    position = get_user_position(user)
    if user.is_superuser or position == "super_admin":
        return True
    return bool(position in BULLETIN_MANAGEMENT_POSITIONS and user_has_branch_scope(user, academic_class.branch))


def can_manage_diplomas(user, academic_class):
    if not user or not user.is_authenticated:
        return False
    position = get_user_position(user)
    return bool(position in DIPLOMA_MANAGEMENT_POSITIONS)


def can_manage_academic_documents(user, academic_class):
    return can_manage_bulletins(user, academic_class) or can_manage_diplomas(user, academic_class)
