from unittest.mock import patch

from django.template.loader import get_template
from django.test import RequestFactory, SimpleTestCase
from django_components import registry

from ui.components.academic import (
    AcademicAlert,
    AcademicBadge,
    AcademicButton,
    AcademicCalendar,
    AcademicCard,
    AcademicDrawer,
    AcademicEmptyState,
    AcademicFilterBar,
    AcademicModal,
    AcademicPageHeader,
    AcademicPageLayout,
    AcademicProgress,
    AcademicQuickAction,
    AcademicSectionHeader,
    AcademicSidebar,
    AcademicStatCard,
    AcademicStepper,
    AcademicTable,
    AcademicTabs,
    AcademicTimeline,
    AcademicToolbar,
)
from ui.components.calendar import (
    CalendarEntryCard,
    CalendarMiniList,
    CalendarMonthGrid,
    CalendarYearGrid,
)
from ui.components.formation_learning_outcomes.formation_learning_outcomes import (
    FormationLearningOutcomes,
)
from ui.components.ui.button.button import Button
from ui.views import gallery


class ComponentTemplateTests(SimpleTestCase):
    def test_every_registered_component_template_compiles(self):
        failures = []

        for name, component_class in sorted(registry.all().items()):
            try:
                template_name = component_class.template_name
                if template_name:
                    get_template(template_name)
            except Exception as exc:  # pragma: no cover - assertion reports details
                failures.append(f"{name}: {type(exc).__name__}: {exc}")

        self.assertEqual(failures, [], "\n".join(failures))

    def test_gallery_renders(self):
        with (
            patch("core.context_processors.Institution.objects.filter") as institution_filter,
            patch("core.context_processors.SiteConfiguration.objects.first") as site_configuration_first,
        ):
            institution_filter.return_value.first.return_value = None
            site_configuration_first.return_value = None
            response = gallery(RequestFactory().get("/ui/galerie/"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Galerie des composants UI")

    def test_button_defaults_to_a_real_button(self):
        html = Button.render(kwargs={"label": "Enregistrer"})

        self.assertIn("<button", html)
        self.assertNotIn('href="#"', html)

    def test_learning_outcomes_builds_items(self):
        html = FormationLearningOutcomes.render(
            kwargs={"learning_outcomes": "Premier objectif\n\nDeuxième objectif"}
        )

        self.assertIn("Premier objectif", html)
        self.assertIn("Deuxième objectif", html)

    def test_academic_card_renders_title_and_slot(self):
        html = AcademicCard.render(
            kwargs={"title": "Titre", "subtitle": "Sous-titre"},
            slots={"default": "<p>contenu</p>"},
        )

        self.assertIn("Titre", html)
        self.assertIn("Sous-titre", html)
        self.assertIn("contenu", html)

    def test_academic_stat_card_renders(self):
        html = AcademicStatCard.render(
            kwargs={"label": "Inscriptions", "value": "42", "icon": "users"}
        )

        self.assertIn("Inscriptions", html)
        self.assertIn("42", html)

    def test_academic_alert_uses_correct_icon(self):
        html = AcademicAlert.render(
            kwargs={"title": "Alerte", "message": "Message", "tone": "success"}
        )

        self.assertIn("Alerte", html)
        self.assertIn("Message", html)

    def test_academic_empty_state_renders_centered(self):
        html = AcademicEmptyState.render(
            kwargs={"title": "Vide", "message": "Aucune donnée", "icon": "inbox"}
        )

        self.assertIn("Vide", html)
        self.assertIn("Aucune donnée", html)

    def test_academic_section_header_renders_badge(self):
        html = AcademicSectionHeader.render(
            kwargs={"title": "Section", "badge": "Nouveau"}
        )

        self.assertIn("Section", html)
        self.assertIn("Nouveau", html)

    def test_academic_badge_renders_label(self):
        html = AcademicBadge.render(kwargs={"label": "Actif", "tone": "success"})

        self.assertIn("Actif", html)

    def test_academic_progress_computes_percentage(self):
        html = AcademicProgress.render(
            kwargs={"label": "Avancement", "value": 25, "max_value": 100}
        )

        self.assertIn("Avancement", html)
        self.assertIn("25%", html)

    def test_academic_quick_action_renders_button(self):
        html = AcademicQuickAction.render(
            kwargs={"label": "Ajouter", "icon": "plus"}
        )

        self.assertIn("Ajouter", html)
        self.assertIn("<button", html)

    def test_academic_page_header_renders_breadcrumb(self):
        html = AcademicPageHeader.render(
            kwargs={
                "title": "Page",
                "breadcrumb_items": [{"label": "Accueil", "url": "/"}],
            }
        )

        self.assertIn("Page", html)
        self.assertIn("Accueil", html)

    def test_academic_tabs_renders_nav(self):
        html = AcademicTabs.render(
            kwargs={
                "tabs": [
                    {"id": "tab1", "label": "Onglet 1"},
                    {"id": "tab2", "label": "Onglet 2"},
                ],
                "active_tab": "tab1",
            }
        )

        self.assertIn("Onglet 1", html)
        self.assertIn("Onglet 2", html)
        self.assertIn("role=\"tablist\"", html)

    def test_academic_filter_bar_renders_select(self):
        html = AcademicFilterBar.render(
            kwargs={
                "filters": [
                    {
                        "name": "status",
                        "placeholder": "Statut",
                        "options": [
                            {"value": "active", "label": "Actif"},
                        ],
                    }
                ]
            }
        )

        self.assertIn("Statut", html)
        self.assertIn("<select", html)

    def test_academic_toolbar_renders_title(self):
        html = AcademicToolbar.render(
            kwargs={"title": "Liste", "total_count": 3}
        )

        self.assertIn("Liste", html)
        self.assertIn("3 résultats", html)

    def test_academic_modal_renders_dialog(self):
        html = AcademicModal.render(kwargs={"title": "Titre modale"})

        self.assertIn("Titre modale", html)
        self.assertIn("role=\"dialog\"", html)

    def test_academic_drawer_renders_aside(self):
        html = AcademicDrawer.render(kwargs={"title": "Détail"})

        self.assertIn("Détail", html)
        self.assertIn("<aside", html)

    def test_academic_timeline_renders_items(self):
        html = AcademicTimeline.render(
            kwargs={
                "items": [
                    {"title": "Étape 1", "description": "Desc", "tone": "success"}
                ]
            }
        )

        self.assertIn("Étape 1", html)
        self.assertIn("Desc", html)

    def test_academic_stepper_renders_steps(self):
        html = AcademicStepper.render(
            kwargs={
                "steps": [
                    {"title": "Étape 1"},
                    {"title": "Étape 2"},
                ],
                "current_step": 1,
            }
        )

        self.assertIn("Étape 1", html)
        self.assertIn("Étape 2", html)

    def test_academic_table_renders_empty_state(self):
        html = AcademicTable.render(
            kwargs={
                "headers": [{"label": "Nom"}],
                "rows": [],
                "empty_title": "Vide",
            }
        )

        self.assertIn("Vide", html)

    def test_academic_calendar_renders_schedule(self):
        html = AcademicCalendar.render(
            kwargs={"title": "Planning", "week_label": "S1"}
        )

        self.assertIn("Planning", html)
        self.assertIn("S1", html)

    def test_academic_page_layout_renders_header(self):
        html = AcademicPageLayout.render(
            kwargs={"title": "Page", "subtitle": "Sous-titre"},
            slots={"default": "<div>contenu</div>"},
        )

        self.assertIn("Page", html)
        self.assertIn("Sous-titre", html)
        self.assertIn("contenu", html)

    def test_calendar_month_grid_renders_days(self):
        html = CalendarMonthGrid.render(
            kwargs={"year": 2026, "month": 1, "entries": []}
        )

        self.assertIn("Lun", html)
        self.assertIn("Dim", html)

    def test_calendar_year_grid_renders_months(self):
        html = CalendarYearGrid.render(
            kwargs={"year": 2026, "months": [{"name": "Janvier", "event_count": 1, "days": [{"number": 1, "has_events": True}]}]}
        )

        self.assertIn("Janvier", html)

    def test_calendar_entry_card_renders_title(self):
        html = CalendarEntryCard.render(
            kwargs={"entry": {"title": "Examens", "status": "published"}}
        )

        self.assertIn("Examens", html)

    def test_calendar_mini_list_renders_calendars(self):
        html = CalendarMiniList.render(
            kwargs={"calendars": [{"id": 1, "version": 1, "status": "draft"}]}
        )

        self.assertIn("Calendrier v1", html)

    def test_academic_button_renders_variant_and_icon(self):
        html = AcademicButton.render(
            kwargs={"label": "Enregistrer", "icon": "check", "variant": "primary"}
        )

        self.assertIn("Enregistrer", html)
        self.assertIn("data-lucide=\"check\"", html)

    def test_academic_sidebar_renders_menu_items(self):
        html = AcademicSidebar.render(
            kwargs={
                "items": [
                    {"key": "home", "label": "Accueil", "icon": "layout-dashboard"},
                    {"key": "planning", "label": "Planification", "icon": "calendar", "children": [{"key": "calendar", "label": "Calendrier"}]},
                ],
                "active_key": "home",
                "brand_title": "ESFE",
                "user_name": "Directeur",
                "user_initial": "D",
            }
        )

        self.assertIn("Accueil", html)
        self.assertIn("Planification", html)
        self.assertIn("Calendrier", html)
        self.assertIn("ESFE", html)
