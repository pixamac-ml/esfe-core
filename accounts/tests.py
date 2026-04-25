from typing import Any, cast

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from branches.models import Branch
from payments.models import PaymentAgent
from students.models import Student
from inscriptions.models import Inscription
from admissions.models import Candidature
from formations.models import Programme, Cycle, Diploma, Filiere

from accounts.access import (
	can_access,
	get_user_annexe,
	get_user_groups,
	get_user_position,
	get_user_role,
	get_user_scope,
)
from portal.permissions import get_user_role as get_portal_user_role
from portal.permissions import get_post_login_portal_url


User = get_user_model()
USER_MANAGER = cast(Any, User._default_manager)


class AccessCompatibilityTests(TestCase):
	def setUp(self):
		self.branch_profile = Branch.objects.create(
			name="Annexe Profil",
			code="APR",
			slug="annexe-profil",
		)
		self.branch_agent = Branch.objects.create(
			name="Annexe Agent",
			code="AAG",
			slug="annexe-agent",
		)
		self.branch_manager = Branch.objects.create(
			name="Annexe Manager",
			code="AMG",
			slug="annexe-manager",
		)

	def _create_user(
		self,
		username,
		*,
		groups=None,
		role="",
		branch=None,
		is_staff=True,
		is_superuser=False,
	):
		if is_superuser:
			user = USER_MANAGER.create_superuser(
				username=username,
				email=f"{username}@example.com",
				password="pass1234",
			)
		else:
			user = USER_MANAGER.create_user(
				username=username,
				email=f"{username}@example.com",
				password="pass1234",
				is_staff=is_staff,
			)

		if groups:
			for group_name in groups:
				group, _ = Group.objects.get_or_create(name=group_name)
				user.groups.add(group)

		profile = user.profile
		profile.role = role
		profile.branch = branch
		profile.save(update_fields=["role", "branch", "updated_at"])
		return user

	def test_get_user_groups_expands_legacy_aliases(self):
		user = self._create_user("adm_group", groups=["admissions_managers"])

		groups = set(get_user_groups(user))

		self.assertIn("admissions_managers", groups)
		self.assertIn("admissions", groups)
		self.assertEqual(get_user_role(user), "staff_admin")

	def test_get_user_annexe_uses_compatibility_priority(self):
		user = self._create_user(
			"scoped_user",
			groups=["finance_agents"],
			role="finance",
			branch=self.branch_profile,
		)
		PaymentAgent.objects.create(user=user, branch=self.branch_agent, is_active=True)
		self.branch_manager.manager = user
		self.branch_manager.save(update_fields=["manager"])

		scope = get_user_scope(user)

		self.assertEqual(get_user_annexe(user), self.branch_profile)
		self.assertEqual(scope["branch"], self.branch_profile)
		self.assertEqual(scope["annexe"], self.branch_profile)
		self.assertFalse(scope["is_global"])

	def test_get_user_position_detects_payment_agent(self):
		user = self._create_user("cashier_user", groups=["finance_agents"], role="")
		PaymentAgent.objects.create(user=user, branch=self.branch_agent, is_active=True)

		self.assertEqual(get_user_position(user), "payment_agent")

	def test_can_access_preserves_profile_role_compatibility(self):
		admissions_user = self._create_user(
			"admissions_role",
			role="admissions",
			branch=self.branch_profile,
		)

		self.assertTrue(can_access(admissions_user, "view_dashboard", "admissions"))
		self.assertFalse(can_access(admissions_user, "view_dashboard", "finance"))
		self.assertEqual(get_user_role(admissions_user), "staff_admin")

	def test_can_access_preserves_group_compatibility(self):
		finance_user = self._create_user(
			"finance_group",
			groups=["finance_agents"],
			branch=self.branch_agent,
		)

		self.assertTrue(can_access(finance_user, "view_dashboard", "finance"))
		self.assertFalse(can_access(finance_user, "view_dashboard", "executive"))

	def test_executive_scope_remains_global(self):
		executive_user = self._create_user(
			"dg_group",
			groups=["executive_director"],
			branch=self.branch_profile,
		)

		scope = get_user_scope(executive_user)

		self.assertTrue(scope["is_global"])
		self.assertEqual(scope["role"], "directeur_etudes")
		self.assertTrue(can_access(executive_user, "view_dashboard", "executive"))
		self.assertTrue(can_access(executive_user, "view_dashboard", "finance"))
		self.assertTrue(can_access(executive_user, "view_dashboard", "admissions"))

	def test_manager_rule_is_explicit(self):
		manager_user = self._create_user(
			"branch_manager_user",
			groups=["gestionnaire"],
			branch=self.branch_manager,
		)

		self.assertTrue(can_access(manager_user, "view_dashboard", "manager"))
		self.assertFalse(can_access(manager_user, "view_dashboard", "executive"))


class DashboardRedirectCompatibilityTests(TestCase):
	def setUp(self):
		self.branch = Branch.objects.create(
			name="Annexe Redirect",
			code="ARD",
			slug="annexe-redirect",
		)

	def _create_user(self, username, *, groups=None, role="", branch=None):
		user = USER_MANAGER.create_user(
			username=username,
			email=f"{username}@example.com",
			password="pass1234",
			is_staff=True,
		)

		if groups:
			for group_name in groups:
				group, _ = Group.objects.get_or_create(name=group_name)
				user.groups.add(group)

		profile = user.profile
		profile.role = role
		profile.branch = branch
		profile.save(update_fields=["role", "branch", "updated_at"])
		return user

	def test_dashboard_redirect_prioritizes_executive(self):
		user = self._create_user(
			"redirect_executive",
			groups=["executive_director", "finance_agents", "gestionnaire"],
			branch=self.branch,
		)
		self.client.force_login(user)

		response = self.client.get(reverse("accounts:dashboard_redirect"))

		self.assertRedirects(
			response,
			reverse("accounts:executive_dashboard"),
			fetch_redirect_response=False,
		)

	def test_dashboard_redirect_prioritizes_finance_before_manager(self):
		user = self._create_user(
			"redirect_finance",
			groups=["finance_agents", "gestionnaire"],
			branch=self.branch,
		)
		self.client.force_login(user)

		response = self.client.get(reverse("accounts:dashboard_redirect"))

		self.assertRedirects(
			response,
			reverse("accounts:finance_dashboard"),
			fetch_redirect_response=False,
		)

	def test_dashboard_redirect_sends_manager_to_manager_dashboard(self):
		user = self._create_user(
			"redirect_manager",
			groups=["gestionnaire"],
			branch=self.branch,
		)
		self.client.force_login(user)

		response = self.client.get(reverse("accounts:dashboard_redirect"))

		self.assertRedirects(
			response,
			reverse("accounts:manager_dashboard"),
			fetch_redirect_response=False,
		)

	def test_dashboard_redirect_sends_admissions_user_to_admissions_dashboard(self):
		user = self._create_user(
			"redirect_admissions",
			role="admissions",
			branch=self.branch,
		)
		self.client.force_login(user)

		response = self.client.get(reverse("accounts:dashboard_redirect"))

		self.assertRedirects(
			response,
			reverse("accounts:admissions_dashboard"),
			fetch_redirect_response=False,
		)


class PortalPhaseOneTests(TestCase):
	def setUp(self):
		self.cycle = Cycle.objects.create(
			name="Licence",
			theme="accent",
			min_duration_years=1,
			max_duration_years=5,
		)
		self.diploma = Diploma.objects.create(name="Licence Test", level="superieur")
		self.filiere = Filiere.objects.create(name="Filiere Test")
		self.programme = Programme.objects.create(
			title="Test Programme",
			filiere=self.filiere,
			cycle=self.cycle,
			diploma_awarded=self.diploma,
			duration_years=3,
			short_description="Programme test",
			description="Description test",
		)
		self.branch = Branch.objects.create(
			name="Annexe Portal",
			code="APT",
			slug="annexe-portal",
		)

	def _create_user(self, username, *, role="", groups=None):
		user = USER_MANAGER.create_user(
			username=username,
			email=f"{username}@example.com",
			password="pass1234",
			is_staff=True,
		)
		if groups:
			for group_name in groups:
				group, _ = Group.objects.get_or_create(name=group_name)
				user.groups.add(group)
		profile = user.profile
		profile.role = role
		profile.branch = self.branch
		profile.save(update_fields=["role", "branch", "updated_at"])
		return user

	def test_login_page_loads(self):
		response = self.client.get(reverse("accounts:login"))
		self.assertEqual(response.status_code, 200)

	def test_portal_student_route_allows_student_only(self):
		student = self._create_user("portal_student", role="student")
		self.client.force_login(student)

		response = self.client.get(reverse("accounts_portal:portal_student"))
		self.assertRedirects(
			response,
			reverse("portal_student:dashboard"),
			fetch_redirect_response=False,
		)

	def test_portal_teacher_route_denies_student(self):
		student = self._create_user("portal_student_denied", role="student")
		self.client.force_login(student)

		response = self.client.get(reverse("accounts_portal:portal_teacher"))
		self.assertEqual(response.status_code, 403)

	def test_portal_dashboard_redirects_staff_admin_to_staff_page(self):
		staff_user = self._create_user("portal_staff", groups=["admissions_managers"])
		self.client.force_login(staff_user)

		response = self.client.get(reverse("accounts_portal:portal_dashboard"))
		self.assertRedirects(
			response,
			reverse("accounts_portal:portal_staff"),
			fetch_redirect_response=False,
		)

	def test_login_redirects_to_portal_student(self):
		student = self._create_user("login_student", role="student")

		response = self.client.post(
			reverse("accounts:login"),
			{"username": student.username, "password": "pass1234"},
		)

		self.assertRedirects(
			response,
			reverse("portal_student:dashboard"),
			fetch_redirect_response=False,
		)

	def test_login_redirects_staff_to_portal_staff(self):
		staff_user = self._create_user("login_staff", groups=["admissions_managers"])

		response = self.client.post(
			reverse("accounts:login"),
			{"username": staff_user.username, "password": "pass1234"},
		)

		self.assertRedirects(
			response,
			reverse("accounts_portal:portal_staff"),
			fetch_redirect_response=False,
		)

	def test_post_login_portal_url_uses_existing_routes_only(self):
		student = self._create_user("post_login_student", role="student")
		staff_user = self._create_user("post_login_staff", groups=["finance_agents"])

		self.assertEqual(
			get_post_login_portal_url(student),
			reverse("portal_student:dashboard"),
		)
		self.assertEqual(
			get_post_login_portal_url(staff_user),
			reverse("accounts_portal:portal_staff"),
		)

	def test_student_dashboard_requires_student_role(self):
		staff_user = self._create_user("student_dashboard_staff", groups=["admissions_managers"])
		self.client.force_login(staff_user)

		response = self.client.get(reverse("portal_student:dashboard"))
		self.assertEqual(response.status_code, 403)

	def test_portal_role_falls_back_to_staff_from_groups(self):
		staff_user = self._create_user("portal_role_group", groups=["finance_agents"], role="")
		self.assertEqual(get_portal_user_role(staff_user), "staff")


class BackfillUserRoleTypeCommandTests(TestCase):
	def setUp(self):
		self.cycle = Cycle.objects.create(
			name="Master",
			theme="secondary",
			min_duration_years=1,
			max_duration_years=5,
		)
		self.diploma = Diploma.objects.create(name="Master Test", level="superieur")
		self.filiere = Filiere.objects.create(name="Filiere Command")
		self.programme = Programme.objects.create(
			title="Programme Command",
			filiere=self.filiere,
			cycle=self.cycle,
			diploma_awarded=self.diploma,
			duration_years=2,
			short_description="Programme command",
			description="Description command",
		)
		self.branch = Branch.objects.create(
			name="Annexe Command",
			code="ACM",
			slug="annexe-command",
		)

	def _build_student_link(self, user):
		candidature = Candidature.objects.create(
			first_name="Std",
			last_name="User",
			birth_date="2000-01-01",
			birth_place="Bamako",
			gender="male",
			email=f"{user.username}@example.com",
			phone="70000000",
			programme=self.programme,
			branch=self.branch,
			academic_year="2025-2026",
			status="accepted",
		)
		inscription = Inscription.objects.create(
			candidature=candidature,
			amount_due=100000,
			status=Inscription.STATUS_ACTIVE,
		)
		Student.objects.create(user=user, inscription=inscription, matricule=f"MAT-{user.pk}")

	def test_backfill_completes_only_missing_fields(self):
		student_user = USER_MANAGER.create_user(
			username="etu_esfe_001",
			email="etu_esfe_001@example.com",
			password="pass1234",
			is_staff=True,
		)
		self._build_student_link(student_user)

		group_user = USER_MANAGER.create_user(
			username="agent_fin",
			email="agent_fin@example.com",
			password="pass1234",
			is_staff=True,
		)
		finance_group, _ = Group.objects.get_or_create(name="finance_agents")
		group_user.groups.add(finance_group)

		public_user = USER_MANAGER.create_user(
			username="public_user",
			email="public_user@example.com",
			password="pass1234",
			is_staff=False,
		)

		valid_profile_user = USER_MANAGER.create_user(
			username="valid_profile",
			email="valid_profile@example.com",
			password="pass1234",
			is_staff=True,
		)
		valid_profile = valid_profile_user.profile
		valid_profile.role = "teacher"
		valid_profile.user_type = "staff"
		valid_profile.save(update_fields=["role", "user_type", "updated_at"])

		call_command("backfill_user_role_type")

		student_user.refresh_from_db()
		group_user.refresh_from_db()
		public_user.refresh_from_db()
		valid_profile_user.refresh_from_db()

		self.assertEqual(student_user.profile.user_type, "staff")
		self.assertEqual(student_user.profile.role, "student")

		self.assertEqual(group_user.profile.user_type, "staff")
		self.assertEqual(group_user.profile.role, "finance")

		self.assertEqual(public_user.profile.user_type, "public")
		self.assertEqual(public_user.profile.role, "")

		# Ne pas écraser un profil déjà valide.
		self.assertEqual(valid_profile_user.profile.user_type, "staff")
		self.assertEqual(valid_profile_user.profile.role, "teacher")

