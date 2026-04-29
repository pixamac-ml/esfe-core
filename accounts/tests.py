from datetime import datetime
from typing import Any, cast

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from branches.models import Branch
from payments.models import PaymentAgent
from students.models import Student, StudentAttendance, TeacherAttendance
from inscriptions.models import Inscription
from admissions.models import Candidature
from formations.models import Programme, Cycle, Diploma, Filiere
from academics.models import AcademicClass, AcademicEnrollment, AcademicScheduleEvent, AcademicYear, EC, LessonLog, Semester, UE

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
from portal.models import SupportAuditLog


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
		academic_year = AcademicYear.objects.create(
			name=f"25-26-{level}",
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

		self.assertEqual(
			get_post_login_portal_url(student),
			reverse("accounts_portal:portal_dashboard"),
		)
		self.assertEqual(
			get_post_login_portal_url(staff_user),
			reverse("accounts_portal:portal_dashboard"),
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
			f"{reverse('accounts_portal:portal_dashboard')}#attendance",
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
			f"{reverse('accounts_portal:portal_dashboard')}#attendance",
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

