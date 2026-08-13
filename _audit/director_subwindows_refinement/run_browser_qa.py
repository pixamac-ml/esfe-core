import json
import os
import subprocess
import sys
import time
import asyncio
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[2]
AUDIT_DIR = Path(__file__).resolve().parent
BASE_URL = "http://127.0.0.1:8001"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test_local")
sys.path.insert(0, str(ROOT))

import django

django.setup()

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.core.management import call_command
from django.utils import timezone
from playwright.sync_api import sync_playwright

from academics.models import (
    AcademicCalendar,
    AcademicCalendarEntry,
    AcademicClass,
    AcademicScheduleEvent,
    AcademicYear,
    EC,
    Semester,
    UE,
)
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme


def aware(year, month, day, hour=8):
    return timezone.make_aware(datetime(year, month, day, hour, 0))


def seed_database():
    database_name = str(settings.DATABASES["default"]["NAME"])
    if not database_name.endswith("test_db.sqlite3"):
        raise RuntimeError(f"Base QA inattendue: {database_name}")
    call_command("flush", interactive=False, verbosity=0)

    branch = Branch.objects.create(
        name="Bamako Moribabougou", code="MORI", slug="bamako-moribabougou"
    )
    cycle = Cycle.objects.create(
        name="Licence professionnelle",
        theme="primary",
        min_duration_years=1,
        max_duration_years=5,
    )
    diploma = Diploma.objects.create(
        name="Licence Agent de Sante Communautaire", level="superieur"
    )
    filiere = Filiere.objects.create(name="Agent de Sante Communautaire")
    programme = Programme.objects.create(
        title="Agent de Sante Communautaire",
        filiere=filiere,
        cycle=cycle,
        diploma_awarded=diploma,
        duration_years=3,
        short_description="Formation sanitaire communautaire",
        description="Programme de sante communautaire.",
    )
    academic_year = AcademicYear.objects.create(
        name="2026-2027",
        start_date=date(2026, 10, 1),
        end_date=date(2027, 7, 31),
        is_active=True,
    )
    academic_class = AcademicClass.objects.create(
        name="L1 Agent de Sante Communautaire",
        programme=programme,
        branch=branch,
        academic_year=academic_year,
        level="L1",
        study_level="LICENCE",
    )
    semester = Semester.objects.create(
        academic_class=academic_class,
        number=1,
        status=Semester.STATUS_FINALIZED,
    )
    ue = UE.objects.create(
        semester=semester,
        code="ASC-UE1",
        title="Fondements de la sante communautaire",
    )
    ec = EC.objects.create(
        ue=ue,
        title="Agent de Sante Communautaire - Concepts de base",
        credit_required="3.00",
        coefficient="2.00",
    )

    user_model = get_user_model()
    director = user_model.objects.create_user(
        username="qa_director_mori",
        email="qa-director-mori@local.test",
        password=None,
        first_name="Moussa",
        last_name="Sylla",
        is_staff=True,
    )
    director.profile.position = "director_of_studies"
    director.profile.role = "executive"
    director.profile.branch = branch
    director.profile.save(
        update_fields=["position", "role", "branch", "updated_at"]
    )
    teacher = user_model.objects.create_user(
        username="qa_enseignant_mori",
        email="qa-enseignant-mori@local.test",
        password=None,
        first_name="Aminata",
        last_name="Traore",
        is_staff=True,
    )
    teacher.profile.position = "teacher"
    teacher.profile.role = "teacher"
    teacher.profile.branch = branch
    teacher.profile.save(
        update_fields=["position", "role", "branch", "updated_at"]
    )

    for index in range(12):
        start = aware(2026, 11, 3 + index, 8)
        AcademicScheduleEvent.objects.create(
            title=f"Evaluation de sante communautaire {index + 1:02d}",
            description="Evaluation rattachee au programme sanitaire actif.",
            event_type=AcademicScheduleEvent.EVENT_TYPE_EXAM,
            academic_class=academic_class,
            ec=ec,
            teacher=teacher,
            branch=branch,
            academic_year=academic_year,
            start_datetime=start,
            end_datetime=start + timedelta(hours=2),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            location="Salle de soins 2",
            created_by=director,
            updated_by=director,
        )

    calendar = AcademicCalendar.objects.create(
        branch=branch,
        academic_year=academic_year,
        version=1,
        status=AcademicCalendar.STATUS_DRAFT,
        created_by=director,
        updated_by=director,
    )
    AcademicCalendarEntry.objects.create(
        calendar=calendar,
        title="Session d'examens du premier semestre",
        description="Periode officielle de la session normale.",
        event_type=AcademicCalendarEntry.EVENT_EXAM_SESSION,
        start_datetime=aware(2026, 12, 7, 0),
        end_datetime=aware(2026, 12, 12, 23),
        all_day=True,
        target_scope=AcademicCalendarEntry.SCOPE_BRANCH,
        is_blocking=True,
        status=AcademicCalendarEntry.STATUS_DRAFT,
        created_by=director,
        updated_by=director,
    )

    session = SessionStore()
    session[SESSION_KEY] = str(director.pk)
    session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    session[HASH_SESSION_KEY] = director.get_session_auth_hash()
    session.save()
    return session.session_key


def wait_for_server(process):
    for _ in range(80):
        if process.poll() is not None:
            raise RuntimeError("Le serveur QA s'est arrete avant le controle navigateur.")
        try:
            with urlopen(f"{BASE_URL}/accounts/login/", timeout=1):
                return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("Le serveur QA n'a pas demarre dans le delai imparti.")


def overflow_state(page):
    return page.evaluate(
        """() => ({
            width: document.documentElement.clientWidth,
            scrollWidth: document.documentElement.scrollWidth,
            overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1
        })"""
    )


def capture(page, filename):
    page.screenshot(path=str(AUDIT_DIR / filename), full_page=True)


def run_browser(session_key):
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    results = {
        "console_errors": [],
        "page_errors": [],
        "overflows": {},
        "htmx_navigation": False,
        "history_restored": False,
        "form_errors_visible": False,
        "form_success_visible": False,
        "pagination_next": False,
        "pagination_previous": False,
        "validation_drawer": False,
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.add_cookies(
            [
                {
                    "name": settings.SESSION_COOKIE_NAME,
                    "value": session_key,
                    "url": BASE_URL,
                    "httpOnly": True,
                    "sameSite": "Lax",
                }
            ]
        )
        page = context.new_page()
        page.on(
            "console",
            lambda message: results["console_errors"].append(message.text)
            if message.type == "error"
            else None,
        )
        page.on("pageerror", lambda error: results["page_errors"].append(str(error)))

        dashboard = f"{BASE_URL}/portal/dashboard/"
        page.goto(
            f"{dashboard}?section=evaluations_calendar&view=overview",
            wait_until="networkidle",
        )
        page.locator("#director-session-subcontent").wait_for()
        capture(page, "01-overview-refined.png")
        results["overflows"]["desktop"] = overflow_state(page)

        navigation_count = page.evaluate(
            "performance.getEntriesByType('navigation').length"
        )
        with page.expect_response(
            lambda response: "/director/exam-sessions/subcontent/" in response.url
        ):
            page.locator('[data-director-subview="create"]').click()
        page.locator('form input[name="title"]').wait_for()
        results["htmx_navigation"] = (
            page.evaluate("performance.getEntriesByType('navigation').length")
            == navigation_count
        )
        capture(page, "02-create-refined.png")

        with page.expect_response(
            lambda response: "/director/evaluations/action/" in response.url
        ):
            page.locator(
                '#director-session-subcontent form button[type="submit"]'
            ).click()
        page.get_by_text("Ce champ est obligatoire.").first.wait_for()
        results["form_errors_visible"] = True
        capture(page, "07-form-errors.png")

        form = page.locator("#director-session-subcontent form")
        form.locator('input[name="title"]').fill(
            "Evaluation des concepts de sante communautaire"
        )
        with page.expect_response(
            lambda response: "/director/evaluations/ec-options/" in response.url
        ):
            form.locator('select[name="class_id"]').select_option(index=1)
        form.locator('select[name="ec"]').select_option(index=1)
        form.locator('select[name="teacher"]').select_option(index=1)
        form.locator('input[name="location"]').fill("Salle de soins 4")
        form.locator('input[name="start_datetime"]').fill("2027-04-06T08:00")
        form.locator('input[name="end_datetime"]').fill("2027-04-06T10:00")
        form.locator('textarea[name="description"]').fill(
            "Evaluation du contenu sanitaire deja rattache a la classe."
        )
        with page.expect_response(
            lambda response: "/director/evaluations/action/" in response.url
        ):
            form.locator('button[type="submit"]').click()
        page.get_by_text("a été planifiée", exact=False).wait_for()
        results["form_success_visible"] = True
        capture(page, "08-form-success.png")
        capture(page, "03-scheduled-refined.png")

        with page.expect_response(
            lambda response: "/director/exam-sessions/subcontent/" in response.url
        ):
            page.locator('select[name="evaluation_status"]').select_option("planned")
        page.get_by_text("Page 1/2", exact=False).wait_for()
        capture(page, "05-pagination-page-1.png")
        results["pagination_next"] = "evaluation_status=planned" in page.url
        with page.expect_response(
            lambda response: "/director/exam-sessions/subcontent/" in response.url
        ):
            page.get_by_role("button", name="Suivant").click()
        page.get_by_text("Page 2/2", exact=False).wait_for()
        capture(page, "06-pagination-page-2.png")
        with page.expect_response(
            lambda response: "/director/exam-sessions/subcontent/" in response.url
        ):
            page.get_by_role("button", name="Précédent").click()
        page.get_by_text("Page 1/2", exact=False).wait_for()
        results["pagination_previous"] = "evaluation_status=planned" in page.url

        page.go_back(wait_until="networkidle")
        page.wait_for_timeout(300)
        results["history_restored"] = page.locator(
            '[data-director-subview="scheduled"]'
        ).get_attribute("aria-current") == "page"

        page.goto(
            f"{dashboard}?section=evaluations&view=validation",
            wait_until="networkidle",
        )
        page.locator("#director-results-validation-list").wait_for()
        card = page.locator("[data-validation-class-card]").first
        if card.count():
            with page.expect_response(
                lambda response: "/portal/director/drawer/" in response.url
            ):
                card.click()
            page.locator("#director-drawer-content").get_by_text(
                "Evaluations & Resultats", exact=True
            ).wait_for()
            results["validation_drawer"] = True
        capture(page, "04-validation-refined.png")

        page.evaluate("window.deCloseDrawer && window.deCloseDrawer()")
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(
            f"{dashboard}?section=evaluations_calendar&view=overview",
            wait_until="networkidle",
        )
        capture(page, "09-mobile.png")
        results["overflows"]["mobile"] = overflow_state(page)

        page.set_viewport_size({"width": 820, "height": 1180})
        page.goto(
            f"{dashboard}?section=evaluations&view=validation",
            wait_until="networkidle",
        )
        capture(page, "10-tablet.png")
        results["overflows"]["tablet"] = overflow_state(page)

        browser.close()
    return results


def main():
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    journal_path = ROOT / "test_db.sqlite3-journal"
    journal_bytes = journal_path.read_bytes() if journal_path.exists() else None
    session_key = seed_database()
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        [
            sys.executable,
            "manage.py",
            "runserver",
            "127.0.0.1:8001",
            "--noreload",
            "--settings=config.settings_test_local",
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )
    try:
        wait_for_server(process)
        results = run_browser(session_key)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        call_command("flush", interactive=False, verbosity=0)
        if journal_bytes is not None:
            journal_path.write_bytes(journal_bytes)
    (AUDIT_DIR / "qa-results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if results["console_errors"] or results["page_errors"]:
        raise SystemExit(1)
    if any(item["overflow"] for item in results["overflows"].values()):
        raise SystemExit(1)
    required = (
        "htmx_navigation",
        "history_restored",
        "form_errors_visible",
        "form_success_visible",
        "pagination_next",
        "pagination_previous",
        "validation_drawer",
    )
    if not all(results[item] for item in required):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
