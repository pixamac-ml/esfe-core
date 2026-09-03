from datetime import date

from django.test import RequestFactory, SimpleTestCase
from django.contrib.humanize.templatetags.humanize import intcomma
from django.core.paginator import Paginator

from accounts.services.manager_dashboard_presentation import (
    MANAGER_SUBVIEW_DEFINITIONS,
    SECTION_PRESENTATION,
    build_manager_dashboard_presentation,
    normalize_manager_subview,
)
from accounts.services.financial_reports import resolve_financial_report_period


class ManagerDashboardPresentationTests(SimpleTestCase):
    def test_every_manager_section_has_a_ui_core_contract(self):
        expected_sections = {
            "overview",
            "candidatures",
            "inscriptions",
            "reenrollment",
            "paiements",
            "salaires",
            "honoraires",
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

    def test_manager_business_domains_expose_real_subviews(self):
        self.assertIn("paiements", MANAGER_SUBVIEW_DEFINITIONS)
        self.assertEqual(
            normalize_manager_subview("paiements", "cash_sessions"),
            "cash_sessions",
        )
        self.assertEqual(
            normalize_manager_subview("paiements", "invented"),
            "overview",
        )

        presentation = build_manager_dashboard_presentation(
            active_section="paiements",
            active_subview="cash_sessions",
            context={"payments": Paginator([], 20).get_page(1)},
            dashboard_url="/portal/manager/",
            workspace_url="/portal/manager/workspace/",
        )

        self.assertEqual(presentation["subview"], "cash_sessions")
        self.assertEqual(
            [item["id"] for item in presentation["subnavigation"]],
            ["overview", "payments", "cash_sessions", "to_validate"],
        )
        self.assertEqual(
            presentation["subnavigation"][0]["hx_target"],
            "#manager-paiements-subcontent",
        )
        self.assertIn(
            "section=paiements&view=overview",
            presentation["subnavigation"][0]["hx_get"],
        )

    def test_daily_work_subviews_keep_only_open_administrative_work(self):
        presentation = build_manager_dashboard_presentation(
            active_section="candidatures",
            active_subview="to_process",
            context={"candidatures": Paginator([], 20).get_page(1)},
            dashboard_url="/portal/manager/",
            workspace_url="/portal/manager/workspace/",
        )
        to_process = next(
            item for item in presentation["subnavigation"] if item["id"] == "to_process"
        )

        self.assertIn("cand_status=open", to_process["hx_get"])

    def test_financial_history_supports_yesterday_without_copying_data(self):
        request = RequestFactory().get("/manager/?report_period=yesterday")

        period = resolve_financial_report_period(request, today=date(2026, 8, 21))

        self.assertEqual(period["start"], date(2026, 8, 20))
        self.assertEqual(period["end"], date(2026, 8, 20))
        self.assertEqual(period["label"], "Hier")
