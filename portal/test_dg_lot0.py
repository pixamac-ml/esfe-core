from datetime import date
from unittest.mock import patch
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from academics.models import AcademicClass, AcademicYear
from accounts.models import BranchMonthlyClosure, FinancialAuditLog, Profile
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme
from portal.dg.executive_actions import nominate_branch_manager, validate_closure
from portal.dg.forms import DgRecruitmentForm, DgStaffLifecycleForm
from portal.dg.rh_service import apply_staff_lifecycle_action, create_staff_from_recruitment
from portal.dg.selectors import get_dg_base_querysets
from portal.dg.services import _build_branch_summaries
from portal.models import SupportAuditLog


class DgLotZeroTests(TestCase):
    """Regression tests for the canonical DG context and its critical actions."""

    @classmethod
    def setUpTestData(cls):
        cls.year_a = AcademicYear.objects.create(
            name="2040-2041", start_date=date(2040, 10, 1), end_date=date(2041, 7, 31), is_active=True,
        )
        cls.year_b = AcademicYear.objects.create(
            name="2039-2040", start_date=date(2039, 10, 1), end_date=date(2040, 7, 31), is_active=False,
        )
        cls.branch_x = Branch.objects.create(name="Annexe Scope X", code="SCX", slug="scope-x")
        cls.branch_y = Branch.objects.create(name="Annexe Scope Y", code="SCY", slug="scope-y")
        cycle = Cycle.objects.create(name="Cycle Scope", min_duration_years=1, max_duration_years=3)
        diploma = Diploma.objects.create(name="Diplôme Scope", level="superieur")
        filiere = Filiere.objects.create(name="Filière Scope")
        programme = Programme.objects.create(
            title="Programme Scope", filiere=filiere, cycle=cycle, diploma_awarded=diploma,
            duration_years=3, short_description="Scope", description="Scope DG",
        )
        cls.class_ax = AcademicClass.objects.create(
            name="Classe A-X", programme=programme, branch=cls.branch_x, academic_year=cls.year_a,
            level="L1", study_level="LICENCE",
        )
        AcademicClass.objects.create(
            name="Classe A-Y", programme=programme, branch=cls.branch_y, academic_year=cls.year_a,
            level="L1", study_level="LICENCE",
        )
        AcademicClass.objects.create(
            name="Classe B-X", programme=programme, branch=cls.branch_x, academic_year=cls.year_b,
            level="L1", study_level="LICENCE",
        )
        users = get_user_model()
        cls.dg = users.objects.create_user(username="lot0-dg", password="password")
        cls.non_dg = users.objects.create_user(username="lot0-non-dg", password="password")
        cls.manager = users.objects.create_user(username="lot0-manager", password="password", is_staff=True)
        Profile.objects.filter(user=cls.dg).update(user_type="staff", position="executive_director")
        Profile.objects.filter(user=cls.manager).update(
            user_type="staff", position="branch_manager", branch=cls.branch_x, employment_status="active",
        )

    def setUp(self):
        self.client.force_login(self.dg)

    def _set_branch_scope(self, branch=None, year=None, global_mode=False):
        params = {"academic_year_id": (year or self.year_a).id}
        if branch is not None:
            params["scope_branch_id"] = branch.id
        elif global_mode:
            params["scope_branch_id"] = ""
        response = self.client.get(reverse("accounts_portal:portal_dg"), params)
        self.assertEqual(response.status_code, 200)

    def test_scope_isolates_year_and_branch_and_global_mode_combines_only_selected_year(self):
        scoped = get_dg_base_querysets([self.branch_x.id], academic_year=self.year_a)
        self.assertEqual(list(scoped["classes"]), [self.class_ax])

        global_mode = get_dg_base_querysets([self.branch_x.id, self.branch_y.id], academic_year=self.year_a)
        self.assertEqual(set(global_mode["classes"].values_list("name", flat=True)), {"Classe A-X", "Classe A-Y"})
        self.assertNotIn("Classe B-X", global_mode["classes"].values_list("name", flat=True))

        self._set_branch_scope(self.branch_x)
        dashboard = self.client.get(reverse("accounts_portal:portal_dg"))
        self.assertEqual(dashboard.context["total_classes"], 1)
        self.assertEqual(dashboard.context["dashboard_mode"], "branch")

        self._set_branch_scope(global_mode=True)
        dashboard = self.client.get(reverse("accounts_portal:portal_dg"))
        self.assertEqual(dashboard.context["total_classes"], 2)
        self.assertEqual(dashboard.context["dashboard_mode"], "global")

    def test_dg_shell_uses_the_ui_core_workspace_loading_contract(self):
        response = self.client.get(reverse("accounts_portal:portal_dg"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "portal/dg/dashboard_ui_core.html")
        self.assertContains(response, 'data-ui-core="loading-overlay"')
        self.assertEqual(response.context["dashboard_period_scope_label"], "Veille admissions : 30 jours")

    def test_lot1_domain_and_subsection_urls_are_reproducible(self):
        dashboard = self.client.get(
            reverse("accounts_portal:portal_dg"),
            {"domain": "finance", "section": "coupons", "academic_year_id": self.year_a.id},
        )

        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.context["dg_active_domain"], "finance")
        self.assertEqual(dashboard.context["dg_active_section"], "coupons")
        self.assertEqual(dashboard.context["dashboard_shell"]["active_section"], "finance")

        workspace = self.client.get(
            reverse("accounts_portal:dg_section", kwargs={"section": "finance"}),
            {"domain": "finance", "academic_year_id": self.year_a.id},
        )
        self.assertEqual(workspace.status_code, 200)
        self.assertTemplateUsed(workspace, "portal/dg/partials/section_shell.html")
        self.assertContains(workspace, 'id="dg-domain-subnav-finance-tab"')
        self.assertContains(workspace, "Synthèse")
        self.assertContains(workspace, "Coupons")
        self.assertContains(workspace, 'hx-target="#executive-workspace"')
        self.assertContains(workspace, 'hx-sync="#executive-workspace:replace"')
        self.assertNotContains(workspace, 'id="dg-domain-loading"')

        subcontent = self.client.get(
            reverse("accounts_portal:dg_section", kwargs={"section": "coupons"}),
            {"domain": "finance", "academic_year_id": self.year_a.id, "_subsection": "1"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(subcontent.status_code, 200)
        self.assertTemplateUsed(subcontent, "portal/dg/partials/coupons/list.html")
        self.assertNotContains(subcontent, 'id="dg-domain-subnav"')
        self.assertIn("section=coupons", subcontent["HX-Push-Url"])

    def test_lot1_sidebar_groups_executive_domains_and_real_badges(self):
        response = self.client.get(
            reverse("accounts_portal:portal_dg"),
            {"academic_year_id": self.year_a.id},
        )

        self.assertContains(response, "Commandement")
        self.assertContains(response, "Pilotage institutionnel")
        self.assertContains(response, "Gouvernance")
        self.assertContains(response, "Cockpit DG")
        self.assertContains(response, 'data-nav-key="finance"')
        self.assertContains(response, 'data-nav-key="gouvernance"')

    def test_lot1_cockpit_is_targeted_and_exposes_scoped_drilldowns(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(
                reverse("accounts_portal:dg_section", kwargs={"section": "overview"}),
                {"academic_year_id": self.year_a.id},
            )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "portal/dg/partials/section_shell.html")
        # The request includes session/authentication, the common portal
        # context and rendering work.  Keep the full DG cockpit request under
        # a controlled 50-query ceiling; the prior full dashboard builder
        # additionally built schedule, analytics and RH details here.
        self.assertLessEqual(len(queries), 50)
        self.assertContains(response, "À votre attention")
        self.assertContains(response, "Repères de décision")
        self.assertContains(response, f"scope_branch_id={self.branch_x.id}")

    def test_lot1_navigation_serializes_workspace_responses(self):
        javascript = (settings.BASE_DIR / "static" / "src" / "js" / "portal" / "dg_dashboard.js").read_text(encoding="utf-8")
        shell_javascript = (settings.BASE_DIR / "static" / "src" / "js" / "portal" / "certified_dashboard_shell.js").read_text(encoding="utf-8")

        self.assertIn("_workspace_request", javascript)
        self.assertIn("htmx:beforeSwap", javascript)
        self.assertIn("requestDomain", javascript)
        self.assertIn("_workspace_request", shell_javascript)

    def test_lot1_rejects_unknown_section_before_building_context(self):
        response = self.client.get(reverse("accounts_portal:dg_section", kwargs={"section": "not-a-section"}))
        self.assertEqual(response.status_code, 400)

    def test_branch_summary_uses_a_fixed_query_budget(self):
        base = get_dg_base_querysets([self.branch_x.id, self.branch_y.id], academic_year=self.year_a)

        with CaptureQueriesContext(connection) as queries:
            summaries = _build_branch_summaries([self.branch_x, self.branch_y], base, academic_year=self.year_a)

        self.assertEqual(len(summaries), 2)
        self.assertLessEqual(len(queries), 7)

    def test_drawer_export_and_protected_routes_respect_scope(self):
        self._set_branch_scope(self.branch_x)
        denied_drawer = self.client.get(
            reverse("accounts_portal:dg_drawer"), {"kind": "branch", "branch_id": self.branch_y.id},
        )
        self.assertEqual(denied_drawer.status_code, 403)

        export = self.client.get(reverse("accounts_portal:dg_export"), {"kind": "finance"})
        body = export.content.decode()
        self.assertIn(self.branch_x.name, body)
        self.assertNotIn(self.branch_y.name, body)

        self.client.force_login(self.non_dg)
        for route_name in ("dg_drawer", "dg_export"):
            self.assertEqual(self.client.get(reverse(f"accounts_portal:{route_name}")).status_code, 403)
        self.assertEqual(self.client.post(reverse("accounts_portal:dg_exec_action"), {"action": "validate_closure"}).status_code, 403)

    def test_schedule_section_honors_the_requested_class_and_week(self):
        response = self.client.get(
            reverse("accounts_portal:dg_section", kwargs={"section": "schedule"}),
            {
                "academic_year_id": self.year_a.id,
                "scope_branch_id": self.branch_x.id,
                "class_id": self.class_ax.id,
                "week_start": "2041-06-04",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["schedule"]["selected_class_id"], str(self.class_ax.id))
        self.assertEqual(response.context["schedule"]["week_start"], date(2041, 6, 3))

        javascript = (settings.BASE_DIR / "static" / "src" / "js" / "portal" / "dg_dashboard.js").read_text(encoding="utf-8")
        self.assertIn('requestSection("schedule", true, { class_id: classId || null })', javascript)
        self.assertIn('requestSection("schedule", true, { week_start: weekStart || null })', javascript)

    def test_chart_sections_use_the_ui_core_chart_contract(self):
        params = {"academic_year_id": self.year_a.id, "scope_branch_id": self.branch_x.id}
        for section, chart_id in (
            ("analytics", "dgMonthlyChart"),
            ("alerts", "dgRiskChart"),
            ("finance", "dgFinanceChart"),
        ):
            with self.subTest(section=section):
                response = self.client.get(reverse("accounts_portal:dg_section", kwargs={"section": section}), params)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f'id="{chart_id}"')
                self.assertContains(response, 'data-ui-chart=')

    def test_alert_modal_uses_the_scoped_alert_kind(self):
        self._set_branch_scope(self.branch_x)

        response = self.client.get(
            reverse("accounts_portal:dg_modal"),
            {"modal": "alert", "id": "999999"},
        )

        self.assertEqual(response.status_code, 403)

    def test_dg_cannot_request_academic_year_deletion(self):
        self._set_branch_scope(self.branch_x, year=self.year_b)

        response = self.client.post(
            reverse("accounts_portal:dg_exec_action"),
            {
                "action": "delete_academic_year",
                "academic_year_id": self.year_b.id,
                "confirmation": self.year_b.name,
                "confirmed": "1",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertTrue(AcademicYear.objects.filter(pk=self.year_b.pk).exists())

    def test_confirmation_and_transactional_financial_audit(self):
        closure = BranchMonthlyClosure.objects.create(branch=self.branch_x, period_month=date(2041, 6, 1))
        self._set_branch_scope(self.branch_x)

        no_confirmation = self.client.post(
            reverse("accounts_portal:dg_exec_action"), {"action": "validate_closure", "closure_id": closure.id},
        )
        self.assertEqual(no_confirmation.status_code, 400)
        self.assertFalse(FinancialAuditLog.objects.filter(target_id=closure.id).exists())

        confirmed = self.client.post(
            reverse("accounts_portal:dg_exec_action"),
            {"action": "validate_closure", "closure_id": closure.id, "confirmed": "1", "reason": "Pièces contrôlées."},
        )
        self.assertEqual(confirmed.status_code, 200)
        closure.refresh_from_db()
        self.assertEqual(closure.status, BranchMonthlyClosure.STATUS_VALIDATED)
        self.assertTrue(FinancialAuditLog.objects.filter(target_id=closure.id, action_type="monthly_closure_validated").exists())

        closure_y = BranchMonthlyClosure.objects.create(branch=self.branch_y, period_month=date(2041, 6, 1))
        with self.assertRaises(ValidationError):
            validate_closure(
                actor=self.dg, closure_id=closure_y.id, scope_branch_ids=[self.branch_x.id], academic_year=self.year_a,
            )
        self.assertFalse(FinancialAuditLog.objects.filter(target_id=closure_y.id).exists())

    def test_sensitive_action_confirmation_modal_cannot_preview_out_of_scope_target(self):
        closure = BranchMonthlyClosure.objects.create(branch=self.branch_x, period_month=date(2041, 5, 1))
        self._set_branch_scope(self.branch_x)
        preview = self.client.get(
            reverse("accounts_portal:dg_modal"),
            {"modal": "executive_action", "action": "validate_closure", "closure_id": closure.id},
        )
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, "Confirmation requise")

        other = BranchMonthlyClosure.objects.create(branch=self.branch_y, period_month=date(2041, 5, 1))
        denied = self.client.get(
            reverse("accounts_portal:dg_modal"),
            {"modal": "executive_action", "action": "validate_closure", "closure_id": other.id},
        )
        self.assertEqual(denied.status_code, 403)

    def test_manager_nomination_is_scoped_and_audited(self):
        result = nominate_branch_manager(
            actor=self.dg, branch_id=self.branch_x.id, user_id=self.manager.id, scope_branch_ids=[self.branch_x.id], reason="Vacance du poste.",
        )
        self.assertTrue(result["ok"])
        self.branch_x.refresh_from_db()
        self.assertEqual(self.branch_x.manager_id, self.manager.id)
        self.assertTrue(SupportAuditLog.objects.filter(action_type=SupportAuditLog.ACTION_MANAGER_NOMINATED, branch=self.branch_x).exists())

        with self.assertRaises(ValidationError):
            nominate_branch_manager(
                actor=self.dg, branch_id=self.branch_y.id, user_id=self.manager.id, scope_branch_ids=[self.branch_x.id],
            )

    def _recruitment_form(self, *, access):
        data = {
            "first_name": "Awa",
            "last_name": "Traore",
            "professional_email": "awa.lot0@example.test",
            "branch": str(self.branch_x.id),
            "position": "secretary",
            "salary_base": "100000",
        }
        if access:
            data.update({"generate_access": "on", "send_access_email": "on"})
        form = DgRecruitmentForm(data)
        self.assertTrue(form.is_valid(), form.errors)
        return form

    def test_recruitment_controls_access_and_uses_a_secure_activation_link(self):
        request = RequestFactory().post("/portal/dg/recruit-staff/", HTTP_HOST="testserver")
        with patch("portal.dg.rh_service.send_mail") as send_mail:
            result = create_staff_from_recruitment(actor=self.dg, form=self._recruitment_form(access=True), request=request)
        user = result["user"]
        self.assertTrue(user.is_active)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(result["access_delivery"], "activation_email_sent")
        email_body = send_mail.call_args.args[1]
        self.assertIn("/dg/activation/", email_body)
        self.assertNotIn("Mot de passe temporaire", email_body)
        activation_url = next(line.strip() for line in email_body.splitlines() if "/dg/activation/" in line)
        activation_path = urlparse(activation_url).path
        activated = self.client.post(
            activation_path,
            {"new_password1": "StrongPassword!2040", "new_password2": "StrongPassword!2040"},
        )
        self.assertEqual(activated.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.has_usable_password())
        self.assertTrue(SupportAuditLog.objects.filter(target_user=user, action_type=SupportAuditLog.ACTION_ACCOUNT_ACTIVATED).exists())

        inactive = create_staff_from_recruitment(
            actor=self.dg, form=self._recruitment_form(access=False), request=request,
        )["user"]
        self.assertFalse(inactive.is_active)
        self.assertFalse(inactive.has_usable_password())

    def test_staff_reassignment_cannot_leave_the_active_scope(self):
        staff = get_user_model().objects.create_user(username="lot0-staff", password="password")
        profile = staff.profile
        profile.user_type, profile.position, profile.branch, profile.employment_status = "staff", "secretary", self.branch_x, "active"
        profile.save(update_fields=["user_type", "position", "branch", "employment_status", "updated_at"])
        form = DgStaffLifecycleForm(
            {"profile_id": profile.id, "action": "reassign", "branch": self.branch_y.id, "reason": "Besoin opérationnel."}
        )
        self.assertTrue(form.is_valid(), form.errors)
        with self.assertRaises(ValidationError):
            apply_staff_lifecycle_action(actor=self.dg, form=form, allowed_branch_ids=[self.branch_x.id])

    def test_backoffice_list_sections_expose_server_filters_and_bookmarkable_urls(self):
        response = self.client.get(
            reverse("accounts_portal:dg_section", kwargs={"section": "students"}),
            {
                "domain": "etudiants",
                "academic_year_id": self.year_a.id,
                "q": "Camara",
                "filter_branch_id": self.branch_x.id,
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "portal/dg/partials/section_shell.html")
        self.assertContains(response, "Nom ou matricule")
        self.assertContains(response, "Programme")
        self.assertIn("section=students", response["HX-Push-Url"])
        self.assertIn("q=Camara", response["HX-Push-Url"])
        self.assertIn(f"filter_branch_id={self.branch_x.id}", response["HX-Push-Url"])

    def test_backoffice_class_drawer_enforces_branch_scope(self):
        self._set_branch_scope(self.branch_x)
        class_y = AcademicClass.objects.get(name="Classe A-Y")

        in_scope = self.client.get(
            reverse("accounts_portal:dg_drawer"),
            {"kind": "academic_class", "id": self.class_ax.id},
        )
        self.assertEqual(in_scope.status_code, 200)
        self.assertTemplateUsed(in_scope, "portal/dg/drawers/entity_detail.html")
        self.assertContains(in_scope, self.class_ax.display_name)

        out_of_scope = self.client.get(
            reverse("accounts_portal:dg_drawer"),
            {"kind": "academic_class", "id": class_y.id},
        )
        self.assertEqual(out_of_scope.status_code, 403)
