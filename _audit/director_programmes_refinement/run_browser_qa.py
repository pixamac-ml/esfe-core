import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import date
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

from academics.models import AcademicClass, AcademicYear, EC, Semester, UE
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme


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
    diploma = Diploma.objects.create(name="Licence professionnelle", level="superieur")
    filiere = Filiere.objects.create(name="Gestion et sante")
    programme = Programme.objects.create(
        title="Gestion des organisations",
        filiere=filiere,
        cycle=cycle,
        diploma_awarded=diploma,
        duration_years=3,
        short_description="Formation en gestion",
        description="Programme de gestion des organisations.",
    )
    programme_two = Programme.objects.create(
        title="Sante communautaire",
        filiere=filiere,
        cycle=cycle,
        diploma_awarded=diploma,
        duration_years=3,
        short_description="Formation sanitaire",
        description="Programme de sante communautaire.",
    )
    academic_year = AcademicYear.objects.create(
        name="2026-2027",
        start_date=date(2026, 10, 1),
        end_date=date(2027, 7, 31),
        is_active=True,
    )
    main_class = AcademicClass.objects.create(
        name="L1 Gestion des organisations",
        programme=programme,
        branch=branch,
        academic_year=academic_year,
        level="L1",
        study_level="LICENCE",
    )
    semester_one = Semester.objects.create(academic_class=main_class, number=1)
    semester_two = Semester.objects.create(academic_class=main_class, number=2)
    ue_one = UE.objects.create(
        semester=semester_one, code="GES101", title="Fondamentaux de gestion"
    )
    UE.objects.create(
        semester=semester_two, code="GES201", title="Pilotage des organisations"
    )
    EC.objects.create(
        ue=ue_one,
        title="Comptabilite generale",
        credit_required="3.00",
        coefficient="2.00",
    )

    for index in range(13):
        academic_class = AcademicClass.objects.create(
            name=f"Classe pedagogique {index + 1:02d}",
            programme=programme_two if index % 2 else programme,
            branch=branch,
            academic_year=academic_year,
            level=f"N{index + 1:02d}",
            study_level="LICENCE",
        )
        Semester.objects.create(academic_class=academic_class, number=1)

    director = get_user_model().objects.create_user(
        username="qa_director_programmes",
        email="qa-director-programmes@local.test",
        password=None,
        first_name="Moussa",
        last_name="Sylla",
        is_staff=True,
    )
    director.profile.position = "director_of_studies"
    director.profile.role = "executive"
    director.profile.branch = branch
    director.profile.save(update_fields=["position", "role", "branch", "updated_at"])

    session = SessionStore()
    session[SESSION_KEY] = str(director.pk)
    session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    session[HASH_SESSION_KEY] = director.get_session_auth_hash()
    session.save()
    return session.session_key


def wait_for_server(process):
    for _ in range(100):
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
        "class_form_errors": False,
        "class_created": False,
        "drawer_opened": False,
        "drawer_desktop_width": 0,
        "ec_created": False,
        "maquette_navigation": False,
        "drawer_mobile_width": 0,
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
        page.goto(f"{dashboard}?section=programme&view=overview", wait_until="networkidle")
        page.locator("#director-programme-subcontent").wait_for()
        capture(page, "01-overview-desktop.png")
        results["overflows"]["desktop_overview"] = overflow_state(page)

        navigation_count = page.evaluate("performance.getEntriesByType('navigation').length")
        with page.expect_response(lambda response: "/director/programme/subcontent/" in response.url):
            page.locator('[data-director-subview="classes"]').click()
        page.locator("#director-programme-class-list-region").wait_for()
        results["htmx_navigation"] = (
            page.evaluate("performance.getEntriesByType('navigation').length") == navigation_count
        )
        capture(page, "02-classes-desktop.png")
        results["overflows"]["desktop_classes"] = overflow_state(page)

        with page.expect_response(lambda response: "/director/programme/class/modal/" in response.url):
            page.get_by_role("button", name="Nouvelle classe").click()
        modal_form = page.locator('#director-modal-content form')
        modal_form.wait_for()
        with page.expect_response(lambda response: "/director/programme/action/" in response.url):
            modal_form.get_by_role("button", name="Enregistrer").click()
        page.get_by_text("Ce champ est obligatoire.").first.wait_for()
        results["class_form_errors"] = True
        capture(page, "03-class-form-errors.png")

        modal_form = page.locator('#director-modal-content form')
        modal_form.locator('select[name="programme"]').select_option(index=1)
        modal_form.locator('select[name="academic_year"]').select_option(index=1)
        modal_form.locator('input[name="level"]').fill("M2")
        modal_form.locator('input[name="validation_threshold"]').fill("12")
        with page.expect_response(lambda response: "/director/programme/action/" in response.url):
            modal_form.get_by_role("button", name="Enregistrer").click()
        page.get_by_text("Classe enregistrée avec succès.").wait_for()
        page.locator("#director-programme-class-list-region article h3", has_text="M2").wait_for()
        results["class_created"] = True
        capture(page, "04-class-created.png")

        with page.expect_response(lambda response: "/portal/director/drawer/" in response.url):
            page.get_by_role("button", name="Maquette").first.click()
        page.locator("#director-drawer-content").get_by_text("Maquette pédagogique", exact=True).wait_for()
        drawer = page.locator('[data-ui-core="drawer"] aside')
        results["drawer_desktop_width"] = round(drawer.bounding_box()["width"])
        results["drawer_opened"] = results["drawer_desktop_width"] >= 800
        capture(page, "05-drawer-wide-desktop.png")

        page.get_by_role("button", name="Ajouter une matière").click()
        ec_form = page.locator('#director-drawer-content form:has(input[name="action"][value="save_ec"])')
        ec_form.locator('select[name="ue"]').select_option(index=1)
        ec_form.locator('input[name="title"]').fill("Analyse financiere")
        ec_form.locator('input[name="coefficient"]').fill("1")
        ec_form.locator('input[name="credit_required"]').fill("2")
        with page.expect_response(lambda response: "/director/programme/action/" in response.url):
            ec_form.get_by_role("button", name="Enregistrer la matière").click()
        page.get_by_text("Élément constitutif enregistré.").wait_for()
        page.get_by_text("Analyse financiere").wait_for()
        results["ec_created"] = True
        capture(page, "06-drawer-ec-created.png")

        page.evaluate("window.deCloseDrawer && window.deCloseDrawer()")
        with page.expect_response(lambda response: "/director/programme/subcontent/" in response.url):
            page.locator('[data-director-subview="maquettes"]').click()
        page.get_by_text("Lecture de la maquette active", exact=False).wait_for()
        results["maquette_navigation"] = True
        capture(page, "07-maquettes-desktop.png")

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{dashboard}?section=programme&view=classes", wait_until="networkidle")
        capture(page, "08-classes-mobile.png")
        results["overflows"]["mobile_classes"] = overflow_state(page)
        with page.expect_response(lambda response: "/portal/director/drawer/" in response.url):
            page.get_by_role("button", name="Maquette").first.click()
        page.locator("#director-drawer-content").get_by_text("Maquette pédagogique", exact=True).wait_for()
        results["drawer_mobile_width"] = round(drawer.bounding_box()["width"])
        capture(page, "09-drawer-mobile.png")
        results["overflows"]["mobile_drawer"] = overflow_state(page)

        page.evaluate("window.deCloseDrawer && window.deCloseDrawer()")
        page.set_viewport_size({"width": 820, "height": 1180})
        page.goto(f"{dashboard}?section=programme&view=maquettes", wait_until="networkidle")
        capture(page, "10-maquettes-tablet.png")
        results["overflows"]["tablet_maquettes"] = overflow_state(page)

        browser.close()
    return results


def main():
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    journal_path = ROOT / "test_db.sqlite3-journal"
    journal_bytes = journal_path.read_bytes() if journal_path.exists() else None
    session_key = seed_database()
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
    required = (
        "htmx_navigation",
        "class_form_errors",
        "class_created",
        "drawer_opened",
        "ec_created",
        "maquette_navigation",
    )
    if results["console_errors"] or results["page_errors"]:
        raise SystemExit(1)
    if any(item["overflow"] for item in results["overflows"].values()):
        raise SystemExit(1)
    if not all(results[item] for item in required):
        raise SystemExit(1)
    if results["drawer_mobile_width"] > 390:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
