import ast
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django_components import registry

from ui.components.ui_core.data_display import (
    ChartPanel,
    DataTable,
    ProgressBar,
    StatCard,
    StatusBadge,
)
from ui.components.ui_core.feedback import Alert, Toast
from ui.components.ui_core.layout import Panel
from ui.components.ui_core.navigation import AppSidebar
from ui.services.navigation import build_navigation


class UiCoreComponentTests(SimpleTestCase):
    public_names = {
        "ui_core.alert",
        "ui_core.app_shell",
        "ui_core.app_sidebar",
        "ui_core.app_topbar",
        "ui_core.breadcrumb",
        "ui_core.chart_panel",
        "ui_core.confirm_dialog",
        "ui_core.content_grid",
        "ui_core.data_table",
        "ui_core.drawer",
        "ui_core.dropdown_menu",
        "ui_core.empty_state",
        "ui_core.filter_bar",
        "ui_core.form_field",
        "ui_core.loading_overlay",
        "ui_core.modal",
        "ui_core.nav_group",
        "ui_core.nav_item",
        "ui_core.page_header",
        "ui_core.page_section",
        "ui_core.panel",
        "ui_core.progress_bar",
        "ui_core.stat_card",
        "ui_core.status_badge",
        "ui_core.tabs",
        "ui_core.timeline",
        "ui_core.toast",
    }

    def test_public_names_are_registered_without_legacy_collisions(self):
        registered = registry.all()

        for name in self.public_names:
            self.assertIn(name, registered)

        self.assertIn("stat_card", registered)
        self.assertIsNot(registered["stat_card"], registered["ui_core.stat_card"])

    def test_every_ui_core_template_exists_after_reorganization(self):
        registered = registry.all()

        for name in self.public_names:
            template_name = registered[name].template_name
            self.assertTrue(template_name)
            self.assertTrue(template_name.startswith("ui_core/"))
            template_path = Path(settings.BASE_DIR, "ui", "templates", template_name)
            self.assertTrue(template_path.is_file(), f"{name}: {template_path}")

    def test_optional_values_and_long_content_render(self):
        long_label = "Indicateur institutionnel " * 12
        html = StatCard.render(kwargs={"label": long_label})

        self.assertIn("Indicateur institutionnel", html)
        self.assertIn("—", html)
        self.assertIn('data-ui-core="stat-card"', html)

    def test_stat_card_preserves_zero_value(self):
        html = StatCard.render(kwargs={"label": "Aucune anomalie", "value": 0})

        self.assertIn(">0<", html)

    def test_unknown_badge_tone_falls_back_to_neutral(self):
        html = StatusBadge.render(
            kwargs={"label": "État non référencé", "tone": "purple-magic"}
        )

        self.assertIn("État non référencé", html)
        self.assertIn("bg-ui-surface-muted", html)

    def test_status_badge_preserves_zero_value(self):
        html = StatusBadge.render(kwargs={"label": 0, "tone": "warning"})

        self.assertIn(">0<", html)
        self.assertNotIn("Inconnu", html)

    def test_unknown_tones_have_safe_fallbacks(self):
        alert_html = Alert.render(
            kwargs={"message": "Alerte", "tone": "unsupported"}
        )
        toast_html = Toast.render(
            kwargs={"message": "Toast", "tone": "unsupported"}
        )
        stat_html = StatCard.render(
            kwargs={"label": "Stat", "tone": "unsupported"}
        )

        self.assertIn("bg-ui-surface-muted", alert_html)
        self.assertIn("bg-ui-info", toast_html)
        self.assertIn("bg-ui-surface-muted", stat_html)

    def test_empty_table_uses_official_empty_state(self):
        html = DataTable.render(
            kwargs={
                "headers": [{"label": "Nom"}],
                "rows": [],
                "empty_title": "Rien à afficher",
            }
        )

        self.assertIn("Rien à afficher", html)
        self.assertIn('data-ui-core="empty-state"', html)

    def test_panel_accepts_missing_optional_parameters(self):
        html = Panel.render(slots={"default": "<p>Contenu</p>"})

        self.assertIn("Contenu", html)
        self.assertIn('data-ui-core="panel"', html)

    def test_empty_navigation_renders_without_error(self):
        html = AppSidebar.render(kwargs={"groups": []})

        self.assertIn("Aucune navigation disponible", html)
        self.assertIn('data-ui-core="app-sidebar"', html)

    def test_dashboard_shell_keeps_one_vertical_scroll_owner(self):
        shell = Path(
            settings.BASE_DIR, "ui", "templates", "ui_core", "layout", "app_shell.html"
        ).read_text(encoding="utf-8")
        sidebar = Path(
            settings.BASE_DIR, "ui", "templates", "ui_core", "navigation", "app_sidebar.html"
        ).read_text(encoding="utf-8")

        self.assertIn("min-h-screen", shell)
        self.assertIn("items-stretch", shell)
        self.assertNotIn("overflow-x-hidden", shell)
        self.assertIn("h-screen", sidebar)
        self.assertIn("lg:sticky", sidebar)
        self.assertIn("min-h-0", sidebar)
        self.assertIn("overflow-y-auto", sidebar)

    def test_overlay_templates_keep_keyboard_focus_contract(self):
        registered = registry.all()

        for name in (
            "ui_core.modal",
            "ui_core.drawer",
            "ui_core.confirm_dialog",
        ):
            html = registered[name].render(kwargs={"trigger_label": "Ouvrir"})
            self.assertIn("@keydown.escape.window", html)
            self.assertIn("@keydown.tab", html)
            self.assertIn("uiOverlay(", html)

        script = Path(
            settings.BASE_DIR, "static", "src", "js", "ui_core", "index.js"
        ).read_text(encoding="utf-8")
        self.assertIn("this.opener.focus()", script)
        self.assertIn("document.documentElement.classList.add", script)

    def test_drawer_supports_compact_and_wide_sizes(self):
        drawer = registry.all()["ui_core.drawer"]

        compact_html = drawer.render(kwargs={"size": "compact"})
        wide_html = drawer.render(kwargs={"size": "wide"})

        self.assertIn("max-w-sm", compact_html)
        self.assertIn("max-w-4xl", wide_html)

    def test_modal_supports_compact_and_wide_sizes(self):
        modal = registry.all()["ui_core.modal"]

        compact_html = modal.render(kwargs={"size": "compact"})
        wide_html = modal.render(kwargs={"size": "wide"})

        self.assertIn("max-w-lg", compact_html)
        self.assertIn("max-w-4xl", wide_html)

    def test_tabs_support_htmx_links_without_breaking_button_items(self):
        tabs = registry.all()["ui_core.tabs"]
        html = tabs.render(
            kwargs={
                "id": "academic-tabs",
                "active": "sessions",
                "items": [
                    {
                        "id": "sessions",
                        "label": "Sessions",
                        "href": "/dashboard/?section=sessions",
                        "hx_get": "/director/sessions/?view=sessions",
                        "hx_target": "#session-content",
                        "hx_push_url": "/dashboard/?section=sessions&view=sessions",
                        "hx_indicator": "#session-loading",
                    },
                    {"id": "archive", "label": "Archive"},
                ],
            }
        )

        self.assertIn('href="/dashboard/?section=sessions"', html)
        self.assertIn('hx-target="#session-content"', html)
        self.assertIn('hx-indicator="#session-loading"', html)
        self.assertIn('data-director-subview="sessions"', html)
        self.assertIn('<button', html)
        self.assertIn("Archive", html)

    def test_density_and_tone_fallbacks_are_safe(self):
        table = DataTable.render(kwargs={"density": "microscopic", "rows": []})
        progress = ProgressBar.render(kwargs={"tone": "purple", "value": 140})

        self.assertIn('data-density="comfortable"', table)
        self.assertIn('aria-valuenow="100"', progress)
        self.assertIn("bg-ui-text-muted", progress)

    def test_chart_states_render_without_model_access(self):
        chart = ChartPanel.render(
            kwargs={
                "title": "Courbe",
                "labels": ["A", "B"],
                "datasets": [{"label": "Valeur", "data": [1, 2]}],
            }
        )
        empty = ChartPanel.render(kwargs={"title": "Vide"})

        self.assertIn('data-ui-chart="', chart)
        self.assertIn("Aucune donnée à visualiser", empty)


class UiCoreArchitectureTests(SimpleTestCase):
    def test_base_uses_one_ui_core_feedback_pipeline(self):
        base = Path(settings.BASE_DIR, "templates", "base.html").read_text(encoding="utf-8")
        toast_host = Path(settings.BASE_DIR, "templates", "toast.html").read_text(encoding="utf-8")
        legacy_toast = Path(
            settings.BASE_DIR, "ui", "templates", "dashboard", "toast.html"
        ).read_text(encoding="utf-8")

        self.assertIn("src/js/ui_core/index.js", base)
        self.assertNotIn("ESFE OPTIMISTIC ENGINE", base)
        self.assertNotIn("esfe-spinner", base)
        self.assertIn('id="ui-toast-region"', toast_host)
        self.assertNotIn("esfeToastCenter", legacy_toast)

    def test_components_do_not_import_business_apps_or_models(self):
        root = Path(settings.BASE_DIR, "ui", "components", "ui_core")
        forbidden_roots = {
            "academic_cycle",
            "academics",
            "accounts",
            "admissions",
            "branches",
            "inscriptions",
            "payments",
            "portal",
            "secretary",
            "students",
            "superadmin",
        }

        failures = []
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module]
                for module in modules:
                    if module.split(".", 1)[0] in forbidden_roots:
                        failures.append(f"{path.relative_to(root)} -> {module}")
                    if module == "django.db" or module.startswith("django.db."):
                        failures.append(f"{path.relative_to(root)} -> {module}")
                if isinstance(node, ast.Attribute) and node.attr == "objects":
                    failures.append(f"{path.relative_to(root)} -> ORM .objects")
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in {"can_access", "get_user_scope"}
                ):
                    failures.append(
                        f"{path.relative_to(root)} -> {node.func.id}()"
                    )

        self.assertEqual(failures, [])

    def test_ui_core_templates_do_not_include_business_templates(self):
        root = Path(settings.BASE_DIR, "ui", "templates", "ui_core")
        forbidden_fragments = (
            '"accounts/',
            '"academics/',
            '"admissions/',
            '"portal/',
            '"secretary/',
            '"students/',
        )
        failures = []

        for path in root.rglob("*.html"):
            content = path.read_text(encoding="utf-8")
            for fragment in forbidden_fragments:
                if fragment in content:
                    failures.append(f"{path.relative_to(root)} -> {fragment}")

        self.assertEqual(failures, [])

    def test_tailwind_scans_nested_ui_core_templates(self):
        config = Path(settings.BASE_DIR, "tailwind.config.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("./**/templates/**/*.html", config)
        self.assertTrue(
            Path(
                settings.BASE_DIR,
                "ui",
                "templates",
                "ui_core",
                "layout",
                "app_shell.html",
            ).is_file()
        )


class NavigationServiceTests(SimpleTestCase):
    def setUp(self):
        self.user = get_user_model()(username="navigation-user")
        self.user._state.adding = False
        self.user.pk = 42

    @patch("ui.services.navigation.can_access", return_value=False)
    @patch("ui.services.navigation.get_user_scope")
    def test_user_without_role_or_branch_gets_personal_navigation_only(
        self, get_scope, can_access
    ):
        get_scope.return_value = {
            "is_global": False,
            "branch": None,
            "role": None,
            "position": None,
        }

        groups = build_navigation(self.user, current_path="/portal/")

        self.assertEqual([group["label"] for group in groups], ["Espace personnel"])
        can_access.assert_not_called()

    @patch("ui.services.navigation.can_access")
    @patch("ui.services.navigation.get_user_scope")
    def test_scoped_user_only_receives_policy_authorized_workspace(
        self, get_scope, can_access
    ):
        get_scope.return_value = {
            "is_global": False,
            "branch": object(),
            "role": "student",
            "position": "student",
        }
        can_access.side_effect = (
            lambda user, action, resource=None: action == "view_portal"
            and resource == "student"
        )

        groups = build_navigation(
            self.user, current_path=reverse("accounts_portal:portal_student")
        )
        workspace = groups[1]["items"]

        self.assertEqual([item["label"] for item in workspace], ["Études"])
        self.assertTrue(workspace[0]["active"])


class UiSystemAccessTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.url = reverse("ui:system")

    @override_settings(DEBUG=False)
    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    @override_settings(DEBUG=False)
    def test_regular_user_is_denied_outside_development(self):
        user = self.user_model.objects.create_user(
            username="ui-regular", password="test-password"
        )
        self.client.force_login(user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 403)

    @override_settings(DEBUG=False)
    def test_superuser_can_render_reference_page(self):
        user = self.user_model.objects.create_superuser(
            username="ui-admin",
            email="ui-admin@example.test",
            password="test-password",
        )
        self.client.force_login(user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "UI Core")
        self.assertContains(response, "Phase 1.75")
        self.assertContains(response, 'data-ui-core="app-shell"')
        self.assertNotContains(response, "Candidater")
        self.assertNotContains(response, "L’École")
        self.assertNotContains(response, 'data-ui-core="public-shell"')

    @override_settings(DEBUG=True)
    def test_authenticated_user_can_render_in_development(self):
        user = self.user_model.objects.create_user(
            username="ui-developer", password="test-password"
        )
        self.client.force_login(user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)


@override_settings(DEBUG=True)
class UiSystemInteractionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="ui-demo-user", password="test-password"
        )
        self.client.force_login(self.user)

    def test_catalogue_uses_internal_base_and_exposes_all_families(self):
        response = self.client.get(reverse("ui:system"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "ui/system_base.html")
        for anchor in (
            "foundations",
            "navigation",
            "layout",
            "data",
            "tables",
            "filters",
            "forms",
            "feedback",
            "overlays",
            "productivity",
            "visualization",
            "planning",
            "responsive",
            "accessibility",
            "dashboard-example",
        ):
            self.assertContains(response, f'id="{anchor}"')
        self.assertNotContains(response, "Accueil</a>")
        self.assertNotContains(response, "Formations")
        self.assertNotContains(response, "Communauté")

    def test_demo_endpoints_are_protected(self):
        self.client.logout()

        for name in (
            "system_demo_table",
            "system_demo_modal",
            "system_demo_drawer",
            "system_demo_form",
            "system_demo_refresh",
            "system_demo_error",
        ):
            response = self.client.get(reverse(f"ui:{name}"))
            self.assertEqual(response.status_code, 302, name)

    def test_table_search_pagination_density_and_states_render_partials(self):
        url = reverse("ui:system_demo_table")
        response = self.client.get(url, {"q": "Aminata", "density": "compact"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aminata Traoré")
        self.assertContains(response, 'data-density="compact"')
        self.assertNotContains(response, "Moussa Diarra")
        self.assertContains(self.client.get(url, {"page": 2}), "Page 2")
        self.assertContains(self.client.get(url, {"state": "empty"}), "Aucun résultat")
        self.assertContains(
            self.client.get(url, {"state": "error"}),
            "Erreur de démonstration contrôlée",
        )
        self.assertContains(
            self.client.get(url, {"state": "permission"}), "Accès non autorisé"
        )

    def test_modal_drawer_and_refresh_fragments_render(self):
        modal = self.client.get(reverse("ui:system_demo_modal"))
        drawer = self.client.get(reverse("ui:system_demo_drawer"))
        refresh = self.client.get(reverse("ui:system_demo_refresh"))

        self.assertContains(modal, 'data-ui-demo-fragment="modal"')
        self.assertContains(drawer, 'data-ui-demo-fragment="drawer"')
        self.assertContains(refresh, 'data-ui-demo="refresh"')
        self.assertIn("ui:toast", refresh.headers["HX-Trigger"])

    def test_form_validates_server_side_and_emits_toast(self):
        url = reverse("ui:system_demo_form")
        invalid = self.client.post(url, {"name": "A", "email": "invalide"})
        valid = self.client.post(
            url,
            {"name": "Awa", "email": "awa@example.test", "context": "compact"},
        )

        self.assertContains(invalid, "Saisissez au moins deux caractères")
        self.assertContains(invalid, "adresse email valide")
        self.assertContains(valid, "Validation réussie")
        self.assertIn("ui:toast", valid.headers["HX-Trigger"])

    def test_confirmation_is_post_only_and_emits_toast(self):
        url = reverse("ui:system_demo_confirm")

        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url)
        self.assertContains(response, "action fictive")
        self.assertIn("ui:toast", response.headers["HX-Trigger"])

    def test_demo_buttons_declare_their_type(self):
        roots = [
            Path(settings.BASE_DIR, "ui", "templates", "ui", "system.html"),
            *Path(settings.BASE_DIR, "ui", "templates", "ui", "partials").glob("*.html"),
            *Path(settings.BASE_DIR, "ui", "templates", "ui_core").rglob("*.html"),
        ]
        failures = []
        import re

        for path in roots:
            content = path.read_text(encoding="utf-8")
            for button in re.findall(r"<button\b[^>]*>", content, re.IGNORECASE):
                if "type=" not in button:
                    failures.append(f"{path.name}: {button[:80]}")
        self.assertEqual(failures, [])

    def test_ui_core_script_has_idempotent_htmx_hooks(self):
        script = Path(
            settings.BASE_DIR, "static", "src", "js", "ui_core", "index.js"
        ).read_text(encoding="utf-8")

        self.assertIn("htmx:afterSwap", script)
        self.assertIn("data-ui-bound", script)
        self.assertIn("UI.instances.charts", script)
        self.assertIn("ui:toast", script)
