from django.test import SimpleTestCase
from django.contrib.humanize.templatetags.humanize import intcomma

from accounts.services.manager_dashboard_presentation import (
    SECTION_PRESENTATION,
    build_manager_dashboard_presentation,
)


class ManagerDashboardPresentationTests(SimpleTestCase):
    def test_every_manager_section_has_a_ui_core_contract(self):
        expected_sections = {
            "overview",
            "candidatures",
            "inscriptions",
            "paiements",
            "salaires",
            "depenses",
            "caisse",
            "rapport",
            "cloture",
            "boutique",
            "dons",
            "settings",
        }

        self.assertEqual(set(SECTION_PRESENTATION), expected_sections)
        for section, presentation in SECTION_PRESENTATION.items():
            with self.subTest(section=section):
                self.assertTrue(presentation["title"])
                self.assertTrue(presentation["subtitle"])
                self.assertIn("page_header", presentation["components"])

    def test_overview_values_are_normalized_for_stat_cards(self):
        presentation = build_manager_dashboard_presentation(
            active_section="overview",
            context={
                "total_students": 1250,
                "total_month": 450000,
                "cash_stats": {"available_balance": 325000},
                "manager_intelligence": {"alerts": [{"level": "warning"}]},
            },
        )

        self.assertEqual(presentation["section"], "overview")
        self.assertEqual(len(presentation["stat_cards"]), 4)
        self.assertEqual(presentation["stat_cards"][0]["value"], intcomma(1250))
        self.assertEqual(presentation["stat_cards"][1]["unit"], "FCFA")
        self.assertEqual(presentation["stat_cards"][2]["tone"], "warning")

    def test_unknown_section_falls_back_to_overview(self):
        presentation = build_manager_dashboard_presentation(
            active_section="unknown",
            context={},
        )

        self.assertEqual(presentation["section"], "overview")
