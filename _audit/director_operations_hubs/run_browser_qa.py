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
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY, get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.core.management import call_command
from playwright.sync_api import sync_playwright

from academics.models import AcademicClass, AcademicEnrollment, AcademicYear
from accounts.models import BranchCashMovement, BranchExpense, PayrollEntry, TeacherHonorariumEntry
from admissions.models import Candidature
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme
from inscriptions.models import Inscription
from notifier.models import NotificationMessage
from notifier.services import NotificationBus
from portal.models import TransferRequest
from students.models import Student


def create_user(username, branch, position, first_name, last_name, role=""):
    user = get_user_model().objects.create_user(
        username=username,
        first_name=first_name,
        last_name=last_name,
        email=f"{username}@example.test",
        password=None,
    )
    user.profile.branch = branch
    user.profile.position = position
    user.profile.role = role
    user.profile.save(update_fields=["branch", "position", "role", "updated_at"])
    return user


def seed_database():
    database_name = str(settings.DATABASES["default"]["NAME"])
    if not database_name.endswith("test_db.sqlite3"):
        raise RuntimeError(f"Unexpected QA database: {database_name}")
    call_command("flush", interactive=False, verbosity=0)
    branch = Branch.objects.create(name="Bamako Centre", code="BCT", slug="bct-hubs")
    cycle = Cycle.objects.create(name="Licence Hubs", min_duration_years=1, max_duration_years=4)
    diploma = Diploma.objects.create(name="Licence Hubs", level="superieur")
    filiere = Filiere.objects.create(name="Gestion Hubs")
    programme = Programme.objects.create(
        title="Gestion des entreprises",
        filiere=filiere,
        cycle=cycle,
        diploma_awarded=diploma,
        duration_years=3,
        short_description="Programme QA",
        description="Programme QA des centres operationnels.",
    )
    academic_year = AcademicYear.objects.create(
        name="2026-2027",
        start_date=date(2026, 8, 1),
        end_date=date(2027, 7, 31),
        is_active=True,
    )
    source_class = AcademicClass.objects.create(
        name="L1 Gestion",
        programme=programme,
        branch=branch,
        academic_year=academic_year,
        level="L1",
        study_level="LICENCE",
    )
    target_class = AcademicClass.objects.create(
        name="L2 Gestion",
        programme=programme,
        branch=branch,
        academic_year=academic_year,
        level="L2",
        study_level="LICENCE",
    )
    director = create_user(
        "qa_director_hubs", branch, "director_of_studies", "Moussa", "Sylla", "executive"
    )
    secretary = create_user("qa_secretary_hubs", branch, "secretary", "Awa", "Keita")
    manager = create_user("qa_manager_hubs", branch, "annex_manager", "Baba", "Diarra")
    teacher = create_user("qa_teacher_hubs", branch, "teacher", "Aminata", "Traore", "teacher")
    student_user = get_user_model().objects.create_user(
        username="qa_student_hubs", first_name="Sira", last_name="Diallo", password=None
    )
    candidature = Candidature.objects.create(
        programme=programme,
        branch=branch,
        academic_year=academic_year.name,
        entry_year=1,
        first_name="Sira",
        last_name="Diallo",
        birth_date=date(2003, 2, 1),
        birth_place="Bamako",
        gender="female",
        phone="70000001",
        email="qa.student.hubs@example.test",
        status="accepted",
    )
    inscription = Inscription.objects.create(
        candidature=candidature,
        academic_class=source_class,
        amount_due=150000,
        status=Inscription.STATUS_ACTIVE,
    )
    student = Student.objects.create(
        user=student_user,
        inscription=inscription,
        matricule="QA-HUB-001",
        is_active=True,
    )
    enrollment = AcademicEnrollment.objects.create(
        inscription=inscription,
        student=student_user,
        programme=programme,
        branch=branch,
        academic_year=academic_year,
        academic_class=source_class,
    )
    student.current_academic_enrollment = enrollment
    student.save(update_fields=["current_academic_enrollment"])
    TransferRequest.objects.create(
        branch=branch,
        enrollment=enrollment,
        transfer_type=TransferRequest.TYPE_CLASS,
        source_class=source_class,
        target_class=target_class,
        reason="Reorientation validee par le conseil pedagogique.",
        created_by=director,
    )
    PayrollEntry.objects.create(
        branch=branch,
        employee=secretary,
        period_month=date(2026, 8, 1),
        base_salary=175000,
        status=PayrollEntry.STATUS_READY,
    )
    TeacherHonorariumEntry.objects.create(
        branch=branch,
        teacher=teacher,
        period_month=date(2026, 8, 1),
        hourly_rate=5000,
        validated_hours=24,
        status=TeacherHonorariumEntry.STATUS_READY,
    )
    BranchCashMovement.objects.create(
        branch=branch,
        movement_type=BranchCashMovement.TYPE_IN,
        source=BranchCashMovement.SOURCE_STUDENT_PAYMENT,
        amount=500000,
        label="Paiements etudiants",
        movement_date=date(2026, 8, 1),
        created_by=manager,
    )
    BranchExpense.objects.create(
        branch=branch,
        title="Fournitures pedagogiques",
        category=BranchExpense.CATEGORY_SUPPLIES,
        amount=45000,
        expense_date=date(2026, 8, 1),
        status=BranchExpense.STATUS_SUBMITTED,
        created_by=manager,
    )
    NotificationBus.notify(
        recipient=director,
        actor=secretary,
        event_type="internal_message",
        title="Dossiers de rentree",
        body="Les dossiers des nouveaux etudiants sont disponibles pour verification.",
        source_app="portal",
        channels=(NotificationMessage.CHANNEL_IN_APP,),
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
            raise RuntimeError("QA server stopped unexpectedly.")
        try:
            with urlopen(f"{BASE_URL}/accounts/login/", timeout=1):
                return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("QA server did not start.")


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
        "independent_navigation": False,
        "transfer_modal": False,
        "message_sent": False,
        "finance_request": False,
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

        page.goto(f"{dashboard}?section=transferts", wait_until="networkidle")
        page.get_by_role("heading", name="Transferts", exact=True).wait_for()
        results["independent_navigation"] = all(
            page.locator(f'[data-nav-key="{key}"]').count() == 1
            for key in ("transferts", "messagerie", "finance")
        )
        results["overflows"]["transfers_desktop"] = overflow_state(page)
        capture(page, "01-transfers-desktop.png")
        page.get_by_role("button", name="Nouveau transfert").click()
        page.get_by_role("heading", name="Nouveau transfert").wait_for()
        results["transfer_modal"] = page.locator('select[name="enrollment_id"]').is_visible()
        capture(page, "02-transfer-modal-desktop.png")
        page.locator('[data-ui-core="modal"] header').get_by_role("button", name="Fermer").click()

        page.goto(f"{dashboard}?section=messagerie", wait_until="networkidle")
        page.get_by_role("heading", name="Messagerie interne").wait_for()
        results["overflows"]["messages_desktop"] = overflow_state(page)
        capture(page, "03-messages-desktop.png")
        page.get_by_role("button", name="Nouveau message").click()
        form = page.locator("#director-modal-content form")
        form.locator('select[name="recipient"]').select_option(label="Baba Diarra")
        form.locator('input[name="title"]').fill("Conseil pedagogique")
        form.locator('textarea[name="body"]').fill("Merci de confirmer la disponibilite de la salle.")
        form.get_by_role("button", name="Envoyer").click()
        page.get_by_role("heading", name="Conseil pedagogique", exact=True).wait_for()
        results["message_sent"] = True
        capture(page, "04-message-sent-desktop.png")

        page.goto(f"{dashboard}?section=finance&period=2026-08", wait_until="networkidle")
        page.get_by_role("heading", name="Finance", exact=True).wait_for()
        results["overflows"]["finance_desktop"] = overflow_state(page)
        capture(page, "05-finance-desktop.png")
        page.get_by_role("tab", name="Salaires").click()
        page.get_by_text("Awa Keita", exact=True).wait_for()
        page.get_by_role("button", name="Transmettre").click()
        page.get_by_text("Demande transmise", exact=False).wait_for()
        results["finance_request"] = True
        capture(page, "06-finance-request-desktop.png")

        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(f"{dashboard}?section=transferts&view=pending", wait_until="networkidle")
        page.locator("#director-transfer-subcontent h2").wait_for()
        results["overflows"]["transfers_mobile"] = overflow_state(page)
        capture(page, "07-transfers-mobile.png")
        page.goto(f"{dashboard}?section=messagerie", wait_until="networkidle")
        page.get_by_role("heading", name="Messagerie interne").wait_for()
        results["overflows"]["messages_mobile"] = overflow_state(page)
        capture(page, "08-messages-mobile.png")
        browser.close()
    return results


def main():
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
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
    (AUDIT_DIR / "qa-results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(results, ensure_ascii=False, indent=2))
    required = ("independent_navigation", "transfer_modal", "message_sent", "finance_request")
    if results["console_errors"] or results["page_errors"]:
        raise SystemExit(1)
    if any(item["overflow"] for item in results["overflows"].values()):
        raise SystemExit(1)
    if not all(results[item] for item in required):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
