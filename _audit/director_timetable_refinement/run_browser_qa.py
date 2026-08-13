import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import date, time as clock_time, timedelta
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
from playwright.sync_api import sync_playwright

from academics.models import AcademicClass, AcademicYear, EC, Semester, UE, WeeklyScheduleSlot
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme


def seed_database():
    database_name = str(settings.DATABASES["default"]["NAME"])
    if not database_name.endswith("test_db.sqlite3"):
        raise RuntimeError(f"Base QA inattendue: {database_name}")
    call_command("flush", interactive=False, verbosity=0)

    branch = Branch.objects.create(name="Bamako Centre", code="BCT", slug="bamako-centre-edt")
    cycle = Cycle.objects.create(
        name="Licence professionnelle EDT", min_duration_years=1, max_duration_years=5
    )
    diploma = Diploma.objects.create(name="Licence professionnelle EDT", level="superieur")
    filiere = Filiere.objects.create(name="Gestion et administration EDT")
    programme = Programme.objects.create(
        title="Gestion des organisations",
        filiere=filiere,
        cycle=cycle,
        diploma_awarded=diploma,
        duration_years=3,
        short_description="Programme QA emploi du temps",
        description="Programme QA pour la grille hebdomadaire du Directeur des études.",
    )
    academic_year = AcademicYear.objects.create(
        name="2026-2027",
        start_date=date(2026, 10, 1),
        end_date=date(2027, 7, 31),
        is_active=True,
    )
    classes = []
    for index, level in enumerate(("L1", "L2", "L3"), start=1):
        academic_class = AcademicClass.objects.create(
            name=f"{level} Gestion des organisations",
            programme=programme,
            branch=branch,
            academic_year=academic_year,
            level=level,
            study_level="LICENCE",
        )
        semester = Semester.objects.create(academic_class=academic_class, number=1)
        ue = UE.objects.create(
            semester=semester, code=f"GES{index}01", title="Fondamentaux de gestion"
        )
        EC.objects.create(
            ue=ue,
            title="Comptabilité générale" if index == 1 else f"Gestion appliquée {level}",
            credit_required="3.00",
            coefficient="2.00",
        )
        if index == 1:
            EC.objects.create(
                ue=ue,
                title="Droit des affaires",
                credit_required="2.00",
                coefficient="1.00",
            )
        classes.append(academic_class)

    User = get_user_model()
    director = User.objects.create_user(
        username="qa_director_timetable",
        first_name="Moussa",
        last_name="Sylla",
        password=None,
        is_staff=True,
    )
    director.profile.position = "director_of_studies"
    director.profile.role = "executive"
    director.profile.branch = branch
    director.profile.save(update_fields=["position", "role", "branch", "updated_at"])

    teachers = []
    for index, full_name in enumerate(("Aminata Traoré", "Mamadou Coulibaly"), start=1):
        first_name, last_name = full_name.split(" ", 1)
        teacher = User.objects.create_user(
            username=f"qa_teacher_timetable_{index}",
            first_name=first_name,
            last_name=last_name,
            password=None,
        )
        teacher.profile.position = "teacher"
        teacher.profile.role = "teacher"
        teacher.profile.branch = branch
        teacher.profile.save(update_fields=["position", "role", "branch", "updated_at"])
        teachers.append(teacher)

    first_ec = EC.objects.filter(ue__semester__academic_class=classes[0]).order_by("id").first()
    WeeklyScheduleSlot.objects.create(
        academic_class=classes[0],
        ec=first_ec,
        teacher=teachers[0],
        branch=branch,
        academic_year=academic_year,
        weekday=0,
        start_time=clock_time(8, 0),
        end_time=clock_time(10, 0),
        room="Salle A12",
        created_by=director,
    )

    session = SessionStore()
    session[SESSION_KEY] = str(director.pk)
    session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    session[HASH_SESSION_KEY] = director.get_session_auth_hash()
    session.save()
    return session.session_key, classes[0].pk


def wait_for_server(process):
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError("Le serveur QA s'est arrêté.")
        try:
            with urlopen(f"{BASE_URL}/accounts/login/", timeout=1):
                return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("Le serveur QA n'a pas démarré.")


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


def run_browser(session_key, class_id):
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    results = {
        "console_errors": [],
        "page_errors": [],
        "overflows": {},
        "htmx_navigation": False,
        "week_navigation": False,
        "drawer_desktop_width": 0,
        "invalid_form_visible": False,
        "course_created": False,
        "preview_visible": False,
        "print_landscape": False,
        "drawer_mobile_width": 0,
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.add_cookies(
            [{
                "name": settings.SESSION_COOKIE_NAME,
                "value": session_key,
                "url": BASE_URL,
                "httpOnly": True,
                "sameSite": "Lax",
            }]
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

        page.goto(f"{dashboard}?section=planification&view=overview", wait_until="networkidle")
        page.locator("#director-timetable-subcontent").wait_for()
        capture(page, "01-overview-desktop.png")
        results["overflows"]["overview_desktop"] = overflow_state(page)

        navigation_count = page.evaluate("performance.getEntriesByType('navigation').length")
        with page.expect_response(lambda response: "/director/timetable/subcontent/" in response.url):
            page.get_by_text("L1 Gestion des organisations", exact=True).click()
        page.locator("[data-timetable-grid]").wait_for()
        results["htmx_navigation"] = (
            page.evaluate("performance.getEntriesByType('navigation').length") == navigation_count
        )
        capture(page, "02-builder-desktop.png")
        results["overflows"]["builder_desktop"] = overflow_state(page)

        week_navigator = page.locator("[data-timetable-week-start]")
        initial_week = week_navigator.get_attribute("data-timetable-week-start")
        expected_next_week = (
            date.fromisoformat(initial_week) + timedelta(days=7)
        ).isoformat()
        with page.expect_response(lambda response: "/director/timetable/subcontent/" in response.url):
            page.get_by_label("Afficher la semaine suivante").click()
        page.locator(
            f'[data-timetable-week-start="{expected_next_week}"]'
        ).wait_for()
        results["week_navigation"] = (
            f"week_start={expected_next_week}" in page.url
            and page.locator('select[name="class_id"]').input_value() == str(class_id)
        )
        capture(page, "02b-next-week-desktop.png")
        with page.expect_response(lambda response: "/director/timetable/subcontent/" in response.url):
            page.get_by_label("Afficher la semaine précédente").click()
        page.locator(f'[data-timetable-week-start="{initial_week}"]').wait_for()

        add_cell = page.get_by_label("Ajouter un cours le Mardi de 08:00 à 10:00")
        with page.expect_response(lambda response: "/director/timetable/slot/" in response.url):
            add_cell.click()
        drawer = page.locator('[data-ui-core="drawer"] aside')
        drawer.wait_for()
        results["drawer_desktop_width"] = round(drawer.bounding_box()["width"])
        form = page.locator("#director-drawer-content form")
        form.locator('select[name="ec_id"]').select_option(index=1)
        form.locator('select[name="teacher_id"]').select_option(index=1)
        form.locator('input[name="room"]').fill("Salle B04")
        form.locator('input[name="start_time"]').fill("11:00")
        form.locator('input[name="end_time"]').fill("09:00")
        with page.expect_response(lambda response: "/director/timetable/action/" in response.url):
            form.get_by_role("button", name="Ajouter à la grille").click()
        page.get_by_text("L'heure de fin doit être postérieure", exact=False).wait_for()
        results["invalid_form_visible"] = True
        capture(page, "03-slot-errors-desktop.png")

        form = page.locator("#director-drawer-content form")
        form.locator('input[name="start_time"]').fill("08:00")
        form.locator('input[name="end_time"]').fill("10:00")
        with page.expect_response(lambda response: "/director/timetable/action/" in response.url):
            form.get_by_role("button", name="Ajouter à la grille").click()
        page.get_by_text("Le cours a été ajouté à l'emploi du temps.").wait_for()
        page.get_by_text("Salle B04").wait_for()
        results["course_created"] = True
        capture(page, "04-course-created-desktop.png")

        preview_tab = page.get_by_role("tab", name="Aperçu et impression")
        with page.expect_response(lambda response: "/director/timetable/subcontent/" in response.url):
            preview_tab.click()
        page.get_by_text("Aperçu avant impression").wait_for()
        results["preview_visible"] = True
        capture(page, "05-preview-desktop.png")

        with page.expect_popup() as popup_info:
            page.get_by_role("link", name="Ouvrir la version imprimable").click()
        print_page = popup_info.value
        print_page.wait_for_load_state("networkidle")
        print_page.get_by_text("Emploi du temps · L1 Gestion des organisations").wait_for()
        results["print_landscape"] = "A4 landscape" in print_page.locator("style").inner_text()
        capture(print_page, "06-print-a4-landscape.png")
        print_page.close()

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(
            f"{dashboard}?section=planification&view=builder&class_id={class_id}",
            wait_until="networkidle",
        )
        page.locator("[data-timetable-grid]").wait_for()
        results["overflows"]["builder_mobile"] = overflow_state(page)
        capture(page, "07-builder-mobile.png")
        with page.expect_response(lambda response: "/director/timetable/slot/" in response.url):
            page.get_by_role("button", name="Ajouter un cours").first.click()
        drawer.wait_for()
        results["drawer_mobile_width"] = round(drawer.bounding_box()["width"])
        results["overflows"]["drawer_mobile"] = overflow_state(page)
        capture(page, "08-slot-drawer-mobile.png")
        browser.close()
    return results


def main():
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    session_key, class_id = seed_database()
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
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        wait_for_server(process)
        results = run_browser(session_key, class_id)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        call_command("flush", interactive=False, verbosity=0)

    (AUDIT_DIR / "qa-results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    required = (
        "htmx_navigation",
        "week_navigation",
        "invalid_form_visible",
        "course_created",
        "preview_visible",
        "print_landscape",
    )
    if results["console_errors"] or results["page_errors"]:
        raise SystemExit(1)
    if any(item["overflow"] for item in results["overflows"].values()):
        raise SystemExit(1)
    if not all(results[item] for item in required):
        raise SystemExit(1)
    if results["drawer_desktop_width"] < 800 or results["drawer_mobile_width"] > 390:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
