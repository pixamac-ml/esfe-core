"""Registre fermé des positions institutionnelles ESFE."""

from dataclasses import dataclass


STUDENT = "student"
TEACHER = "teacher"
ANNEX_MANAGER = "annex_manager"

CATEGORY_STUDENT = "STUDENT"
CATEGORY_TEACHING = "TEACHING_STAFF"
CATEGORY_ADMIN = "ADMIN_STAFF"

SCOPE_BRANCH = "BRANCH"
SCOPE_GLOBAL = "GLOBAL"


@dataclass(frozen=True)
class PositionDefinition:
    code: str
    label: str
    category: str
    scope: str
    dashboard_url_name: str
    default_group: str
    branch_required: bool


POSITION_REGISTRY = {
    STUDENT: PositionDefinition(STUDENT, "Étudiant", CATEGORY_STUDENT, SCOPE_BRANCH, "accounts_portal:portal_student", "student", True),
    TEACHER: PositionDefinition(TEACHER, "Enseignant", CATEGORY_TEACHING, SCOPE_BRANCH, "accounts_portal:portal_teacher", "teacher", True),
    ANNEX_MANAGER: PositionDefinition(ANNEX_MANAGER, "Gestionnaire d'annexe", CATEGORY_ADMIN, SCOPE_BRANCH, "accounts_portal:portal_annex_manager", "annex_manager", True),
    "finance_manager": PositionDefinition("finance_manager", "Responsable finance", CATEGORY_ADMIN, SCOPE_BRANCH, "accounts_portal:portal_finance", "finance_manager", True),
    "payment_agent": PositionDefinition("payment_agent", "Agent de paiement", CATEGORY_ADMIN, SCOPE_BRANCH, "accounts_portal:portal_finance", "payment_agent", True),
    "secretary": PositionDefinition("secretary", "Secrétaire", CATEGORY_ADMIN, SCOPE_BRANCH, "accounts_portal:portal_secretary", "secretary", True),
    "admissions": PositionDefinition("admissions", "Agent des admissions", CATEGORY_ADMIN, SCOPE_BRANCH, "accounts_portal:portal_admissions", "admissions", True),
    "academic_supervisor": PositionDefinition("academic_supervisor", "Surveillant général", CATEGORY_ADMIN, SCOPE_BRANCH, "accounts_portal:portal_dashboard", "academic_supervisor", True),
    "it_support": PositionDefinition("it_support", "Informaticien", CATEGORY_ADMIN, SCOPE_BRANCH, "accounts_portal:portal_it_v2", "it_support", True),
    "director_of_studies": PositionDefinition("director_of_studies", "Directeur des études", CATEGORY_ADMIN, SCOPE_BRANCH, "accounts_portal:portal_director", "director_of_studies", True),
    "marketing_manager": PositionDefinition("marketing_manager", "Responsable marketing", CATEGORY_ADMIN, SCOPE_GLOBAL, "marketing:dashboard", "marketing_manager", False),
    "executive_director": PositionDefinition("executive_director", "Directeur général", CATEGORY_ADMIN, SCOPE_GLOBAL, "accounts_portal:portal_dg", "executive_director", False),
    "deputy_executive_director": PositionDefinition("deputy_executive_director", "Directeur général adjoint", CATEGORY_ADMIN, SCOPE_GLOBAL, "accounts_portal:portal_dg", "deputy_executive_director", False),
    "super_admin": PositionDefinition("super_admin", "Super administrateur", CATEGORY_ADMIN, SCOPE_GLOBAL, "superadmin:dashboard", "super_admin", False),
}

LEGACY_POSITION_ALIASES = {
    "branch_manager": ANNEX_MANAGER,
}


def normalize_position(position):
    normalized = str(position or "").strip().lower()
    return LEGACY_POSITION_ALIASES.get(normalized, normalized)


def get_position_definition(position):
    return POSITION_REGISTRY.get(normalize_position(position))
