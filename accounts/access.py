"""Couche centrale de compatibilité pour les accès ESFé.

Objectifs :
- centraliser la lecture des groupes Django et de ``profile.role``
- normaliser vers des rôles canoniques
- conserver les comportements legacy via des wrappers progressifs
- fournir un scope annexe unique pour les nouvelles vues
"""

from __future__ import annotations

import logging

from branches.models import Branch
from payments.models import PaymentAgent


logger = logging.getLogger(__name__)


PROFILE_ROLE_TO_CANONICAL = {
	"student": "student",
	"teacher": "teacher",
	"admissions": "staff_admin",
	"finance": "staff_admin",
	"executive": "directeur_etudes",
	"superadmin": "super_admin",
}

GROUP_COMPAT_CLUSTERS = (
	("admissions_managers", "admissions"),
	("finance_agents", "finance"),
	("executive_director", "executive"),
	("gestionnaire", "manager"),
)

GROUP_TO_CANONICAL = {
	"admissions_managers": "staff_admin",
	"admissions": "staff_admin",
	"finance_agents": "staff_admin",
	"finance": "staff_admin",
	"gestionnaire": "staff_admin",
	"manager": "staff_admin",
	"executive_director": "directeur_etudes",
	"executive": "directeur_etudes",
}

ACCESS_RULES = {
	("view_dashboard", "admissions"): {
		"groups": {"admissions_managers", "admissions"},
		"profile_roles": {"admissions"},
		"canonical_roles": set(),
		"allow_global": True,
	},
	("view_dashboard", "finance"): {
		"groups": {"finance_agents", "finance"},
		"profile_roles": {"finance"},
		"canonical_roles": set(),
		"allow_global": True,
	},
	("view_dashboard", "executive"): {
		"groups": {"executive_director", "executive"},
		"profile_roles": {"executive", "superadmin"},
		"canonical_roles": {"directeur_etudes", "super_admin"},
		"allow_global": True,
	},
	("view_dashboard", "manager"): {
		"groups": {"gestionnaire", "manager"},
		"profile_roles": set(),
		"canonical_roles": set(),
		"allow_global": False,
	},
	("view_portal", "student"): {
		"groups": set(),
		"profile_roles": {"student"},
		"canonical_roles": {"student"},
		"allow_global": False,
	},
	("view_portal", "teacher"): {
		"groups": set(),
		"profile_roles": {"teacher"},
		"canonical_roles": {"teacher"},
		"allow_global": False,
	},
	("view_portal", "staff"): {
		"groups": {
			"admissions_managers",
			"admissions",
			"finance_agents",
			"finance",
			"gestionnaire",
			"manager",
			"executive_director",
			"executive",
		},
		"profile_roles": {"admissions", "finance", "executive", "superadmin"},
		"canonical_roles": {"staff_admin", "directeur_etudes", "super_admin"},
		"allow_global": True,
	},
	("view_portal", "dashboard"): {
		"groups": set(),
		"profile_roles": {"superadmin"},
		"canonical_roles": {"super_admin"},
		"allow_global": False,
	},
}


def _is_authenticated(user):
	return bool(user and getattr(user, "is_authenticated", False))


def _normalize_token(value):
	if value is None:
		return None
	return str(value).strip().lower() or None


def _get_profile(user):
	if not _is_authenticated(user):
		return None

	try:
		return user.profile
	except Exception:
		return None


def _get_raw_group_names(user):
	if not _is_authenticated(user):
		return set()

	return {
		_normalize_token(name)
		for name in user.groups.values_list("name", flat=True)
		if _normalize_token(name)
	}


def _is_global_user(user, *, profile_role=None, groups=None, canonical_role=None):
	if not _is_authenticated(user):
		return False

	profile_role = profile_role if profile_role is not None else get_user_profile_role(user)
	groups = set(groups) if groups is not None else set(get_user_groups(user))
	canonical_role = canonical_role if canonical_role is not None else get_user_role(user)

	return bool(
		user.is_superuser
		or profile_role in {"executive", "superadmin"}
		or "executive_director" in groups
		or canonical_role in {"directeur_etudes", "super_admin"}
	)


def get_user_profile_role(user):
	"""Retourne le rôle brut porté par ``profile.role`` si disponible."""

	profile = _get_profile(user)
	role = _normalize_token(getattr(profile, "role", None))

	if _is_authenticated(user):
		logger.debug(
			"Profil rôle détecté pour %s: %s",
			getattr(user, "username", "anonymous"),
			role,
		)

	return role


def get_user_groups(user):
	"""Retourne les groupes utilisateur avec expansion des alias legacy."""

	groups = _get_raw_group_names(user)
	expanded_groups = set(groups)

	for cluster in GROUP_COMPAT_CLUSTERS:
		if groups.intersection(cluster):
			expanded_groups.update(cluster)

	if _is_authenticated(user) and getattr(user, "is_superuser", False):
		expanded_groups.add("superuser")

	ordered_groups = tuple(sorted(expanded_groups))

	if _is_authenticated(user):
		logger.debug(
			"Groupes détectés pour %s: %s",
			getattr(user, "username", "anonymous"),
			", ".join(ordered_groups) or "aucun",
		)

	return ordered_groups


def get_user_position(user):
	"""Retourne une position métier dérivée si elle peut être inférée."""

	if not _is_authenticated(user):
		return None

	if user.is_superuser:
		position = "super_admin"
	elif Branch.objects.filter(manager=user).exists():
		position = "branch_manager"
	elif PaymentAgent.objects.filter(user=user).exists():
		position = "payment_agent"
	elif "executive_director" in get_user_groups(user):
		position = "executive_director"
	else:
		position = None

	logger.debug(
		"Position détectée pour %s: %s",
		getattr(user, "username", "anonymous"),
		position,
	)

	return position


def get_user_role(user):
	"""Retourne le rôle canonique de l'utilisateur sans casser l'existant."""

	if not _is_authenticated(user):
		return None

	profile_role = get_user_profile_role(user)
	groups = set(get_user_groups(user))
	position = get_user_position(user)

	role = None

	if user.is_superuser:
		role = "super_admin"
	elif profile_role in PROFILE_ROLE_TO_CANONICAL:
		role = PROFILE_ROLE_TO_CANONICAL[profile_role]
	else:
		for group_name in sorted(groups):
			if group_name in GROUP_TO_CANONICAL:
				role = GROUP_TO_CANONICAL[group_name]
				break

	if role is None and position in {"branch_manager", "payment_agent"}:
		role = "staff_admin"

	if role is None and getattr(user, "is_staff", False) and groups:
		role = "staff_admin"

	logger.debug(
		"Rôle canonique détecté pour %s: %s (profile_role=%s, position=%s)",
		getattr(user, "username", "anonymous"),
		role,
		profile_role,
		position,
	)

	return role


def get_user_annexe(user):
	"""Retourne l'annexe active détectée pour l'utilisateur."""

	if not _is_authenticated(user):
		return None

	if user.is_superuser:
		logger.debug("Annexe détectée pour %s: aucune (superuser/global)", user.username)
		return None

	profile = _get_profile(user)
	profile_branch = getattr(profile, "branch", None)
	if profile_branch:
		logger.debug(
			"Annexe détectée pour %s via profile.branch: %s",
			user.username,
			profile_branch,
		)
		return profile_branch

	payment_agent = (
		PaymentAgent.objects
		.select_related("branch")
		.filter(user=user)
		.first()
	)
	if payment_agent and payment_agent.branch:
		logger.debug(
			"Annexe détectée pour %s via PaymentAgent.branch: %s",
			user.username,
			payment_agent.branch,
		)
		return payment_agent.branch

	managed_branch = Branch.objects.filter(manager=user).first()
	if managed_branch:
		logger.debug(
			"Annexe détectée pour %s via Branch.manager: %s",
			user.username,
			managed_branch,
		)
		return managed_branch

	logger.debug("Annexe détectée pour %s: aucune", user.username)
	return None


def get_user_scope(user):
	"""Retourne le scope d'accès unifié des nouvelles vues."""

	profile_role = get_user_profile_role(user)
	groups = get_user_groups(user)
	canonical_role = get_user_role(user)
	position = get_user_position(user)
	branch = get_user_annexe(user)
	is_global = _is_global_user(
		user,
		profile_role=profile_role,
		groups=groups,
		canonical_role=canonical_role,
	)

	scope = {
		"branch": branch,
		"annexe": branch,
		"is_global": is_global,
		"role": canonical_role,
		"profile_role": profile_role,
		"groups": groups,
		"position": position,
	}

	if _is_authenticated(user):
		logger.debug(
			"Scope détecté pour %s: role=%s, profile_role=%s, position=%s, is_global=%s, branch=%s",
			getattr(user, "username", "anonymous"),
			canonical_role,
			profile_role,
			position,
			is_global,
			branch,
		)

	return scope


def can_access(user, action, resource=None):
	"""Décide si l'utilisateur peut accéder à une action/ressource donnée."""

	action_key = _normalize_token(action)
	resource_key = _normalize_token(resource)

	if not _is_authenticated(user):
		logger.warning(
			"Accès refusé (non authentifié): action=%s, resource=%s",
			action_key,
			resource_key,
		)
		return False

	groups = set(get_user_groups(user))
	profile_role = get_user_profile_role(user)
	canonical_role = get_user_role(user)
	is_global = _is_global_user(
		user,
		profile_role=profile_role,
		groups=groups,
		canonical_role=canonical_role,
	)

	if user.is_superuser:
		logger.debug(
			"Accès accordé (superuser): user=%s, action=%s, resource=%s",
			user.username,
			action_key,
			resource_key,
		)
		return True

	rule = ACCESS_RULES.get((action_key, resource_key))
	if not rule:
		logger.warning(
			"Accès refusé (règle inconnue): user=%s, action=%s, resource=%s, role=%s, groups=%s",
			user.username,
			action_key,
			resource_key,
			canonical_role,
			sorted(groups),
		)
		return False

	has_access = bool(
		(rule["allow_global"] and is_global)
		or profile_role in rule["profile_roles"]
		or canonical_role in rule["canonical_roles"]
		or bool(groups.intersection(rule["groups"]))
	)

	log_method = logger.debug if has_access else logger.warning
	log_method(
		"Accès %s: user=%s, action=%s, resource=%s, role=%s, profile_role=%s, groups=%s, is_global=%s",
		"accordé" if has_access else "refusé",
		user.username,
		action_key,
		resource_key,
		canonical_role,
		profile_role,
		sorted(groups),
		is_global,
	)

	return has_access

