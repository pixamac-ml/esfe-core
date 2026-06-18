from datetime import datetime
from decimal import Decimal
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from branches.models import Branch
from payments.models import Payment, PaymentAgent
from students.models import Student, StudentAttendance, TeacherAttendance
from inscriptions.models import Inscription
from admissions.models import Candidature
from formations.models import Programme, Cycle, Diploma, Filiere
from academics.models import AcademicClass, AcademicDebt, AcademicEnrollment, AcademicScheduleEvent, AcademicYear, EC, ECChapter, ECContent, ECGrade, LessonLog, Semester, UE, WeeklyScheduleSlot

from accounts.access import (
	can_access,
	get_user_annexe,
	get_user_groups,
	get_user_position,
	get_user_role,
	get_user_scope,
)
from accounts.models import BranchCashMovement, PayrollEntry, UserPreference
from communication.models import CommunicationNotification
from portal.permissions import get_user_role as get_portal_user_role
from portal.permissions import get_post_login_portal_url
from portal.models import AccountSupportState, ArchiveBatch, DirectorTeacherAssignment, SupportAuditLog, TeacherDashboardPreference


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
		position="",
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
		profile.position = position
		profile.branch = branch
		profile.save(update_fields=["role", "position", "branch", "updated_at"])
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

	def test_get_user_position_prefers_profile_position(self):
		user = self._create_user("supervisor_user", position="academic_supervisor")
		self.assertEqual(get_user_position(user), "academic_supervisor")

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
		self.assertEqual(scope["role"], "directeur_general")
		self.assertTrue(can_access(executive_user, "view_dashboard", "executive"))
		self.assertFalse(can_access(executive_user, "view_dashboard", "director_studies"))
		self.assertTrue(can_access(executive_user, "view_dashboard", "finance"))
		self.assertTrue(can_access(executive_user, "view_dashboard", "admissions"))

	def test_director_of_studies_scope_is_not_global(self):
		director = self._create_user(
			"director_studies",
			role="executive",
			position="director_of_studies",
			branch=self.branch_profile,
		)

		scope = get_user_scope(director)

		self.assertFalse(scope["is_global"])
		self.assertEqual(scope["role"], "directeur_etudes")
		self.assertFalse(can_access(director, "view_dashboard", "executive"))
		self.assertTrue(can_access(director, "view_dashboard", "director_studies"))

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

	def _create_user(self, username, *, groups=None, role="", position="", branch=None):
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
		profile.position = position
		profile.branch = branch
		profile.save(update_fields=["role", "position", "branch", "updated_at"])
		return user

	def test_dashboard_redirect_sends_dg_to_dg_portal(self):
		user = self._create_user(
			"redirect_executive",
			groups=["executive_director", "finance_agents", "gestionnaire"],
			branch=self.branch,
		)
		self.client.force_login(user)

		response = self.client.get(reverse("accounts:dashboard_redirect"))

		self.assertRedirects(
			response,
			reverse("accounts_portal:portal_dg"),
			fetch_redirect_response=False,
		)

	def test_dashboard_redirect_sends_superadmin_to_superadmin_dashboard(self):
		user = USER_MANAGER.create_superuser(
			username="redirect_superadmin",
			email="redirect_superadmin@example.com",
			password="pass1234",
		)
		self.client.force_login(user)

		response = self.client.get(reverse("accounts:dashboard_redirect"))

		self.assertRedirects(
			response,
			reverse("superadmin:dashboard"),
			fetch_redirect_response=False,
		)

	def test_dashboard_redirect_sends_director_of_studies_to_director_portal(self):
		user = self._create_user(
			"redirect_director_studies",
			role="executive",
			position="director_of_studies",
			branch=self.branch,
		)
		self.client.force_login(user)

		response = self.client.get(reverse("accounts:dashboard_redirect"))

		self.assertRedirects(
			response,
			reverse("accounts_portal:portal_director"),
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

	def test_dashboard_redirect_sends_secretary_to_secretary_portal(self):
		user = self._create_user(
			"redirect_secretary",
			position="secretary",
			branch=self.branch,
		)
		self.client.force_login(user)

		response = self.client.get(reverse("accounts:dashboard_redirect"))

		self.assertRedirects(
			response,
			reverse("accounts_portal:portal_secretary"),
			fetch_redirect_response=False,
		)


class ManagerDashboardRegressionTests(TestCase):
	def setUp(self):
		self.branch = Branch.objects.create(
			name="Annexe Gestion",
			code="AGT",
			slug="annexe-gestion",
		)
		self.user = USER_MANAGER.create_user(
			username="manager_cash_view",
			email="manager_cash_view@example.com",
			password="pass1234",
			is_staff=True,
		)
		group, _ = Group.objects.get_or_create(name="gestionnaire")
		self.user.groups.add(group)
		profile = self.user.profile
		profile.branch = self.branch
		profile.save(update_fields=["branch", "updated_at"])
		self.client.force_login(self.user)

	def test_manager_cash_section_renders_when_movement_has_no_creator(self):
		BranchCashMovement.objects.create(
			branch=self.branch,
			movement_type=BranchCashMovement.TYPE_IN,
			source=BranchCashMovement.SOURCE_MANUAL,
			amount=25000,
			label="Regularisation caisse",
			reference="CASH-REG-001",
			created_by=None,
		)

		response = self.client.get(reverse("accounts:manager_dashboard"), {"section": "caisse"})

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Regularisation caisse")

	def test_manager_report_section_renders_annual_revenue_panel(self):
		response = self.client.get(reverse("accounts:manager_dashboard"), {"section": "rapport"})

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Argent genere par an")

	def test_salary_ready_notifies_employee_dashboard(self):
		employee = USER_MANAGER.create_user(
			username="employee_payroll_ready",
			email="employee_payroll_ready@example.com",
			password="pass1234",
			is_staff=True,
		)
		employee_profile = employee.profile
		employee_profile.branch = self.branch
		employee_profile.salary_base = 90000
		employee_profile.position = "secretary"
		employee_profile.user_type = "staff"
		employee_profile.save(update_fields=["branch", "salary_base", "position", "user_type", "updated_at"])

		response = self.client.post(
			reverse("accounts:htmx_manager_salary_upsert", args=[employee.id]),
			{
				"period_month": "2026-05-01",
				"base_salary": "90000",
				"allowances": "10000",
				"deductions": "5000",
				"advances": "0",
				"notes": "Controle gestionnaire",
				"submit_action": "ready",
			},
		)

		self.assertEqual(response.status_code, 200)
		entry = PayrollEntry.objects.get(branch=self.branch, employee=employee, period_month="2026-05-01")
		self.assertEqual(entry.status, PayrollEntry.STATUS_READY)
		self.assertTrue(
			CommunicationNotification.objects.filter(
				recipient=employee,
				event_type="salary_available",
				legacy_source="payroll_entry",
				legacy_object_id=str(entry.pk),
			).exists()
		)

	def test_salary_payment_is_blocked_when_branch_cash_is_insufficient(self):
		employee = USER_MANAGER.create_user(
			username="employee_cash_blocked",
			email="employee_cash_blocked@example.com",
			password="pass1234",
			is_staff=True,
		)
		employee_profile = employee.profile
		employee_profile.branch = self.branch
		employee_profile.salary_base = 75000
		employee_profile.position = "secretary"
		employee_profile.user_type = "staff"
		employee_profile.save(update_fields=["branch", "salary_base", "position", "user_type", "updated_at"])
		entry = PayrollEntry.objects.create(
			branch=self.branch,
			employee=employee,
			period_month="2026-05-01",
			base_salary=75000,
			status=PayrollEntry.STATUS_READY,
			created_by=self.user,
			updated_by=self.user,
		)

		response = self.client.post(
			reverse("accounts:htmx_manager_salary_pay", args=[entry.id]),
			{"payment_amount": "75000"},
		)

		self.assertEqual(response.status_code, 400)
		entry.refresh_from_db()
		self.assertEqual(entry.paid_amount, 0)

	def test_salary_payment_creates_cash_outflow_when_cash_is_available(self):
		employee = USER_MANAGER.create_user(
			username="employee_cash_ok",
			email="employee_cash_ok@example.com",
			password="pass1234",
			is_staff=True,
		)
		employee_profile = employee.profile
		employee_profile.branch = self.branch
		employee_profile.salary_base = 60000
		employee_profile.position = "secretary"
		employee_profile.user_type = "staff"
		employee_profile.save(update_fields=["branch", "salary_base", "position", "user_type", "updated_at"])
		entry = PayrollEntry.objects.create(
			branch=self.branch,
			employee=employee,
			period_month="2026-05-01",
			base_salary=60000,
			status=PayrollEntry.STATUS_READY,
			created_by=self.user,
			updated_by=self.user,
		)
		BranchCashMovement.objects.create(
			branch=self.branch,
			movement_type=BranchCashMovement.TYPE_IN,
			source=BranchCashMovement.SOURCE_MANUAL,
			amount=100000,
			label="Approvisionnement caisse",
			created_by=self.user,
		)

		response = self.client.post(
			reverse("accounts:htmx_manager_salary_pay", args=[entry.id]),
			{"payment_amount": "60000"},
		)

		self.assertEqual(response.status_code, 200)
		entry.refresh_from_db()
		self.assertEqual(entry.paid_amount, 60000)
		self.assertTrue(
			BranchCashMovement.objects.filter(
				branch=self.branch,
				source=BranchCashMovement.SOURCE_PAYROLL,
				movement_type=BranchCashMovement.TYPE_OUT,
				source_reference__startswith="PAYROLL-",
			).exists()
		)

	def test_salary_advance_updates_payroll_and_cash_before_availability(self):
		employee = USER_MANAGER.create_user(
			username="employee_advance_ok",
			email="employee_advance_ok@example.com",
			password="pass1234",
			is_staff=True,
		)
		employee_profile = employee.profile
		employee_profile.branch = self.branch
		employee_profile.salary_base = 80000
		employee_profile.position = "secretary"
		employee_profile.user_type = "staff"
		employee_profile.save(update_fields=["branch", "salary_base", "position", "user_type", "updated_at"])
		BranchCashMovement.objects.create(
			branch=self.branch,
			movement_type=BranchCashMovement.TYPE_IN,
			source=BranchCashMovement.SOURCE_MANUAL,
			amount=50000,
			label="Approvisionnement avance",
			created_by=self.user,
		)

		response = self.client.post(
			reverse("accounts:htmx_manager_salary_advance", args=[employee.id]),
			{
				"period_month": "2026-05-01",
				"advance_amount": "30000",
			},
		)

		self.assertEqual(response.status_code, 200)
		entry = PayrollEntry.objects.get(branch=self.branch, employee=employee, period_month="2026-05-01")
		self.assertEqual(entry.status, PayrollEntry.STATUS_DRAFT)
		self.assertEqual(entry.advances, 30000)
		self.assertTrue(
			BranchCashMovement.objects.filter(
				branch=self.branch,
				source=BranchCashMovement.SOURCE_PAYROLL,
				movement_type=BranchCashMovement.TYPE_OUT,
				label__icontains="Avance salaire",
			).exists()
		)

	def test_salary_advance_is_blocked_when_payroll_is_already_available(self):
		employee = USER_MANAGER.create_user(
			username="employee_advance_blocked",
			email="employee_advance_blocked@example.com",
			password="pass1234",
			is_staff=True,
		)
		employee_profile = employee.profile
		employee_profile.branch = self.branch
		employee_profile.salary_base = 65000
		employee_profile.position = "secretary"
		employee_profile.user_type = "staff"
		employee_profile.save(update_fields=["branch", "salary_base", "position", "user_type", "updated_at"])
		PayrollEntry.objects.create(
			branch=self.branch,
			employee=employee,
			period_month="2026-05-01",
			base_salary=65000,
			status=PayrollEntry.STATUS_READY,
			created_by=self.user,
			updated_by=self.user,
		)
		BranchCashMovement.objects.create(
			branch=self.branch,
			movement_type=BranchCashMovement.TYPE_IN,
			source=BranchCashMovement.SOURCE_MANUAL,
			amount=50000,
			label="Approvisionnement blocage",
			created_by=self.user,
		)

		response = self.client.post(
			reverse("accounts:htmx_manager_salary_advance", args=[employee.id]),
			{
				"period_month": "2026-05-01",
				"advance_amount": "10000",
			},
		)

		self.assertEqual(response.status_code, 400)


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

	def _create_user(self, username, *, role="", position="", groups=None):
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
		profile.position = position
		profile.branch = self.branch
		profile.save(update_fields=["role", "position", "branch", "updated_at"])
		return user

	def _create_student_record(self, user, *, inscription_status=Inscription.STATUS_PARTIAL):
		candidature = Candidature.objects.create(
			first_name="Portal",
			last_name="Student",
			birth_date="2000-01-01",
			birth_place="Bamako",
			gender="male",
			email=f"{user.username}@example.com",
			phone="70000000",
			programme=self.programme,
			branch=self.branch,
			academic_year="2025-2026",
			entry_year=1,
			status="accepted",
		)
		inscription = Inscription.objects.create(
			candidature=candidature,
			amount_due=100000,
			status=inscription_status,
		)
		return Student.objects.create(user=user, inscription=inscription, matricule=f"MAT-{user.pk}")

	def _create_academic_class_bundle(self, level="L1"):
		safe_level = "".join(ch for ch in level if ch.isalnum())[:3]
		academic_year = AcademicYear.objects.create(
			name=f"25-26-{safe_level}",
			start_date="2025-10-01",
			end_date="2026-07-31",
			is_active=True,
		)
		academic_class = AcademicClass.objects.create(
			programme=self.programme,
			branch=self.branch,
			academic_year=academic_year,
			level=level,
			study_level="LICENCE",
			is_active=True,
		)
		semester = Semester.objects.create(academic_class=academic_class, number=1)
		ue = UE.objects.create(semester=semester, code=f"UE-{level}", title=f"UE {level}")
		ec = EC.objects.create(ue=ue, title=f"EC {level}", credit_required=3, coefficient=2)
		return academic_year, academic_class, ec

	def _create_course_event(self, academic_class, academic_year, ec, teacher, *, hour=8):
		start_datetime = timezone.make_aware(datetime(2026, 4, 28, hour, 0))
		end_datetime = timezone.make_aware(datetime(2026, 4, 28, hour + 2, 0))
		return AcademicScheduleEvent.objects.create(
			title=f"Cours {ec.title}",
			description="Cours test",
			event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
			academic_class=academic_class,
			ec=ec,
			teacher=teacher,
			branch=self.branch,
			academic_year=academic_year,
			start_datetime=start_datetime,
			end_datetime=end_datetime,
			status=AcademicScheduleEvent.STATUS_PLANNED,
			location="Salle A1",
			created_by=teacher,
			updated_by=teacher,
			is_active=True,
		)

	def test_login_page_loads(self):
		response = self.client.get(reverse("accounts:login"))
		self.assertEqual(response.status_code, 200)

	def test_portal_student_route_allows_student_only(self):
		student = self._create_user("portal_student", role="student")
		self.client.force_login(student)

		response = self.client.get(reverse("accounts_portal:portal_student"))
		self.assertRedirects(
			response,
			reverse("accounts_portal:portal_dashboard"),
			fetch_redirect_response=False,
		)

	def test_portal_teacher_route_denies_student(self):
		student = self._create_user("portal_student_denied", role="student")
		self.client.force_login(student)

		response = self.client.get(reverse("accounts_portal:portal_teacher"))
		self.assertEqual(response.status_code, 403)

	def test_portal_teacher_route_renders_dashboard_for_teacher(self):
		teacher = self._create_user("portal_teacher_dashboard", role="teacher", position="teacher")
		teacher.profile.employee_code = "ENS-001"
		teacher.profile.employment_status = "permanent"
		teacher.profile.save(update_fields=["employee_code", "employment_status", "updated_at"])
		self.client.force_login(teacher)

		response = self.client.get(reverse("accounts_portal:portal_teacher"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Dashboard enseignant")
		self.assertContains(response, "ENS-001")
		self.assertContains(response, "Mes classes et effectifs")
		self.assertContains(response, "Chargement des parametres")

	def test_teacher_class_detail_renders_for_assigned_teacher(self):
		teacher = self._create_user("portal_teacher_class_detail", role="teacher", position="teacher")
		academic_year, academic_class, ec = self._create_academic_class_bundle("L2")
		self._create_course_event(academic_class, academic_year, ec, teacher, hour=9)
		self.client.force_login(teacher)

		response = self.client.get(reverse("accounts_portal:teacher_class_detail", args=[academic_class.id]))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, academic_class.display_name)
		self.assertContains(response, "Etudiants de la classe")

	def test_teacher_lesson_log_panel_post_creates_log(self):
		teacher = self._create_user("portal_teacher_log_panel", role="teacher", position="teacher")
		academic_year, academic_class, ec = self._create_academic_class_bundle("L3")
		schedule_event = self._create_course_event(academic_class, academic_year, ec, teacher, hour=11)
		self.client.force_login(teacher)

		response = self.client.post(
			reverse("accounts_portal:teacher_lesson_log_panel", args=[schedule_event.id]),
			{
				"status": LessonLog.STATUS_DONE,
				"content": "Cours assure normalement",
				"homework": "Exercice 1",
				"observations": "RAS",
			},
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(response.status_code, 200)
		self.assertNotIn("HX-Refresh", response)
		self.assertContains(response, "Cahier enregistre avec succes.")
		self.assertTrue(
			LessonLog.objects.filter(
				teacher=teacher,
				schedule_event=schedule_event,
				status=LessonLog.STATUS_DONE,
			).exists()
		)

	def test_teacher_class_detail_renders_weekly_slot_rows(self):
		teacher = self._create_user("portal_teacher_weekly_slot", role="teacher", position="teacher")
		academic_year, academic_class, ec = self._create_academic_class_bundle("L3S")
		WeeklyScheduleSlot.objects.create(
			academic_class=academic_class,
			academic_year=academic_year,
			branch=academic_class.branch,
			teacher=teacher,
			ec=ec,
			weekday=1,
			start_time=datetime.strptime("10:00", "%H:%M").time(),
			end_time=datetime.strptime("12:00", "%H:%M").time(),
			room="B12",
		)
		self.client.force_login(teacher)

		response = self.client.get(reverse("accounts_portal:teacher_class_detail", args=[academic_class.id]))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Trame hebdomadaire officielle")
		self.assertContains(response, "B12")

	def test_teacher_support_workspace_creates_video_and_text_supports(self):
		teacher = self._create_user("portal_teacher_supports", role="teacher", position="teacher")
		academic_year, academic_class, ec = self._create_academic_class_bundle("L4")
		self._create_course_event(academic_class, academic_year, ec, teacher, hour=11)
		self.client.force_login(teacher)

		chapter_response = self.client.post(
			reverse("accounts_portal:teacher_support_workspace"),
			{
				"action": "create_chapter",
				"class_id": academic_class.id,
				"ec_id": ec.id,
				"chapter_title": "Chapitre 1",
			},
			HTTP_HX_REQUEST="true",
		)
		self.assertEqual(chapter_response.status_code, 200)
		chapter = ECChapter.objects.get(ec=ec, title="Chapitre 1")

		video_response = self.client.post(
			reverse("accounts_portal:teacher_support_workspace"),
			{
				"action": "create_content",
				"class_id": academic_class.id,
				"ec_id": ec.id,
				"chapter_id": chapter.id,
				"content_title": "Video chapitre 1",
				"content_type": ECContent.CONTENT_TYPE_VIDEO,
				"video_url": "https://example.com/video-intro",
			},
			HTTP_HX_REQUEST="true",
		)
		self.assertEqual(video_response.status_code, 200)
		self.assertTrue(
			ECContent.objects.filter(
				chapter=chapter,
				title="Video chapitre 1",
				content_type=ECContent.CONTENT_TYPE_VIDEO,
				video_url="https://example.com/video-intro",
			).exists()
		)

		text_response = self.client.post(
			reverse("accounts_portal:teacher_support_workspace"),
			{
				"action": "create_content",
				"class_id": academic_class.id,
				"ec_id": ec.id,
				"chapter_id": chapter.id,
				"content_title": "Resume chapitre 1",
				"content_type": ECContent.CONTENT_TYPE_TEXT,
				"text_content": "Synthese du cours et consignes.",
			},
			HTTP_HX_REQUEST="true",
		)
		self.assertEqual(text_response.status_code, 200)
		self.assertTrue(
			ECContent.objects.filter(
				chapter=chapter,
				title="Resume chapitre 1",
				content_type=ECContent.CONTENT_TYPE_TEXT,
				text_content="Synthese du cours et consignes.",
			).exists()
		)

	def test_teacher_dashboard_uses_director_assignment_even_without_schedule(self):
		teacher = self._create_user("portal_teacher_assignment_only", role="teacher", position="teacher")
		director = self._create_user("portal_director_assignment_only", role="staff_admin", position="director_of_studies")
		academic_year, academic_class, ec = self._create_academic_class_bundle("L5")
		director.profile.branch = academic_class.branch
		director.profile.save(update_fields=["branch", "updated_at"])
		DirectorTeacherAssignment.objects.create(
			branch=academic_class.branch,
			teacher=teacher,
			academic_class=academic_class,
			ec=ec,
			room_label="C-14",
			planned_hours="24.00",
			created_by=director,
		)
		self.client.force_login(teacher)

		response = self.client.get(reverse("accounts_portal:portal_teacher"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, academic_class.display_name)
		self.assertContains(response, ec.title)

	def test_teacher_support_workspace_lists_director_assigned_class_without_schedule(self):
		teacher = self._create_user("portal_teacher_assignment_support", role="teacher", position="teacher")
		director = self._create_user("portal_director_assignment_support", role="staff_admin", position="director_of_studies")
		academic_year, academic_class, ec = self._create_academic_class_bundle("M1")
		director.profile.branch = academic_class.branch
		director.profile.save(update_fields=["branch", "updated_at"])
		DirectorTeacherAssignment.objects.create(
			branch=academic_class.branch,
			teacher=teacher,
			academic_class=academic_class,
			ec=ec,
			room_label="Lab-2",
			planned_hours="18.00",
			created_by=director,
		)
		self.client.force_login(teacher)

		response = self.client.get(reverse("accounts_portal:teacher_support_workspace"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, academic_class.display_name)
		self.assertContains(response, ec.title)

	def test_teacher_settings_workspace_renders_and_persists_preferences(self):
		teacher = self._create_user("portal_teacher_settings", role="teacher", position="teacher")
		self.client.force_login(teacher)

		dashboard_response = self.client.get(reverse("accounts_portal:portal_dashboard"))
		self.assertEqual(dashboard_response.status_code, 200)
		self.assertContains(dashboard_response, "Profil central, preferences, securite")
		self.assertContains(dashboard_response, "Ouvrir Parametres")

		response = self.client.get(reverse("accounts_portal:teacher_settings_workspace"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Tableau de bord enseignant")
		self.assertContains(response, "Section d'ouverture")
		self.assertContains(response, "Modifier le profil")

		post_response = self.client.post(
			reverse("accounts_portal:teacher_settings_workspace"),
			{
				"dark_mode": "on",
				"sidebar_collapsed": "on",
				"compact_mode": "on",
				"default_section": "schedule",
				"notify_lesson_reminders": "on",
				"notify_schedule_changes": "on",
				"notify_support_messages": "on",
			},
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(post_response.status_code, 200)
		self.assertContains(post_response, "Parametres enregistres.")

		preference = TeacherDashboardPreference.objects.get(teacher=teacher, branch=self.branch)
		self.assertTrue(preference.dark_mode)
		self.assertTrue(preference.sidebar_collapsed)
		self.assertTrue(preference.compact_mode)
		self.assertEqual(preference.default_section, "schedule")
		self.assertTrue(preference.notify_lesson_reminders)
		self.assertTrue(preference.notify_schedule_changes)
		self.assertTrue(preference.notify_support_messages)

	def test_portal_dashboard_renders_staff_page_from_single_entry(self):
		staff_user = self._create_user("portal_staff", groups=["admissions_managers"])
		self.client.force_login(staff_user)

		response = self.client.get(reverse("accounts_portal:portal_dashboard"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Portail staff")

	def test_login_redirects_to_portal_student(self):
		student = self._create_user("login_student", role="student")

		response = self.client.post(
			reverse("accounts:login"),
			{"username": student.username, "password": "pass1234"},
		)

		self.assertRedirects(
			response,
			reverse("accounts_portal:portal_dashboard"),
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
			reverse("accounts_portal:portal_dashboard"),
			fetch_redirect_response=False,
		)

	def test_post_login_portal_url_uses_single_portal_entry(self):
		student = self._create_user("post_login_student", role="student")
		staff_user = self._create_user("post_login_staff", groups=["finance_agents"])
		dg_user = self._create_user("post_login_dg", groups=["executive_director"])
		superadmin = USER_MANAGER.create_superuser(
			username="post_login_superadmin",
			email="post_login_superadmin@example.com",
			password="pass1234",
		)

		self.assertEqual(
			get_post_login_portal_url(student),
			reverse("accounts_portal:portal_dashboard"),
		)
		self.assertEqual(
			get_post_login_portal_url(staff_user),
			reverse("accounts_portal:portal_dashboard"),
		)
		self.assertEqual(
			get_post_login_portal_url(dg_user),
			reverse("accounts_portal:portal_dg"),
		)
		self.assertEqual(
			get_post_login_portal_url(superadmin),
			reverse("superadmin:dashboard"),
		)

	def test_student_dashboard_requires_student_role(self):
		staff_user = self._create_user("student_dashboard_staff", groups=["admissions_managers"])
		self.client.force_login(staff_user)

		response = self.client.get(reverse("portal_student:dashboard"))
		self.assertEqual(response.status_code, 403)

	def test_student_dashboard_shows_real_academic_assignment(self):
		student_user = self._create_user("student_dashboard_real", role="student")
		student = self._create_student_record(student_user)
		academic_year = AcademicYear.objects.create(
			name="2025-2026",
			start_date="2025-10-01",
			end_date="2026-07-31",
			is_active=True,
		)
		academic_class = AcademicClass.objects.create(
			programme=self.programme,
			branch=self.branch,
			academic_year=academic_year,
			level="L1",
			study_level="LICENCE",
			is_active=True,
		)
		AcademicEnrollment.objects.create(
			inscription=student.inscription,
			student=student_user,
			programme=self.programme,
			branch=self.branch,
			academic_year=academic_year,
			academic_class=academic_class,
		)
		self.client.force_login(student_user)

		response = self.client.get(reverse("portal_student:dashboard"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Ma situation academique")
		self.assertContains(response, self.programme.title)
		self.assertContains(response, "Affecte")
		self.assertContains(response, "2025-2026")

	def test_student_dashboard_shows_pending_message_without_enrollment(self):
		student_user = self._create_user("student_dashboard_pending", role="student")
		self._create_student_record(student_user)
		self.client.force_login(student_user)

		response = self.client.get(reverse("portal_student:dashboard"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Affectation academique en cours ou requise.")

	def test_student_ec_detail_shows_only_enrolled_class_ec(self):
		student_user = self._create_user("student_ec_detail_ok", role="student")
		student = self._create_student_record(student_user)
		academic_year = AcademicYear.objects.create(
			name="2025-2026",
			start_date="2025-10-01",
			end_date="2026-07-31",
			is_active=True,
		)
		academic_class = AcademicClass.objects.create(
			programme=self.programme,
			branch=self.branch,
			academic_year=academic_year,
			level="L1",
			study_level="LICENCE",
			is_active=True,
		)
		AcademicEnrollment.objects.create(
			inscription=student.inscription,
			student=student_user,
			programme=self.programme,
			branch=self.branch,
			academic_year=academic_year,
			academic_class=academic_class,
		)
		semester = Semester.objects.create(academic_class=academic_class, number=1)
		ue = UE.objects.create(semester=semester, code="UE101", title="Fondamentaux")
		ec = EC.objects.create(ue=ue, title="Introduction", credit_required=3, coefficient=2)
		self.client.force_login(student_user)

		response = self.client.get(reverse("portal_student:ec_detail", args=[ec.id]))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Introduction")
		self.assertContains(response, "Fondamentaux")

	def test_student_ec_detail_hides_ec_from_other_class(self):
		student_user = self._create_user("student_ec_detail_denied", role="student")
		student = self._create_student_record(student_user)
		academic_year = AcademicYear.objects.create(
			name="2025-2026",
			start_date="2025-10-01",
			end_date="2026-07-31",
			is_active=True,
		)
		student_class = AcademicClass.objects.create(
			programme=self.programme,
			branch=self.branch,
			academic_year=academic_year,
			level="L1",
			study_level="LICENCE",
			is_active=True,
		)
		AcademicEnrollment.objects.create(
			inscription=student.inscription,
			student=student_user,
			programme=self.programme,
			branch=self.branch,
			academic_year=academic_year,
			academic_class=student_class,
		)
		other_class = AcademicClass.objects.create(
			programme=self.programme,
			branch=self.branch,
			academic_year=academic_year,
			level="L2",
			study_level="LICENCE",
			is_active=True,
		)
		other_semester = Semester.objects.create(academic_class=other_class, number=1)
		other_ue = UE.objects.create(semester=other_semester, code="UE201", title="Approfondissement")
		other_ec = EC.objects.create(ue=other_ue, title="EC Hors Classe", credit_required=3, coefficient=2)
		self.client.force_login(student_user)

		response = self.client.get(reverse("portal_student:ec_detail", args=[other_ec.id]))

		self.assertEqual(response.status_code, 404)

	def test_student_semester_two_is_locked_until_semester_one_is_validated(self):
		from portal.student.services import get_student_courses

		student_user = self._create_user("student_s2_locked", role="student")
		student = self._create_student_record(student_user)
		academic_year = AcademicYear.objects.create(
			name="2025-2026",
			start_date="2025-10-01",
			end_date="2026-07-31",
			is_active=True,
		)
		academic_class = AcademicClass.objects.create(
			programme=self.programme,
			branch=self.branch,
			academic_year=academic_year,
			level="L1",
			study_level="LICENCE",
			is_active=True,
		)
		enrollment = AcademicEnrollment.objects.create(
			inscription=student.inscription,
			student=student_user,
			programme=self.programme,
			branch=self.branch,
			academic_year=academic_year,
			academic_class=academic_class,
		)
		semester_one = Semester.objects.create(academic_class=academic_class, number=1)
		semester_two = Semester.objects.create(academic_class=academic_class, number=2)
		ue_one = UE.objects.create(semester=semester_one, code="UE101", title="Bases")
		ue_two = UE.objects.create(semester=semester_two, code="UE201", title="Suite")
		ec_one = EC.objects.create(ue=ue_one, title="EC S1", credit_required=3, coefficient=2)
		ec_two = EC.objects.create(ue=ue_two, title="EC S2", credit_required=3, coefficient=2)

		courses = get_student_courses(student)
		s2_course = next(course for course in courses if course["id"] == ec_two.id)
		self.assertFalse(s2_course["semester_unlocked"])

		self.client.force_login(student_user)
		response = self.client.get(reverse("portal_student:ec_detail", args=[ec_two.id]))
		self.assertEqual(response.status_code, 403)

		ECGrade.objects.create(
			enrollment=enrollment,
			ec=ec_one,
			normal_score=Decimal("14.00"),
			final_score=Decimal("14.00"),
			credit_obtained=Decimal("3.00"),
			is_validated=True,
		)

		courses = get_student_courses(student)
		s2_course = next(course for course in courses if course["id"] == ec_two.id)
		self.assertTrue(s2_course["semester_unlocked"])

		response = self.client.get(reverse("portal_student:ec_detail", args=[ec_two.id]))
		self.assertEqual(response.status_code, 200)

	def test_portal_role_falls_back_to_staff_from_groups(self):
		staff_user = self._create_user("portal_role_group", groups=["finance_agents"], role="")
		self.assertEqual(get_portal_user_role(staff_user), "staff")

	def test_login_redirects_finance_position_to_finance_portal(self):
		finance_user = self._create_user("portal_finance_user", role="finance", position="finance_manager")
		response = self.client.post(
			reverse("accounts:login"),
			{"username": finance_user.username, "password": "pass1234"},
		)
		self.assertRedirects(
			response,
			reverse("accounts_portal:portal_dashboard"),
			fetch_redirect_response=False,
		)

	def test_portal_dashboard_renders_supervisor_dashboard_from_single_entry(self):
		supervisor = self._create_user("portal_supervisor", position="academic_supervisor")
		self.client.force_login(supervisor)
		response = self.client.get(reverse("accounts_portal:portal_dashboard"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Dashboard Surveillant General")
		self.assertContains(response, "Pilotage des classes, du temps et de la discipline")

	def test_portal_dashboard_renders_director_dashboard_from_single_entry(self):
		director = self._create_user("portal_director", role="executive", position="director_of_studies")
		self.client.force_login(director)
		response = self.client.get(reverse("accounts_portal:portal_dashboard"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Dashboard Direction des Etudes")
		self.assertContains(response, "Pilotage de la qualite academique et des charges")
		self.assertContains(response, reverse("accounts:logout"))

	def test_portal_dashboard_renders_dg_dashboard_from_single_entry(self):
		dg_user = self._create_user("portal_dg", position="executive_director")
		self.client.force_login(dg_user)

		response = self.client.get(reverse("accounts_portal:portal_dashboard"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Dashboard Directeur")
		self.assertContains(response, "Direction generale")

	def test_portal_dashboard_redirects_superadmin_to_superadmin_dashboard(self):
		superadmin = USER_MANAGER.create_superuser(
			username="portal_superadmin",
			email="portal_superadmin@example.com",
			password="pass1234",
		)
		self.client.force_login(superadmin)

		response = self.client.get(reverse("accounts_portal:portal_dashboard"))

		self.assertRedirects(
			response,
			reverse("superadmin:dashboard"),
			fetch_redirect_response=False,
		)

	def test_director_can_create_teacher_with_initial_room_assignment(self):
		director = self._create_user("portal_director_create_teacher", role="executive", position="director_of_studies")
		academic_year, academic_class, ec = self._create_academic_class_bundle("D1A")
		self.client.force_login(director)

		response = self.client.post(
			reverse("accounts_portal:director_teacher_create"),
			{
				"first_name": "Awa",
				"last_name": "Diallo",
				"email": "awa.diallo@example.com",
				"phone": "+22370000000",
				"specialty": "Anatomie",
				"class_id": academic_class.id,
				"ec_id": ec.id,
				"room_label": "Salle B12",
				"planned_hours": "24",
			},
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(response.status_code, 200)
		teacher = User.objects.get(email="awa.diallo@example.com")
		self.assertEqual(teacher.profile.position, "teacher")
		assignment = DirectorTeacherAssignment.objects.get(teacher=teacher, academic_class=academic_class, ec=ec)
		self.assertEqual(assignment.room_label, "Salle B12")
		self.assertEqual(str(assignment.planned_hours), "24.00")
		self.assertContains(response, "Enseignant cree, affecte et acces generes.")

	def test_director_teacher_assignment_requires_matching_class_room_and_ec(self):
		director = self._create_user("portal_director_assign_teacher", role="executive", position="director_of_studies")
		teacher = self._create_user("portal_teacher_for_director_assign", role="teacher", position="teacher")
		_academic_year, academic_class, ec = self._create_academic_class_bundle("D2A")
		other_year = AcademicYear.objects.create(
			name="2026-2027",
			start_date="2025-10-01",
			end_date="2026-07-31",
			is_active=False,
		)
		other_class = AcademicClass.objects.create(
			programme=self.programme,
			branch=self.branch,
			academic_year=other_year,
			level="D3A",
			study_level="LICENCE",
			is_active=True,
		)
		other_semester = Semester.objects.create(academic_class=other_class, number=1)
		other_ue = UE.objects.create(semester=other_semester, code="UE-D3A", title="UE D3A")
		other_ec = EC.objects.create(ue=other_ue, title="EC Hors Classe Directeur", credit_required=3, coefficient=2)
		self.client.force_login(director)

		error_response = self.client.post(
			reverse("accounts_portal:director_teacher_assign"),
			{
				"teacher_id": teacher.id,
				"class_id": academic_class.id,
				"ec_id": other_ec.id,
				"room_label": "Salle B14",
				"planned_hours": "18",
			},
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(error_response.status_code, 200)
		self.assertContains(error_response, "La matiere selectionnee")
		self.assertContains(error_response, "classe choisie")
		self.assertFalse(DirectorTeacherAssignment.objects.filter(teacher=teacher, academic_class=academic_class).exists())

		success_response = self.client.post(
			reverse("accounts_portal:director_teacher_assign"),
			{
				"teacher_id": teacher.id,
				"class_id": academic_class.id,
				"ec_id": ec.id,
				"room_label": "Salle B14",
				"planned_hours": "18",
			},
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(success_response.status_code, 200)
		assignment = DirectorTeacherAssignment.objects.get(teacher=teacher, academic_class=academic_class, ec=ec)
		self.assertEqual(assignment.room_label, "Salle B14")
		self.assertEqual(str(assignment.planned_hours), "18.00")
		self.assertContains(success_response, "Affectation enregistree :")

	def test_director_teacher_assignment_requires_planned_hours(self):
		director = self._create_user("portal_director_assign_hours", role="executive", position="director_of_studies")
		teacher = self._create_user("portal_teacher_assign_hours", role="teacher", position="teacher")
		_academic_year, academic_class, ec = self._create_academic_class_bundle("D4A")
		self.client.force_login(director)

		response = self.client.post(
			reverse("accounts_portal:director_teacher_assign"),
			{
				"teacher_id": teacher.id,
				"class_id": academic_class.id,
				"ec_id": ec.id,
				"room_label": "Salle C10",
				"planned_hours": "",
			},
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Le volume horaire est obligatoire")
		self.assertFalse(DirectorTeacherAssignment.objects.filter(teacher=teacher, academic_class=academic_class, ec=ec).exists())

	def test_director_can_open_planner_hub_for_class(self):
		director = self._create_user("portal_director_planner_hub", role="executive", position="director_of_studies")
		_academic_year, academic_class, _ec = self._create_academic_class_bundle("D5A")
		self.client.force_login(director)

		response = self.client.get(
			reverse("accounts_portal:director_planner_hub"),
			{"class_id": academic_class.id, "week_start": "2026-05-11"},
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, academic_class.display_name)
		self.assertContains(response, "Grille hebdomadaire")

	def test_director_can_plan_weekly_slot_and_generate_month(self):
		director = self._create_user("portal_director_plan_month", role="executive", position="director_of_studies")
		teacher = self._create_user("portal_teacher_plan_month", role="teacher", position="teacher")
		academic_year, academic_class, ec = self._create_academic_class_bundle("D6A")
		self.client.force_login(director)

		save_response = self.client.post(
			reverse("accounts_portal:director_weekly_slot_save", args=[academic_class.id]),
			{
				"week_start": "2026-05-11",
				"action": "create",
				"weekday": "0",
				"start_time": "08:00",
				"end_time": "10:00",
				"ec_id": ec.id,
				"teacher_id": teacher.id,
				"room": "Salle D12",
			},
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(save_response.status_code, 200)
		self.assertContains(save_response, "Creneau hebdomadaire cree.")

		month_response = self.client.post(
			reverse("accounts_portal:director_month_materialize", args=[academic_class.id]),
			{"week_start": "2026-05-11"},
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(month_response.status_code, 200)
		self.assertContains(month_response, "Mois pedagogique genere")
		self.assertEqual(
			AcademicScheduleEvent.objects.filter(
				academic_class=academic_class,
				academic_year=academic_year,
				ec=ec,
				teacher=teacher,
				location="Salle D12",
			).count(),
			4,
		)

		second_month_response = self.client.post(
			reverse("accounts_portal:director_month_materialize", args=[academic_class.id]),
			{"week_start": "2026-05-11"},
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(second_month_response.status_code, 200)
		self.assertEqual(
			AcademicScheduleEvent.objects.filter(
				academic_class=academic_class,
				academic_year=academic_year,
				ec=ec,
				teacher=teacher,
				location="Salle D12",
			).count(),
			4,
		)

	def test_director_can_program_teacher_in_free_slot(self):
		director = self._create_user("portal_director_program_free", role="executive", position="director_of_studies")
		teacher = self._create_user("portal_teacher_program_free", role="teacher", position="teacher")
		academic_year, academic_class, ec = self._create_academic_class_bundle("D7A")
		self.client.force_login(director)

		response = self.client.post(
			reverse("accounts_portal:director_create_schedule_event", args=[academic_class.id]),
			{
				"week_start": "2026-05-11",
				"planner_intent": "program",
				"date": "2026-05-11",
				"start_time": "08:00",
				"end_time": "10:00",
				"location": "Salle E01",
				"ec_id": ec.id,
				"teacher_id": teacher.id,
			},
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Cours programme sur la semaine.")
		self.assertTrue(
			AcademicScheduleEvent.objects.filter(
				academic_class=academic_class,
				academic_year=academic_year,
				ec=ec,
				teacher=teacher,
				location="Salle E01",
			).exists()
		)

	def test_director_schedule_event_rejects_teacher_room_and_class_conflicts(self):
		director = self._create_user("portal_director_conflicts", role="executive", position="director_of_studies")
		teacher = self._create_user("portal_teacher_conflicts", role="teacher", position="teacher")
		academic_year, academic_class, ec = self._create_academic_class_bundle("D8A")
		other_year = AcademicYear.objects.create(
			name="2028-2029",
			start_date="2028-10-01",
			end_date="2029-07-31",
			is_active=False,
		)
		other_class = AcademicClass.objects.create(
			programme=self.programme,
			branch=self.branch,
			academic_year=other_year,
			level="D8B",
			study_level="LICENCE",
			is_active=True,
		)
		other_semester = Semester.objects.create(academic_class=other_class, number=1)
		other_ue = UE.objects.create(semester=other_semester, code="UE-D8B", title="UE D8B")
		other_ec = EC.objects.create(ue=other_ue, title="EC D8B", credit_required=3, coefficient=2)
		self.client.force_login(director)

		self.client.post(
			reverse("accounts_portal:director_create_schedule_event", args=[academic_class.id]),
			{
				"week_start": "2026-05-11",
				"planner_intent": "program",
				"date": "2026-05-11",
				"start_time": "08:00",
				"end_time": "10:00",
				"location": "Salle F10",
				"ec_id": ec.id,
				"teacher_id": teacher.id,
			},
			HTTP_HX_REQUEST="true",
		)

		class_conflict = self.client.post(
			reverse("accounts_portal:director_create_schedule_event", args=[academic_class.id]),
			{
				"week_start": "2026-05-11",
				"planner_intent": "program",
				"date": "2026-05-11",
				"start_time": "09:00",
				"end_time": "11:00",
				"location": "Salle F11",
				"ec_id": ec.id,
				"teacher_id": teacher.id,
			},
			HTTP_HX_REQUEST="true",
		)
		self.assertContains(class_conflict, "Classe occupee")

		teacher_room_conflict = self.client.post(
			reverse("accounts_portal:director_create_schedule_event", args=[other_class.id]),
			{
				"week_start": "2026-05-11",
				"planner_intent": "program",
				"date": "2026-05-11",
				"start_time": "09:00",
				"end_time": "11:00",
				"location": "Salle F10",
				"ec_id": other_ec.id,
				"teacher_id": teacher.id,
			},
			HTTP_HX_REQUEST="true",
		)
		self.assertContains(teacher_room_conflict, "Enseignant deja programme")
		self.assertContains(teacher_room_conflict, "Salle occupee")

	def test_director_schedule_event_respects_assignment_planned_hours(self):
		director = self._create_user("portal_director_hours_limit", role="executive", position="director_of_studies")
		teacher = self._create_user("portal_teacher_hours_limit", role="teacher", position="teacher")
		academic_year, academic_class, ec = self._create_academic_class_bundle("H1A")
		DirectorTeacherAssignment.objects.create(
			teacher=teacher,
			academic_class=academic_class,
			ec=ec,
			branch=self.branch,
			room_label="Salle H01",
			planned_hours="2.0",
			created_by=director,
		)
		self.client.force_login(director)

		first_response = self.client.post(
			reverse("accounts_portal:director_create_schedule_event", args=[academic_class.id]),
			{
				"week_start": "2026-05-11",
				"planner_intent": "program",
				"date": "2026-05-11",
				"start_time": "08:00",
				"end_time": "10:00",
				"location": "Salle H01",
				"ec_id": ec.id,
				"teacher_id": teacher.id,
			},
			HTTP_HX_REQUEST="true",
		)
		self.assertContains(first_response, "Cours programme sur la semaine.")

		overflow_response = self.client.post(
			reverse("accounts_portal:director_create_schedule_event", args=[academic_class.id]),
			{
				"week_start": "2026-05-11",
				"planner_intent": "program",
				"date": "2026-05-12",
				"start_time": "08:00",
				"end_time": "09:00",
				"location": "Salle H01",
				"ec_id": ec.id,
				"teacher_id": teacher.id,
			},
			HTTP_HX_REQUEST="true",
		)
		self.assertContains(overflow_response, "Heures depassees")

	def test_director_class_schedule_print_works(self):
		director = self._create_user("portal_director_print_class", role="executive", position="director_of_studies")
		teacher = self._create_user("portal_teacher_print_class", role="teacher", position="teacher")
		academic_year, academic_class, ec = self._create_academic_class_bundle("D9A")
		self._create_course_event(academic_class, academic_year, ec, teacher, hour=8)
		self.client.force_login(director)

		response = self.client.get(
			reverse("accounts_portal:schedule_class_print", args=[academic_class.id]),
			{"week_start": "2026-04-27", "period": "week"},
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Emploi du temps officiel de classe")
		self.assertContains(response, academic_class.display_name)

	def test_director_teacher_schedule_print_works(self):
		director = self._create_user("portal_director_print_teacher", role="executive", position="director_of_studies")
		teacher = self._create_user("portal_teacher_print_teacher", role="teacher", position="teacher")
		academic_year, academic_class, ec = self._create_academic_class_bundle("D10")
		self._create_course_event(academic_class, academic_year, ec, teacher, hour=10)
		self.client.force_login(director)

		response = self.client.get(
			reverse("accounts_portal:schedule_teacher_print", args=[teacher.id]),
			{"week_start": "2026-04-27", "period": "week"},
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Emploi du temps enseignant")
		self.assertContains(response, teacher.username)

	def test_portal_dashboard_renders_it_dashboard_from_single_entry(self):
		it_user = self._create_user("portal_it", position="it_support")
		self.client.force_login(it_user)
		response = self.client.get(reverse("accounts_portal:portal_dashboard"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Dashboard Informaticien")
		self.assertContains(response, "Support technique, acces, et sante du portail")
		self.assertContains(response, "Gestion des notes")
		self.assertContains(response, "Inscriptions sans affectation")

	def test_it_user_can_access_grade_dashboard(self):
		it_user = self._create_user("portal_it_grades", position="it_support")
		self.client.force_login(it_user)

		response = self.client.get(reverse("accounts_portal:admin_grade_dashboard"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Gestion des notes")

	def test_it_dashboard_keeps_notes_module_inside_dashboard(self):
		it_user = self._create_user("portal_it_notes_inline", position="it_support")
		academic_year, academic_class, _ec = self._create_academic_class_bundle("L1IT")
		semester = academic_class.semesters.get(number=1)
		self.client.force_login(it_user)

		response = self.client.get(
			reverse("accounts_portal:portal_dashboard"),
			{"class_id": academic_class.id, "semester_id": semester.id},
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Workspace Notes")
		self.assertContains(
			response,
			f'hx-get="{reverse("accounts_portal:it_notes_workspace")}?class_id={academic_class.id}&amp;semester_id={semester.id}"',
			html=False,
		)

	def test_it_notes_workspace_returns_filters_only_before_selection(self):
		it_user = self._create_user("portal_it_notes_workspace", position="it_support")
		self.client.force_login(it_user)

		response = self.client.get(reverse("accounts_portal:it_notes_workspace"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Workspace Notes")
		self.assertContains(response, "Choisir une classe")
		self.assertNotContains(response, "Maquette unique de reference")

	def test_it_notes_grid_htmx_returns_shared_maquette(self):
		it_user = self._create_user("portal_it_notes_grid", position="it_support")
		academic_year, academic_class, _ec = self._create_academic_class_bundle("L2IT")
		semester = academic_class.semesters.get(number=1)
		self.client.force_login(it_user)

		response = self.client.get(
			reverse("accounts_portal:it_notes_grid"),
			{"class_id": academic_class.id, "semester_id": semester.id},
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Gestion des notes")
		self.assertContains(response, f"Semestre {semester.number}")

	def test_it_notes_decisions_uses_official_annual_decision(self):
		it_user = self._create_user("portal_it_notes_decisions", position="it_support")
		student_user = self._create_user("portal_student_notes_decisions", role="student")
		student = self._create_student_record(student_user, inscription_status=Inscription.STATUS_ACTIVE)
		academic_year, academic_class, ec_one = self._create_academic_class_bundle("L2D")
		semester_one = academic_class.semesters.get(number=1)
		semester_two = Semester.objects.create(
			academic_class=academic_class,
			number=2,
			total_required_credits=Decimal("6.00"),
		)
		ue_two = UE.objects.create(semester=semester_two, code="RES-L2D", title="Compensation")
		ec_two = EC.objects.create(ue=ue_two, title="Matiere C", credit_required=Decimal("3.00"), coefficient=Decimal("3.00"))
		ec_three = EC.objects.create(ue=ue_two, title="Matiere D", credit_required=Decimal("3.00"), coefficient=Decimal("3.00"))
		AcademicEnrollment.objects.create(
			inscription=student.inscription,
			student=student_user,
			programme=self.programme,
			branch=self.branch,
			academic_year=academic_year,
			academic_class=academic_class,
		)
		enrollment = AcademicEnrollment.objects.get(student=student_user, academic_class=academic_class)
		# Seuil LICENCE = 12, marge d'admissibilite = 2.
		# S1 valide (moyenne 14 >= 12), S2 dans la marge d'admissibilite (moyenne 11 >= 12 - 2) -> ADMISSIBLE + dette.
		ECGrade.objects.create(enrollment=enrollment, ec=ec_one, normal_score=Decimal("14.00"))
		ECGrade.objects.create(enrollment=enrollment, ec=ec_two, normal_score=Decimal("11.00"))
		ECGrade.objects.create(enrollment=enrollment, ec=ec_three, normal_score=Decimal("11.00"))
		self.client.force_login(it_user)

		response = self.client.get(
			reverse("accounts_portal:it_notes_decisions"),
			{"class_id": academic_class.id},
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, student.full_name)
		self.assertContains(response, "ADMISSIBLE")
		self.assertEqual(
			AcademicDebt.objects.filter(enrollment=enrollment, status="pending").count(),
			2,
		)

	def test_it_notes_workflow_publishes_normal_session_then_unlocks_retake_modal(self):
		it_user = self._create_user("portal_it_notes_publish_normal", position="it_support")
		student_user = self._create_user("portal_student_notes_normal", role="student")
		student = self._create_student_record(student_user, inscription_status=Inscription.STATUS_ACTIVE)
		academic_year, academic_class, ec = self._create_academic_class_bundle("L2N")
		semester = academic_class.semesters.get(number=1)
		AcademicEnrollment.objects.create(
			inscription=student.inscription,
			student=student_user,
			programme=self.programme,
			branch=self.branch,
			academic_year=academic_year,
			academic_class=academic_class,
		)
		enrollment = AcademicEnrollment.objects.get(student=student_user, academic_class=academic_class)
		ECGrade.objects.create(enrollment=enrollment, ec=ec, normal_score=8, final_score=8, is_validated=False)
		self.client.force_login(it_user)

		response = self.client.post(
			reverse("accounts_portal:it_notes_workflow_action"),
			{
				"class_id": academic_class.id,
				"semester_id": semester.id,
				"action": "publier_session_normale",
			},
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(response.status_code, 200)
		semester.refresh_from_db()
		self.assertEqual(semester.status, Semester.STATUS_NORMAL_LOCKED)
		self.assertContains(response, "Session normale publiee")
		self.assertContains(response, "Ouvrir rattrapage")

		modal_response = self.client.get(
			reverse("accounts_portal:it_notes_retake_modal"),
			{"class_id": academic_class.id, "semester_id": semester.id},
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(modal_response.status_code, 200)
		self.assertContains(modal_response, "Verification avant activation")
		self.assertContains(modal_response, student.full_name)
		self.assertContains(modal_response, ec.title)

	def test_it_notes_retake_edit_is_blocked_for_validated_subject(self):
		it_user = self._create_user("portal_it_notes_retake_blocked", position="it_support")
		student_user = self._create_user("portal_student_notes_retake", role="student")
		student = self._create_student_record(student_user, inscription_status=Inscription.STATUS_ACTIVE)
		academic_year, academic_class, ec = self._create_academic_class_bundle("L2R")
		semester = academic_class.semesters.get(number=1)
		semester.status = Semester.STATUS_RETAKE_ENTRY
		semester.save(update_fields=["status"])
		AcademicEnrollment.objects.create(
			inscription=student.inscription,
			student=student_user,
			programme=self.programme,
			branch=self.branch,
			academic_year=academic_year,
			academic_class=academic_class,
		)
		enrollment = AcademicEnrollment.objects.get(student=student_user, academic_class=academic_class)
		ECGrade.objects.create(enrollment=enrollment, ec=ec, normal_score=13, final_score=13, is_validated=True)
		self.client.force_login(it_user)

		response = self.client.post(
			reverse("accounts_portal:save_grade"),
			{
				"enrollment_id": enrollment.id,
				"ec_id": ec.id,
				"session_type": "retake",
				"note": "15",
			},
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(response.status_code, 403)
		self.assertContains(response, "Seules les matieres non validees peuvent etre modifiees au rattrapage.")

	def test_it_structure_workspace_renders_academic_configuration_module(self):
		it_user = self._create_user("portal_it_structure_workspace", position="it_support")
		academic_year, academic_class, _ec = self._create_academic_class_bundle("L3IT")
		self.client.force_login(it_user)

		response = self.client.get(
			reverse("accounts_portal:it_structure_workspace"),
			{"class_id": academic_class.id},
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Parametrage academique")
		self.assertContains(response, "Classes, maquettes et affectations")
		self.assertContains(response, academic_class.display_name)

	def test_it_structure_action_can_create_academic_class(self):
		it_user = self._create_user("portal_it_structure_create", position="it_support")
		academic_year = AcademicYear.objects.create(
			name="26-27-IT",
			start_date="2026-10-01",
			end_date="2027-07-31",
			is_active=False,
		)
		self.client.force_login(it_user)

		response = self.client.post(
			reverse("accounts_portal:it_structure_action"),
			{
				"action": "save_class",
				"programme_id": self.programme.id,
				"academic_year_id": academic_year.id,
				"level": "L4",
				"validation_threshold": "10",
			},
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(response.status_code, 200)
		created_class = AcademicClass.objects.get(programme=self.programme, academic_year=academic_year, level="L4", branch=self.branch)
		self.assertContains(response, "Classe academique enregistree.")
		self.assertTrue(created_class.semesters.filter(number=1).exists())
		self.assertTrue(created_class.semesters.filter(number=2).exists())

	def test_it_structure_action_keeps_modal_open_on_validation_error(self):
		it_user = self._create_user("portal_it_structure_modal_error", position="it_support")
		academic_year = AcademicYear.objects.create(
			name="26-27E",
			start_date="2026-10-01",
			end_date="2027-07-31",
			is_active=False,
		)
		self.client.force_login(it_user)

		response = self.client.post(
			reverse("accounts_portal:it_structure_action"),
			{
				"action": "save_class",
				"section": "classes",
				"programme_id": self.programme.id,
				"academic_year_id": academic_year.id,
				"level": "L4",
				"validation_threshold": "dix",
			},
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.headers.get("HX-Retarget"), "#it-modal-root")
		self.assertNotIn("HX-Trigger", response.headers)
		self.assertContains(response, "Seuil de validation invalide.")
		self.assertContains(response, "Enregistrer la classe")
		self.assertContains(response, 'value="dix"', html=False)

	def test_it_import_workspace_renders_professional_excel_panel(self):
		it_user = self._create_user("portal_it_import_panel", position="it_support")
		_academic_year, academic_class, _ec = self._create_academic_class_bundle("L4I")
		semester = academic_class.semesters.get(number=1)
		self.client.force_login(it_user)

		response = self.client.get(
			reverse("accounts_portal:it_import_workspace"),
			{"class_id": academic_class.id, "semester_id": semester.id},
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Modele Excel officiel")
		self.assertContains(response, "Verifier et importer")
		self.assertContains(response, "ENROLLMENT_ID")
		self.assertContains(response, "MATRICULE")
		self.assertContains(response, "Maquette Excel")

	def test_it_import_upload_imports_template_by_enrollment_id(self):
		it_user = self._create_user("portal_it_import_upload", position="it_support")
		student_user = self._create_user("portal_it_import_student", role="student")
		student = self._create_student_record(student_user, inscription_status=Inscription.STATUS_ACTIVE)
		academic_year, academic_class, ec = self._create_academic_class_bundle("L4U")
		semester = academic_class.semesters.get(number=1)
		enrollment = AcademicEnrollment.objects.create(
			inscription=student.inscription,
			student=student_user,
			programme=self.programme,
			branch=self.branch,
			academic_year=academic_year,
			academic_class=academic_class,
		)
		self.client.force_login(it_user)

		template_response = self.client.get(
			reverse("academics:download_import_template", args=[academic_class.id, semester.id])
		)
		self.assertEqual(template_response.status_code, 200)

		from io import BytesIO
		from openpyxl import load_workbook

		workbook_buffer = BytesIO(template_response.content)
		workbook = load_workbook(workbook_buffer)
		sheet = workbook.active
		self.assertEqual(sheet["A5"].value, "ENROLLMENT_ID")
		self.assertEqual(sheet["B5"].value, "MATRICULE")
		self.assertTrue(str(sheet["E5"].value).startswith("NOTE /20 - "))
		self.assertEqual(str(sheet["A6"].value), str(enrollment.id))
		self.assertEqual(sheet["E6"].fill.fgColor.rgb, "00FEF3C7")
		sheet["E6"] = "14,5"
		output = BytesIO()
		workbook.save(output)
		output.seek(0)

		response = self.client.post(
			reverse("accounts_portal:it_import_upload"),
			{
				"class_id": academic_class.id,
				"semester_id": semester.id,
				"file": SimpleUploadedFile(
					"notes.xlsx",
					output.getvalue(),
					content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
				),
			},
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "1 note(s) importee(s)")
		grade = ECGrade.objects.get(enrollment=enrollment, ec=ec)
		self.assertEqual(grade.normal_score, Decimal("14.5"))

	def test_it_archives_class_and_restores_it(self):
		it_user = self._create_user("portal_it_archive", position="it_support")
		student_user = self._create_user("portal_archive_student", role="student")
		inactive_user = self._create_user("portal_archive_inactive", role="student")
		student = self._create_student_record(student_user, inscription_status=Inscription.STATUS_ACTIVE)
		inactive_student = self._create_student_record(inactive_user, inscription_status=Inscription.STATUS_ACTIVE)
		inactive_student.is_active = False
		inactive_student.save(update_fields=["is_active"])
		academic_year, academic_class, ec = self._create_academic_class_bundle("L4A")
		enrollment = AcademicEnrollment.objects.create(
			inscription=student.inscription,
			student=student_user,
			programme=self.programme,
			branch=self.branch,
			academic_year=academic_year,
			academic_class=academic_class,
		)
		AcademicEnrollment.objects.create(
			inscription=inactive_student.inscription,
			student=inactive_user,
			programme=self.programme,
			branch=self.branch,
			academic_year=academic_year,
			academic_class=academic_class,
		)
		ECGrade.objects.create(enrollment=enrollment, ec=ec, normal_score=Decimal("13.00"))
		Payment.objects.create(
			inscription=student.inscription,
			amount=10000,
			method=Payment.METHOD_CASH,
			status=Payment.STATUS_PENDING,
		)
		self.client.force_login(it_user)

		preview = self.client.get(
			reverse("accounts_portal:it_archives_workspace"),
			{"class_id": academic_class.id},
			HTTP_HX_REQUEST="true",
		)
		self.assertEqual(preview.status_code, 200)
		self.assertContains(preview, "Archiver maintenant")
		self.assertContains(preview, "Notes")

		response = self.client.post(
			reverse("accounts_portal:it_archives_action"),
			{
				"action": "archive_class",
				"class_id": academic_class.id,
				"reason": "Cloture test",
			},
			HTTP_HX_REQUEST="true",
		)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Classe archivee avec succes.")
		academic_class.refresh_from_db()
		enrollment.refresh_from_db()
		student.refresh_from_db()
		student.inscription.refresh_from_db()
		self.assertTrue(academic_class.is_archived)
		self.assertFalse(academic_class.is_active)
		self.assertTrue(enrollment.is_archived)
		self.assertFalse(enrollment.is_active)
		self.assertTrue(student.inscription.is_archived)
		self.assertFalse(student.is_active)
		batch = ArchiveBatch.objects.get(academic_class=academic_class)
		self.assertEqual(batch.grades_count, 1)
		self.assertEqual(batch.payments_count, 1)
		self.assertIn(str(inactive_student.id), batch.snapshot["state"]["students"])
		self.assertFalse(batch.snapshot["state"]["students"][str(inactive_student.id)]["is_active"])

		restore = self.client.post(
			reverse("accounts_portal:it_archives_action"),
			{"action": "restore", "batch_id": batch.id},
			HTTP_HX_REQUEST="true",
		)
		self.assertEqual(restore.status_code, 200)
		self.assertContains(restore, "Archive restauree.")
		academic_class.refresh_from_db()
		enrollment.refresh_from_db()
		student.refresh_from_db()
		inactive_student.refresh_from_db()
		student.inscription.refresh_from_db()
		batch.refresh_from_db()
		self.assertFalse(academic_class.is_archived)
		self.assertTrue(academic_class.is_active)
		self.assertFalse(enrollment.is_archived)
		self.assertTrue(enrollment.is_active)
		self.assertFalse(student.inscription.is_archived)
		self.assertTrue(student.is_active)
		self.assertFalse(inactive_student.is_active)
		self.assertEqual(batch.status, ArchiveBatch.STATUS_RESTORED)

	def test_it_dashboard_can_toggle_scoped_staff_account(self):
		it_user = self._create_user("portal_it_toggle", position="it_support")
		target_user = self._create_user("portal_staff_target", position="secretary")
		self.client.force_login(it_user)

		response = self.client.post(
			reverse("accounts_portal:it_toggle_account"),
			{
				"target_user_id": target_user.id,
				"kind": "staff",
				"id": target_user.id,
				"q": target_user.username,
			},
		)

		self.assertRedirects(
			response,
			f"{reverse('accounts_portal:portal_dashboard')}?q={target_user.username}&kind=staff&id={target_user.id}#diagnostics",
			fetch_redirect_response=False,
		)
		target_user.refresh_from_db()
		self.assertFalse(target_user.is_active)
		self.assertTrue(
			SupportAuditLog.objects.filter(
				actor=it_user,
				target_user=target_user,
				action_type=SupportAuditLog.ACTION_ACCOUNT_DEACTIVATED,
			).exists()
		)

	def test_it_dashboard_can_reset_scoped_user_password(self):
		it_user = self._create_user("portal_it_reset", position="it_support")
		target_user = self._create_user("portal_staff_reset", position="secretary")
		self.client.force_login(it_user)

		response = self.client.post(
			reverse("accounts_portal:it_reset_password"),
			{
				"target_user_id": target_user.id,
				"kind": "staff",
				"id": target_user.id,
				"q": target_user.username,
			},
		)

		self.assertEqual(response.status_code, 302)
		session_feedback = self.client.session.get("it_support_feedback")
		self.assertIsNotNone(session_feedback)
		self.assertTrue(session_feedback.get("password"))
		target_user.refresh_from_db()
		self.assertTrue(target_user.check_password(session_feedback["password"]))
		self.assertTrue(
			SupportAuditLog.objects.filter(
				actor=it_user,
				target_user=target_user,
				action_type=SupportAuditLog.ACTION_PASSWORD_RESET,
			).exists()
		)

	def test_it_dashboard_rejects_cross_branch_account_action(self):
		it_user = self._create_user("portal_it_scope", position="it_support")
		other_branch = Branch.objects.create(
			name="Annexe Hors Scope",
			code="AHS",
			slug="annexe-hors-scope",
		)
		target_user = self._create_user("portal_staff_other_branch", position="secretary")
		target_user.profile.branch = other_branch
		target_user.profile.save(update_fields=["branch", "updated_at"])
		self.client.force_login(it_user)

		response = self.client.post(
			reverse("accounts_portal:it_toggle_account"),
			{
				"target_user_id": target_user.id,
				"kind": "staff",
				"id": target_user.id,
				"q": target_user.username,
			},
		)

		self.assertEqual(response.status_code, 302)
		target_user.refresh_from_db()
		self.assertTrue(target_user.is_active)
		self.assertFalse(
			SupportAuditLog.objects.filter(
				actor=it_user,
				target_user=target_user,
			).exists()
		)

	def test_legacy_supervisor_route_redirects_to_single_entry(self):
		supervisor = self._create_user("portal_supervisor_legacy", position="academic_supervisor")
		self.client.force_login(supervisor)
		response = self.client.get(reverse("accounts_portal:portal_supervisor"))
		self.assertRedirects(
			response,
			reverse("accounts_portal:portal_dashboard"),
			fetch_redirect_response=False,
		)

	def test_supervisor_dashboard_marks_student_attendance(self):
		supervisor = self._create_user("portal_supervisor_att_student", position="academic_supervisor")
		teacher = self._create_user("portal_teacher_att_student", role="teacher", position="teacher")
		student_user = self._create_user("portal_student_att", role="student")
		student = self._create_student_record(student_user, inscription_status=Inscription.STATUS_ACTIVE)
		academic_year, academic_class, ec = self._create_academic_class_bundle("L1A")
		AcademicEnrollment.objects.create(
			inscription=student.inscription,
			student=student_user,
			programme=self.programme,
			branch=self.branch,
			academic_year=academic_year,
			academic_class=academic_class,
		)
		schedule_event = self._create_course_event(academic_class, academic_year, ec, teacher, hour=8)
		self.client.force_login(supervisor)

		response = self.client.post(
			reverse("accounts_portal:supervisor_mark_student_attendance"),
			{
				"schedule_event_id": schedule_event.id,
				"student_id": student.id,
				"status": StudentAttendance.STATUS_LATE,
				"arrival_time": "08:17",
				"justification": "Transport",
			},
		)

		self.assertRedirects(
			response,
			f"{reverse('accounts_portal:portal_dashboard')}#absences",
			fetch_redirect_response=False,
		)
		attendance = StudentAttendance.objects.get(student=student, schedule_event=schedule_event)
		self.assertEqual(attendance.status, StudentAttendance.STATUS_LATE)
		self.assertEqual(attendance.branch, self.branch)
		self.assertEqual(attendance.recorded_by, supervisor)

	def test_supervisor_dashboard_marks_teacher_attendance(self):
		supervisor = self._create_user("portal_supervisor_att_teacher", position="academic_supervisor")
		teacher = self._create_user("portal_teacher_att_teacher", role="teacher", position="teacher")
		academic_year, academic_class, ec = self._create_academic_class_bundle("L1B")
		schedule_event = self._create_course_event(academic_class, academic_year, ec, teacher, hour=10)
		self.client.force_login(supervisor)

		response = self.client.post(
			reverse("accounts_portal:supervisor_mark_teacher_attendance"),
			{
				"schedule_event_id": schedule_event.id,
				"status": TeacherAttendance.STATUS_ABSENT,
				"justification": "Indisponible",
			},
		)

		self.assertRedirects(
			response,
			f"{reverse('accounts_portal:portal_dashboard')}#absences",
			fetch_redirect_response=False,
		)
		attendance = TeacherAttendance.objects.get(teacher=teacher, schedule_event=schedule_event)
		self.assertEqual(attendance.status, TeacherAttendance.STATUS_ABSENT)
		self.assertEqual(attendance.recorded_by, supervisor)

	def test_supervisor_dashboard_creates_or_updates_lesson_log(self):
		supervisor = self._create_user("portal_supervisor_log", position="academic_supervisor")
		teacher = self._create_user("portal_teacher_log", role="teacher", position="teacher")
		academic_year, academic_class, ec = self._create_academic_class_bundle("L1C")
		schedule_event = self._create_course_event(academic_class, academic_year, ec, teacher, hour=14)
		self.client.force_login(supervisor)

		response = self.client.post(
			reverse("accounts_portal:supervisor_save_lesson_log"),
			{
				"schedule_event_id": schedule_event.id,
				"status": LessonLog.STATUS_DONE,
				"content": "Fonctions et derives.",
				"homework": "Serie 1",
				"observations": "Classe calme",
			},
		)

		self.assertRedirects(
			response,
			f"{reverse('accounts_portal:portal_dashboard')}#courses",
			fetch_redirect_response=False,
		)
		lesson_log = LessonLog.objects.get(schedule_event=schedule_event)
		self.assertEqual(lesson_log.status, LessonLog.STATUS_DONE)
		self.assertEqual(lesson_log.created_by, supervisor)
		self.assertEqual(lesson_log.content, "Fonctions et derives.")


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


class FixUserPositionsCommandTests(TestCase):
	def setUp(self):
		self.branch = Branch.objects.create(
			name="Annexe Position",
			code="APS",
			slug="annexe-position",
		)

	def test_fix_user_positions_sets_detectable_position(self):
		user = USER_MANAGER.create_user(
			username="position_finance",
			email="position_finance@example.com",
			password="pass1234",
			is_staff=True,
		)
		group, _ = Group.objects.get_or_create(name="finance_agents")
		user.groups.add(group)
		PaymentAgent.objects.create(user=user, branch=self.branch, is_active=True)

		profile = user.profile
		profile.position = ""
		profile.save(update_fields=["position", "updated_at"])

		call_command("fix_user_positions")

		user.refresh_from_db()
		self.assertEqual(user.profile.position, "payment_agent")


class ProfileCenterTests(TestCase):
	def setUp(self):
		self.user = USER_MANAGER.create_user(
			username="profil_central",
			email="profil_central@example.com",
			password="pass1234",
			first_name="Avant",
			last_name="Profil",
		)
		self.cycle = Cycle.objects.create(
			name="Licence Profil",
			theme="primary",
			min_duration_years=1,
			max_duration_years=3,
		)
		self.diploma = Diploma.objects.create(name="Diplome Profil", level="superieur")
		self.filiere = Filiere.objects.create(name="Filiere Profil")
		self.branch = Branch.objects.create(
			name="Annexe Profil Centre",
			code="APC",
			slug="annexe-profil-centre",
		)
		self.programme = Programme.objects.create(
			title="Programme Profil Centre",
			filiere=self.filiere,
			cycle=self.cycle,
			diploma_awarded=self.diploma,
			duration_years=3,
			short_description="Programme de test profil",
			description="Programme de test profil",
		)

	def test_edit_profile_updates_identity_and_contact_fields(self):
		self.client.force_login(self.user)

		response = self.client.post(
			reverse("accounts:edit_profile"),
			{
				"first_name": "Awa",
				"last_name": "Traore",
				"bio": "Responsable de parcours",
				"location": "Bamako",
				"phone": "+22370000000",
				"address": "Hamdallaye ACI",
				"main_domain": "Administration",
				"website": "https://esfe.example.com",
			},
		)

		self.assertRedirects(response, reverse("accounts:profile"), fetch_redirect_response=False)
		self.user.refresh_from_db()
		self.assertEqual(self.user.first_name, "Awa")
		self.assertEqual(self.user.last_name, "Traore")
		self.assertEqual(self.user.profile.phone, "+22370000000")
		self.assertEqual(self.user.profile.address, "Hamdallaye ACI")
		self.assertEqual(self.user.profile.main_domain, "Administration")

	def test_edit_preferences_creates_and_updates_unified_preferences(self):
		self.client.force_login(self.user)
		AccountSupportState.objects.create(
			user=self.user,
			is_blocked=True,
			must_change_password=True,
		)

		response = self.client.post(
			reverse("accounts:edit_preferences"),
			{
				"notify_email": "on",
				"notify_in_app": "on",
				"ui_compact_mode": "on",
			},
		)

		self.assertRedirects(response, reverse("accounts:edit_preferences"), fetch_redirect_response=False)
		preference = UserPreference.objects.get(user=self.user)
		self.assertTrue(preference.notify_email)
		self.assertTrue(preference.notify_in_app)
		self.assertFalse(preference.notify_sms)
		self.assertFalse(preference.ui_sidebar_collapsed)
		self.assertTrue(preference.ui_compact_mode)
		self.assertFalse(preference.ui_autorefresh)

	def test_profile_settings_htmx_renders_preference_summary(self):
		self.client.force_login(self.user)
		UserPreference.objects.create(
			user=self.user,
			notify_email=False,
			notify_in_app=True,
			ui_compact_mode=True,
		)
		self.user.profile.phone = "65000000"
		self.user.profile.address = "Kalaban"
		self.user.profile.save(update_fields=["phone", "address", "updated_at"])

		response = self.client.get(
			reverse("accounts:profile_settings"),
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Notifications et interface")
		self.assertContains(response, "65000000")
		self.assertContains(response, "Kalaban")

	def test_student_settings_updates_central_phone_profile(self):
		self.user.profile.role = "student"
		self.user.profile.save(update_fields=["role", "updated_at"])
		candidature = Candidature.objects.create(
			first_name="Avant",
			last_name="Profil",
			birth_date="2001-01-01",
			birth_place="Bamako",
			gender="male",
			email=self.user.email,
			phone="61000000",
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
		Student.objects.create(user=self.user, inscription=inscription, matricule="MAT-PC-001")
		self.client.force_login(self.user)

		response = self.client.post(
			reverse("portal_student:update_settings_profile"),
			{
				"email": "profil_central@example.com",
				"phone": "+22376123456",
			},
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(response.status_code, 200)
		self.user.refresh_from_db()
		candidature.refresh_from_db()
		self.assertEqual(candidature.phone, "+22376123456")
		self.assertEqual(self.user.profile.phone, "+22376123456")

