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
from portal.models import AdministrativeDocument, TeacherDocument


def seed_database():
    database_name = str(settings.DATABASES["default"]["NAME"])
    if not database_name.endswith("test_db.sqlite3"):
        raise RuntimeError(f"Base QA inattendue: {database_name}")
    call_command("flush", interactive=False, verbosity=0)
    branch = Branch.objects.create(name="Bamako Centre", code="BCT", slug="bamako-centre")
    cycle = Cycle.objects.create(name="Licence QA DE", min_duration_years=1, max_duration_years=4)
    diploma = Diploma.objects.create(name="Diplome QA DE", level="superieur")
    filiere = Filiere.objects.create(name="Gestion QA DE")
    programme = Programme.objects.create(
        title="Gestion des organisations",
        filiere=filiere,
        cycle=cycle,
        diploma_awarded=diploma,
        duration_years=3,
        short_description="Programme QA",
        description="Programme QA du Directeur des etudes.",
    )
    academic_year = AcademicYear.objects.create(
        name="2026-2027",
        start_date=date(2026, 10, 1),
        end_date=date(2027, 7, 31),
        is_active=True,
    )
    academic_class = AcademicClass.objects.create(
        name="L1 Gestion",
        programme=programme,
        branch=branch,
        academic_year=academic_year,
        level="L1",
        study_level="LICENCE",
    )
    semester = Semester.objects.create(academic_class=academic_class, number=1)
    ue = UE.objects.create(semester=semester, code="GES101", title="Fondamentaux")
    EC.objects.create(ue=ue, title="Comptabilite generale", credit_required=3, coefficient=2)

    User = get_user_model()
    director = User.objects.create_user(
        username="qa_director_teachers_documents",
        first_name="Moussa",
        last_name="Sylla",
        password=None,
        is_staff=True,
    )
    director.profile.position = "director_of_studies"
    director.profile.role = "executive"
    director.profile.branch = branch
    director.profile.save(update_fields=["position", "role", "branch", "updated_at"])

    for index in range(13):
        teacher = User.objects.create_user(
            username=f"qa_teacher_{index + 1:02d}",
            first_name=f"Prenom{index + 1:02d}",
            last_name=f"Enseignant{index + 1:02d}",
            email=f"enseignant{index + 1:02d}@qa.test",
            password=None,
        )
        teacher.profile.position = "teacher"
        teacher.profile.role = "teacher"
        teacher.profile.branch = branch
        teacher.profile.employee_code = f"ENS-{index + 1:03d}"
        teacher.profile.main_domain = "Gestion"
        teacher.profile.save(
            update_fields=["position", "role", "branch", "employee_code", "main_domain", "updated_at"]
        )

    for index in range(13):
        AdministrativeDocument.objects.create(
            branch=branch,
            doc_type=AdministrativeDocument.TYPE_NOTE_SERVICE,
            reference=f"DE/2026/{index + 1:03d}",
            title=f"Note pedagogique {index + 1:02d}",
            recipients="Equipe pedagogique",
            body="Contenu administratif de controle.",
            status=(
                AdministrativeDocument.STATUS_DRAFT
                if index % 3 == 0
                else AdministrativeDocument.STATUS_PUBLISHED
            ),
            created_by=director,
        )

    session = SessionStore()
    session[SESSION_KEY] = str(director.pk)
    session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    session[HASH_SESSION_KEY] = director.get_session_auth_hash()
    session.save()
    return session.session_key


def wait_for_server(process):
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError("Le serveur QA s'est arrete.")
        try:
            with urlopen(f"{BASE_URL}/accounts/login/", timeout=1):
                return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("Le serveur QA n'a pas demarre.")


def overflow_state(page):
    return page.evaluate(
        """() => ({width: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
        overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1})"""
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
        "teacher_htmx_navigation": False,
        "teacher_form_errors": False,
        "teacher_created": False,
        "assignment_created": False,
        "document_form_errors": False,
        "draft_created": False,
        "draft_published": False,
        "modal_desktop_width": 0,
        "modal_mobile_width": 0,
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.add_cookies([{
            "name": settings.SESSION_COOKIE_NAME,
            "value": session_key,
            "url": BASE_URL,
            "httpOnly": True,
            "sameSite": "Lax",
        }])
        page = context.new_page()
        page.on("console", lambda message: results["console_errors"].append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: results["page_errors"].append(str(error)))
        dashboard = f"{BASE_URL}/portal/dashboard/"

        page.goto(f"{dashboard}?section=enseignants&view=overview", wait_until="networkidle")
        page.locator("#director-teacher-subcontent").wait_for()
        capture(page, "01-teachers-overview-desktop.png")
        results["overflows"]["teachers_overview_desktop"] = overflow_state(page)
        navigation_count = page.evaluate("performance.getEntriesByType('navigation').length")
        with page.expect_response(lambda response: "/director/teachers/subcontent/" in response.url):
            page.get_by_role("tab", name="Répertoire").click()
        page.get_by_text("Répertoire de l’annexe").wait_for()
        results["teacher_htmx_navigation"] = page.evaluate("performance.getEntriesByType('navigation').length") == navigation_count
        capture(page, "02-teacher-directory-desktop.png")

        with page.expect_response(lambda response: "/director/teachers/create/" in response.url):
            page.get_by_role("button", name="Nouvel enseignant").click()
        modal = page.locator('[data-ui-core="modal"] section')
        results["modal_desktop_width"] = round(modal.bounding_box()["width"])
        form = page.locator("#director-modal-content form")
        form.get_by_role("button", name="Créer l’enseignant").click()
        page.get_by_text("Ce champ est obligatoire.").first.wait_for()
        results["teacher_form_errors"] = True
        capture(page, "03-teacher-form-errors.png")
        form = page.locator("#director-modal-content form")
        form.locator('input[name="last_name"]').fill("Coulibaly")
        form.locator('input[name="first_name"]').fill("Fatou")
        form.locator('input[name="email"]').fill("fatou.coulibaly@qa.test")
        form.locator('input[name="specialty"]').fill("Comptabilite")
        with page.expect_response(lambda response: "/director/teachers/create/" in response.url):
            form.get_by_role("button", name="Créer l’enseignant").click()
        page.get_by_text("Enseignant cree, affecte et acces generes.").wait_for()
        page.get_by_text("Fatou Coulibaly").wait_for()
        results["teacher_created"] = True
        capture(page, "04-teacher-created.png")

        teacher_row = page.locator("article", has_text="Fatou Coulibaly")
        teacher_row.get_by_role("button", name="Gérer les affectations").click()
        page.locator("#director-modal-content").get_by_text("Fatou Coulibaly").wait_for()
        assignment_form = page.locator("#director-modal-content form").first
        assignment_form.locator('select[name="class_id"]').select_option(index=1)
        page.wait_for_timeout(800)
        assignment_form.locator('input[name="room_label"]').fill("Salle B12")
        assignment_form.locator('input[name="planned_hours"]').fill("24")
        assignment_submit = page.locator('#director-modal-content button[name="action"][value="add"]')
        assignment_submit.wait_for()
        with page.expect_response(lambda response: "/director/teachers/assign/" in response.url):
            assignment_submit.click()
        page.get_by_text("Affectation enregistree :").wait_for()
        results["assignment_created"] = True
        capture(page, "05-assignment-created.png")

        page.goto(f"{dashboard}?section=correspondances&view=overview", wait_until="networkidle")
        capture(page, "06-documents-overview-desktop.png")
        results["overflows"]["documents_overview_desktop"] = overflow_state(page)
        page.get_by_role("tab", name="Rédiger").click()
        document_form = page.locator("#director-document-subcontent form")
        document_form.get_by_role("button", name="Enregistrer le brouillon").click()
        page.get_by_text("Ce champ est obligatoire.").first.wait_for()
        results["document_form_errors"] = True
        capture(page, "07-document-form-errors.png")
        document_form = page.locator("#director-document-subcontent form")
        document_form.locator('input[name="reference"]').fill("DE/2026/100")
        document_form.locator('input[name="title"]').fill("Reunion pedagogique")
        document_form.locator('input[name="recipients"]').fill("Tous les enseignants")
        document_form.locator('textarea[name="body"]').fill("Une reunion pedagogique est programmee lundi matin.")
        with page.expect_response(lambda response: "/director/correspondances/create/" in response.url):
            document_form.get_by_role("button", name="Enregistrer le brouillon").click()
        page.get_by_text("Brouillon enregistre.").wait_for()
        page.get_by_text("Reunion pedagogique").wait_for()
        results["draft_created"] = True
        capture(page, "08-draft-created.png")
        row = page.locator("article", has_text="Reunion pedagogique")
        with page.expect_response(lambda response: "/publish/" in response.url):
            row.get_by_role("button", name="Publier").click()
        page.get_by_text("Document publie.").wait_for()
        results["draft_published"] = True
        capture(page, "09-document-published.png")

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{dashboard}?section=enseignants&view=directory", wait_until="networkidle")
        results["overflows"]["teacher_directory_mobile"] = overflow_state(page)
        capture(page, "10-teacher-directory-mobile.png")
        with page.expect_response(lambda response: "/director/teachers/assign/" in response.url):
            page.get_by_role("button", name="Gérer les affectations").first.click()
        page.locator('#director-modal-content form select[name="class_id"]').wait_for()
        results["modal_mobile_width"] = round(modal.bounding_box()["width"])
        results["overflows"]["teacher_modal_mobile"] = overflow_state(page)
        capture(page, "11-teacher-modal-mobile.png")
        page.evaluate("window.deCloseModal && window.deCloseModal()")
        page.goto(f"{dashboard}?section=correspondances&view=archives", wait_until="networkidle")
        results["overflows"]["document_archives_mobile"] = overflow_state(page)
        capture(page, "12-document-archives-mobile.png")
        browser.close()
    return results


def main():
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    journal_path = ROOT / "test_db.sqlite3-journal"
    journal_bytes = journal_path.read_bytes() if journal_path.exists() else None
    session_key = seed_database()
    process = subprocess.Popen(
        [sys.executable, "manage.py", "runserver", "127.0.0.1:8001", "--noreload", "--settings=config.settings_test_local"],
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
    (AUDIT_DIR / "qa-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    required = (
        "teacher_htmx_navigation", "teacher_form_errors", "teacher_created",
        "assignment_created", "document_form_errors", "draft_created", "draft_published",
    )
    if results["console_errors"] or results["page_errors"]:
        raise SystemExit(1)
    if any(item["overflow"] for item in results["overflows"].values()):
        raise SystemExit(1)
    if not all(results[item] for item in required):
        raise SystemExit(1)
    if results["modal_desktop_width"] < 850 or results["modal_mobile_width"] > 390:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
