from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from academics.models import AcademicClass, AcademicYear
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme


class DirectorDashboardPhaseTwoTests(TestCase):
    password = "phase2-test-password"

    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(
            name="Annexe Phase 2",
            code="AP2",
            slug="annexe-phase-2",
        )
        cls.other_branch = Branch.objects.create(
            name="Annexe Hors Périmètre",
            code="AHP",
            slug="annexe-hors-perimetre",
        )
        cycle = Cycle.objects.create(
            name="Licence Phase 2",
            theme="primary",
            min_duration_years=1,
            max_duration_years=5,
        )
        diploma = Diploma.objects.create(name="Diplôme Phase 2", level="superieur")
        filiere = Filiere.objects.create(name="Filière Phase 2")
        programme = Programme.objects.create(
            title="Programme Phase 2",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Programme de validation du pilote",
            description="Données de test du dashboard Directeur des Études.",
        )
        academic_year = AcademicYear.objects.create(
            name="2026-2027",
            start_date="2026-10-01",
            end_date="2027-07-31",
            is_active=True,
        )
        cls.own_class = AcademicClass.objects.create(
            name="Classe Annexe Autorisée",
            programme=programme,
            branch=cls.branch,
            academic_year=academic_year,
            level="L1",
            study_level="LICENCE",
        )
        cls.other_class = AcademicClass.objects.create(
            name="Classe Inter Annexe Interdite",
            programme=programme,
            branch=cls.other_branch,
            academic_year=academic_year,
            level="L2",
            study_level="LICENCE",
        )
        cls.director = cls._create_user(
            "phase2_director",
            position="director_of_studies",
            role="executive",
            branch=cls.branch,
        )
        cls.director_with_avatar = cls._create_user(
            "phase2_director_avatar",
            position="director_of_studies",
            role="executive",
            branch=cls.branch,
        )
        cls.director_with_avatar.profile.avatar.save(
            "director-avatar.png",
            SimpleUploadedFile(
                "director-avatar.png",
                b"avatar-bytes",
                content_type="image/png",
            ),
            save=True,
        )

    @classmethod
    def _create_user(cls, username, *, position="", role="", branch=None, superuser=False):
        manager = get_user_model().objects
        if superuser:
            return manager.create_superuser(
                username=username,
                email=f"{username}@example.test",
                password=cls.password,
            )
        user = manager.create_user(
            username=username,
            email=f"{username}@example.test",
            password=cls.password,
            is_staff=True,
        )
        profile = user.profile
        profile.position = position
        profile.role = role
        profile.branch = branch
        profile.save(update_fields=["position", "role", "branch", "updated_at"])
        return user

    def setUp(self):
        self.client.force_login(self.director)

    def test_active_dashboard_uses_one_ui_core_shell(self):
        response = self.client.get(reverse("accounts_portal:portal_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "portal/staff/director_dashboard.html")
        self.assertContains(response, 'data-certified-dashboard-shell="true"')
        self.assertContains(response, 'data-dashboard-role="director_of_studies"')
        self.assertEqual(response.content.count(b'data-ui-core="app-shell"'), 1)
        self.assertEqual(response.content.count(b'data-ui-core="app-sidebar"'), 1)
        self.assertEqual(response.content.count(b'data-ui-core="app-topbar"'), 1)
        self.assertNotContains(response, "academic_sidebar")
        self.assertNotContains(response, "academic_drawer")
        self.assertNotContains(response, "academic_modal")
        self.assertNotContains(response, "Candidater")

    def test_certified_shell_context_is_adapted_to_director_role(self):
        response = self.client.get(reverse("accounts_portal:portal_dashboard"))

        shell = response.context["dashboard_shell"]
        self.assertEqual(shell["certified_template"], "portal/staff/director_dashboard.html")
        self.assertEqual(shell["role"], "director_of_studies")
        self.assertEqual(shell["key"], "director")
        self.assertEqual(shell["workspace_id"], "director-workspace")
        self.assertEqual(shell["active_section"], "home")

    def test_dashboard_uses_ui_core_kpis_panels_table_and_overlays(self):
        response = self.client.get(reverse("accounts_portal:portal_dashboard"))

        self.assertEqual(response.content.count(b'data-ui-core="stat-card"'), 6)
        self.assertContains(response, 'data-ui-core="panel"')
        self.assertContains(response, 'data-ui-core="data-table"')
        self.assertContains(response, 'data-ui-core="drawer"')
        self.assertContains(response, 'data-ui-core="modal"')
        self.assertContains(response, 'data-ui-core="confirm-dialog"')

    def test_dashboard_is_strictly_limited_to_director_branch(self):
        response = self.client.get(reverse("accounts_portal:portal_dashboard"))

        self.assertContains(response, self.own_class.name)
        self.assertNotContains(response, self.other_class.name)

    def test_director_without_branch_is_forbidden(self):
        user = self._create_user(
            "phase2_unscoped",
            position="director_of_studies",
            role="executive",
        )
        self.client.force_login(user)

        dashboard = self.client.get(reverse("accounts_portal:portal_dashboard"))
        workspace = self.client.get(
            reverse("accounts_portal:director_workspace"),
            {"section": "programme"},
        )

        self.assertEqual(dashboard.status_code, 403)
        self.assertEqual(workspace.status_code, 403)

    def test_unauthorized_user_cannot_open_director_fragments(self):
        user = self._create_user(
            "phase2_teacher",
            position="teacher",
            role="teacher",
            branch=self.branch,
        )
        self.client.force_login(user)

        response = self.client.get(
            reverse("accounts_portal:director_workspace"),
            {"section": "programme"},
        )

        self.assertEqual(response.status_code, 403)

    def test_superuser_can_use_explicit_global_director_entry(self):
        superuser = self._create_user("phase2_superuser", superuser=True)
        self.client.force_login(superuser)

        response = self.client.get(reverse("accounts_portal:portal_director"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.own_class.name)
        self.assertContains(response, self.other_class.name)
        self.assertContains(response, "Périmètre global")

    def test_workspace_home_and_business_sections_are_htmx_fragments(self):
        for section in ("home", "programme", "enseignants"):
            with self.subTest(section=section):
                response = self.client.get(
                    reverse("accounts_portal:director_workspace"),
                    {"section": section},
                    HTTP_HX_REQUEST="true",
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f'data-director-section="{section}"')
                self.assertNotContains(response, 'data-ui-core="app-shell"')

    def test_calendar_fragment_serializes_alpine_metadata_as_json(self):
        response = self.client.get(
            reverse("accounts_portal:director_workspace"),
            {"section": "calendrier"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '"needs_class": false')
        self.assertNotContains(response, '"needs_class": False')

    def test_sidebar_navigation_targets_only_workspace_and_pushes_url(self):
        response = self.client.get(reverse("accounts_portal:portal_dashboard"))

        self.assertContains(response, 'hx-target="#director-workspace"')
        self.assertContains(response, 'data-nav-key="programme"')
        self.assertContains(response, "hx-push-url=")
        self.assertContains(response, 'aria-current="page"')

    def test_topbar_uses_internal_profile_and_notifications_fragments(self):
        response = self.client.get(reverse("accounts_portal:portal_dashboard"))

        self.assertContains(response, 'id="director-topbar-fragments"')
        self.assertContains(
            response,
            f'hx-get="{reverse("accounts_portal:director_account_panel")}?view=profile"',
        )
        self.assertContains(
            response,
            f'hx-get="{reverse("accounts_portal:director_notifications_preview")}"',
        )
        self.assertContains(
            response,
            f'hx-get="{reverse("accounts_portal:director_workspace")}?section=messagerie"',
        )
        self.assertNotContains(
            response,
            f'href="{reverse("notification_center:notifications")}"',
        )

    def test_topbar_renders_avatar_when_profile_has_one(self):
        self.client.force_login(self.director_with_avatar)
        response = self.client.get(reverse("accounts_portal:portal_dashboard"))

        self.assertContains(response, "/media/profiles/")
        self.assertContains(response, 'data-ui-core="profile-dropdown"')

    def test_account_and_notifications_fragments_render_without_full_shell(self):
        account = self.client.get(
            reverse("accounts_portal:director_account_panel"),
            {"view": "profile"},
            HTTP_HX_REQUEST="true",
        )
        notifications = self.client.get(
            reverse("accounts_portal:director_workspace"),
            {"section": "notifications"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(account.status_code, 200)
        self.assertContains(account, 'data-ui-core="profile-view"')
        self.assertNotContains(account, 'data-ui-core="app-shell"')

        self.assertEqual(notifications.status_code, 200)
        self.assertContains(notifications, 'data-director-section="messagerie"')
        self.assertContains(notifications, 'id="director-notification-detail"')
        self.assertNotContains(notifications, 'data-ui-core="app-shell"')

    def test_accessibility_structure_and_mobile_shell_classes_are_present(self):
        response = self.client.get(reverse("accounts_portal:portal_dashboard"))

        self.assertContains(response, 'href="#ui-core-main"')
        self.assertContains(response, 'id="ui-core-main"')
        self.assertContains(response, 'aria-live="polite"')
        self.assertContains(response, 'aria-busy="false"')
        self.assertContains(response, "lg:hidden")
        self.assertContains(response, "lg:flex")

    def test_legacy_director_url_keeps_controlled_redirect(self):
        response = self.client.get(reverse("accounts_portal:portal_director"))

        self.assertRedirects(
            response,
            reverse("accounts_portal:portal_dashboard"),
            fetch_redirect_response=False,
        )

    def test_empty_branch_data_renders_explicit_empty_state(self):
        empty_branch = Branch.objects.create(
            name="Annexe Vide",
            code="AVD",
            slug="annexe-vide",
        )
        user = self._create_user(
            "phase2_empty",
            position="director_of_studies",
            role="executive",
            branch=empty_branch,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("accounts_portal:portal_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aucune classe active")

    def test_dashboard_script_is_external_and_ui_core_driven(self):
        response = self.client.get(reverse("accounts_portal:portal_dashboard"))

        self.assertContains(response, "src/js/portal/certified_dashboard_shell.js")
        self.assertContains(response, "src/js/portal/director_dashboard.js")
        self.assertContains(response, "src/js/ui_core/index.js")
        self.assertNotContains(response, "function deDashboard()")


class DirectorEvaluationsSubwindowsTests(TestCase):
    password = "eval-sub-test-password"

    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(
            name="Annexe Eval Sub", code="AES", slug="annexe-eval-sub",
        )
        cycle = Cycle.objects.create(
            name="Licence Eval", theme="primary",
            min_duration_years=1, max_duration_years=5,
        )
        diploma = Diploma.objects.create(name="Diplome Eval", level="superieur")
        filiere = Filiere.objects.create(name="Filiere Eval")
        programme = Programme.objects.create(
            title="Programme Eval", filiere=filiere, cycle=cycle,
            diploma_awarded=diploma, duration_years=3,
            short_description="Test eval subwindows",
            description="Donnees de test.",
        )
        academic_year = AcademicYear.objects.create(
            name="2026-2027", start_date="2026-10-01",
            end_date="2027-07-31", is_active=True,
        )
        cls.academic_class = AcademicClass.objects.create(
            name="Classe Eval", programme=programme, branch=cls.branch,
            academic_year=academic_year, level="L1", study_level="LICENCE",
        )
        cls.director = get_user_model().objects.create_user(
            username="eval_director", email="eval_director@test.test",
            password=cls.password, is_staff=True,
        )
        profile = cls.director.profile
        profile.position = "director_of_studies"
        profile.role = "executive"
        profile.branch = cls.branch
        profile.save(update_fields=["position", "role", "branch", "updated_at"])

    def setUp(self):
        self.client.force_login(self.director)

    def test_evaluations_section_shows_subnavigation(self):
        response = self.client.get(
            reverse("accounts_portal:director_workspace"),
            {"section": "evaluations"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="director-result-tabs-overview-tab"')
        self.assertContains(response, "Vue d&#x27;ensemble")
        self.assertContains(response, "Validation et publication")
        self.assertNotContains(response, "Planifier")
        self.assertNotContains(response, "Programmées")
        self.assertContains(response, "director-results-subcontent")
        self.assertContains(response, "director-results-loading")
        self.assertContains(response, "Résultats et notes")

    def test_sessions_section_owns_planning_subnavigation(self):
        response = self.client.get(
            reverse("accounts_portal:director_workspace"),
            {"section": "evaluations_calendar"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="director-session-tabs-overview-tab"')
        self.assertContains(response, "Sessions")
        self.assertContains(response, "Planifier")
        self.assertContains(response, "Programmées")
        self.assertContains(response, "director-session-subcontent")

    def test_evaluations_subcontent_default_is_overview(self):
        response = self.client.get(
            reverse("accounts_portal:director_evaluations_subcontent"),
            {"view": "overview"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Traitement des résultats")
        self.assertContains(response, "Bulletins")

    def test_evaluations_subcontent_create(self):
        response = self.client.get(
            reverse("accounts_portal:director_exam_sessions_subcontent"),
            {"view": "create"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Planifier une évaluation")
        self.assertContains(response, "hx-post")
        self.assertContains(response, "director-evaluation-ec-field")
        self.assertContains(response, "director-evaluation-form-loading")

    def test_evaluations_subcontent_scheduled(self):
        response = self.client.get(
            reverse("accounts_portal:director_exam_sessions_subcontent"),
            {"view": "scheduled"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aucune évaluation programmée")

    def test_evaluations_subcontent_validation(self):
        response = self.client.get(
            reverse("accounts_portal:director_evaluations_subcontent"),
            {"view": "validation"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Classes et semestres")

    def test_evaluations_subcontent_unknown_view_defaults_to_overview(self):
        response = self.client.get(
            reverse("accounts_portal:director_evaluations_subcontent"),
            {"view": "nonexistent"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Traitement des résultats")

    def test_evaluations_subcontent_requires_authentication(self):
        self.client.logout()
        response = self.client.get(
            reverse("accounts_portal:director_evaluations_subcontent"),
            {"view": "overview"},
        )
        self.assertEqual(response.status_code, 302)

    def test_evaluations_subcontent_requires_director_position(self):
        regular = get_user_model().objects.create_user(
            username="eval_regular", email="eval_regular@test.test",
            password=self.password, is_staff=True,
        )
        profile = regular.profile
        profile.position = "teacher"
        profile.role = "teacher"
        profile.branch = self.branch
        profile.save(update_fields=["position", "role", "branch", "updated_at"])
        self.client.force_login(regular)
        response = self.client.get(
            reverse("accounts_portal:director_evaluations_subcontent"),
            {"view": "overview"},
        )
        self.assertEqual(response.status_code, 403)

    def test_each_subcontent_returns_unique_fragment(self):
        result_fragments = {}
        for view in ("overview", "validation"):
            response = self.client.get(
                reverse("accounts_portal:director_evaluations_subcontent"),
                {"view": view},
            )
            self.assertEqual(response.status_code, 200)
            result_fragments[view] = response.content.decode()
        self.assertNotEqual(result_fragments["overview"], result_fragments["validation"])

        session_fragments = {}
        for view in ("overview", "sessions", "create", "scheduled"):
            response = self.client.get(
                reverse("accounts_portal:director_exam_sessions_subcontent"),
                {"view": view},
            )
            self.assertEqual(response.status_code, 200)
            session_fragments[view] = response.content.decode()
        self.assertEqual(len(set(session_fragments.values())), 4)

    def test_workspace_evaluations_has_htmx_indicator(self):
        response = self.client.get(
            reverse("accounts_portal:director_workspace"),
            {"section": "evaluations"},
        )
        self.assertContains(response, "hx-indicator")
        self.assertContains(response, "director-results-loading")
        self.assertContains(response, "htmx-indicator")

    def test_workspace_evaluations_tabs_use_correct_target(self):
        response = self.client.get(
            reverse("accounts_portal:director_workspace"),
            {"section": "evaluations"},
        )
        content = response.content.decode()
        self.assertIn('hx-target="#director-results-subcontent"', content)
        self.assertIn('hx-swap="innerHTML"', content)
        self.assertIn("hx-push-url", content)

    def test_subcontent_pushes_full_dashboard_url(self):
        response = self.client.get(
            reverse("accounts_portal:director_exam_sessions_subcontent"),
            {"view": "scheduled", "evaluation_status": "planned"},
        )
        self.assertEqual(
            response.headers["HX-Push-Url"],
            reverse("accounts_portal:portal_dashboard")
            + "?view=scheduled&evaluation_status=planned&section=evaluations_calendar",
        )

    def test_initial_validation_has_no_unprocessed_oob_counters(self):
        response = self.client.get(
            reverse("accounts_portal:director_workspace"),
            {"section": "evaluations", "view": "validation"},
        )
        content = response.content.decode()
        self.assertEqual(content.count('id="director-validation-count"'), 1)
        self.assertEqual(content.count('id="director-publication-count"'), 1)
        self.assertNotIn('hx-swap-oob="innerHTML"', content)

    def test_workspace_evaluations_has_no_global_overflow(self):
        response = self.client.get(
            reverse("accounts_portal:director_workspace"),
            {"section": "evaluations"},
        )
        self.assertContains(response, "overflow-x-auto")
