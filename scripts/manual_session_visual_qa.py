"""Playwright recipe for SYSTEM session security on a local manual-test server."""

from __future__ import annotations

import asyncio
from datetime import date
import json
import os
from pathlib import Path
import secrets
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.sessions.backends.db import SessionStore
from django.db import close_old_connections
from django.test import Client
from django.utils import timezone
from playwright.async_api import async_playwright

from accounts.models import AccountSecurityEvent, Profile
from accounts.session_policy import SESSION_ACTIVITY_KEY, SESSION_STARTED_KEY
from admissions.models import Candidature
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme
from inscriptions.models import Inscription
from students.models import Student


BASE_URL = os.getenv("ESFE_QA_BASE_URL", "http://127.0.0.1:8010")
ARTIFACT_DIR = Path(os.getenv("ESFE_QA_ARTIFACT_DIR", "test_artifacts/session_visual_qa"))
PREFIX = "__qa_session_"
POSITIONS = (
    ("student", "Etudiant"),
    ("teacher", "Enseignant"),
    ("annex_manager", "Gestionnaire"),
    ("academic_supervisor", "Administratif"),
    ("super_admin", "Super administrateur"),
)


def _cleanup_users():
    User = get_user_model()
    users = list(User.objects.filter(username__startswith=PREFIX))
    qa_candidatures = Candidature.objects.filter(email__startswith=PREFIX)
    qa_inscriptions = Inscription.objects.filter(candidature__in=qa_candidatures)
    AccountSecurityEvent.objects.filter(user__in=users).delete()
    Student.objects.filter(user__in=users).delete()
    Student.objects.filter(matricule__startswith="ESFE-QA-").delete()
    User.objects.filter(pk__in=[user.pk for user in users]).delete()
    qa_inscriptions.delete()
    qa_candidatures.delete()


def _create_accounts(password):
    _cleanup_users()
    User = get_user_model()
    branch = Branch.objects.first()
    programme = Programme.objects.first()
    if branch is None:
        branch = Branch.objects.create(
            name="Annexe QA Sessions",
            code="QASESS",
            slug="annexe-qa-sessions",
            city="Bamako",
        )
    if programme is None:
        cycle, _ = Cycle.objects.get_or_create(
            name="Cycle QA Sessions",
            defaults={"min_duration_years": 1, "max_duration_years": 1},
        )
        diploma, _ = Diploma.objects.get_or_create(
            name="Diplome QA Sessions",
            defaults={"level": "superieur"},
        )
        filiere, _ = Filiere.objects.get_or_create(name="Filiere QA Sessions")
        programme = Programme.objects.create(
            title="Programme QA Sessions",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=1,
            short_description="Programme technique pour la recette des sessions.",
            description="Programme technique pour la recette des sessions.",
        )

    accounts = {}
    for index, (position, label) in enumerate(POSITIONS):
        username = f"{PREFIX}{position}"
        user = User.objects.create_user(
            username=username,
            email=f"{username}@qa.invalid",
            password=None,
            first_name="QA",
            last_name=label,
            is_staff=position == "super_admin",
            is_superuser=position == "super_admin",
        )
        profile = user.profile
        profile.position = position
        profile.role = "student" if position == "student" else ("teacher" if position == "teacher" else ("superadmin" if position == "super_admin" else ""))
        profile.user_type = "staff"
        profile.branch = None if position == "super_admin" else branch
        profile.save(update_fields=["position", "role", "user_type", "branch", "updated_at"])
        if position == "annex_manager":
            group, _ = Group.objects.get_or_create(name="gestionnaire")
            user.groups.add(group)
        if position == "student":
            candidature = Candidature.objects.create(
                programme=programme,
                branch=branch,
                academic_year="2026-2027",
                first_name="QA",
                last_name="Etudiant",
                birth_date=date(2000, 1, 1),
                birth_place="Bamako",
                gender="male",
                phone="70000000",
                email=f"{username}@qa.invalid",
                status="accepted",
            )
            inscription = Inscription.objects.create(candidature=candidature, amount_due=1, status="active")
            Student.objects.create(user=user, inscription=inscription, matricule=f"ESFE-QA-{int(time.time())}")
        accounts[position] = {"username": username, "label": label, "user_id": user.pk}

    active = User.objects.create_user(
        username=f"{PREFIX}active_secretary",
        email="qa-active-secretary@qa.invalid",
        password=None,
        first_name="QA",
        last_name="Activite",
    )
    active.profile.position = "secretary"
    active.profile.user_type = "staff"
    active.profile.branch = branch
    active.profile.save(update_fields=["position", "user_type", "branch", "updated_at"])
    accounts["active_secretary"] = {"username": active.username, "label": "Secretaire active", "user_id": active.pk}

    revoked = User.objects.create_user(
        username=f"{PREFIX}revoked_admin",
        email="qa-revoked-admin@qa.invalid",
        password=None,
        first_name="QA",
        last_name="Revocation",
    )
    revoked.profile.position = "secretary"
    revoked.profile.user_type = "staff"
    revoked.profile.branch = branch
    revoked.profile.save(update_fields=["position", "user_type", "branch", "updated_at"])
    accounts["revoked_admin"] = {"username": revoked.username, "label": "Administratif revoque", "user_id": revoked.pk}
    return accounts


def _force_absolute_expiry(session_key):
    close_old_connections()
    store = SessionStore(session_key=session_key)
    store[SESSION_STARTED_KEY] = timezone.now().timestamp() - (13 * 60 * 60)
    store[SESSION_ACTIVITY_KEY] = timezone.now().timestamp()
    store.save(must_create=False)
    close_old_connections()


def _force_idle_age(session_key, age_seconds):
    close_old_connections()
    store = SessionStore(session_key=session_key)
    now = timezone.now().timestamp()
    store[SESSION_STARTED_KEY] = now - age_seconds
    store[SESSION_ACTIVITY_KEY] = now - age_seconds
    store.save(must_create=False)
    close_old_connections()


def _administratively_revoke(user_id):
    close_old_connections()
    from accounts.session_security import revoke_user_sessions

    user = get_user_model().objects.get(pk=user_id)
    revoked = revoke_user_sessions(user, global_scope=True)
    close_old_connections()
    return revoked


def _issue_authenticated_session(user_id):
    """Create a genuine Django login session without reloading the login UI."""
    close_old_connections()
    client = Client()
    user = get_user_model().objects.get(pk=user_id)
    client.force_login(user)
    session_key = client.cookies[settings.SESSION_COOKIE_NAME].value
    close_old_connections()
    return session_key


def _audit_snapshot(user_ids, started_at):
    rows = list(
        AccountSecurityEvent.objects.filter(user_id__in=user_ids, created_at__gte=started_at)
        .values("user_id", "event_type", "authentication_method", "reason", "metadata")
        .order_by("created_at")
    )
    forbidden = ("password", "pin", "cookie", "session_key", "token")
    serialized = json.dumps(rows, ensure_ascii=False).lower()
    secret_free = not any(f'"{key}":' in serialized and "[redacted]" not in serialized for key in forbidden)
    return rows, secret_free


async def _login(browser, account, password, *, pages=1):
    session_key = await sync_to_async(_issue_authenticated_session, thread_sensitive=True)(account["user_id"])
    context = await browser.new_context(viewport={"width": 1440, "height": 900})
    context.set_default_timeout(120000)
    await context.add_cookies([
        {
            "name": settings.SESSION_COOKIE_NAME,
            "value": session_key,
            "url": BASE_URL,
        },
        {
            "name": "cookie_consent_accepted",
            "value": "true",
            "url": BASE_URL,
        },
    ])
    page = await context.new_page()
    page.set_default_navigation_timeout(120000)
    state = {"activity_requests": 0, "websocket_opened": 0, "websocket_closed": 0}

    def on_request(request):
        if "/portal/session/activity/" in request.url:
            state["activity_requests"] += 1

    def on_websocket(ws):
        state["websocket_opened"] += 1
        ws.on("close", lambda: state.__setitem__("websocket_closed", state["websocket_closed"] + 1))

    page.on("request", on_request)
    page.on("websocket", on_websocket)
    await page.goto(f"{BASE_URL}/portal/dashboard/", wait_until="domcontentloaded")
    await page.wait_for_load_state("domcontentloaded")
    if "/login/" in page.url:
        raise AssertionError(f"Connexion refusee pour {account['label']}")

    extra_pages = []
    for _ in range(max(0, pages - 1)):
        extra = await context.new_page()
        extra.on("request", on_request)
        extra.on("websocket", on_websocket)
        await extra.goto(page.url, wait_until="domcontentloaded")
        extra_pages.append(extra)
    return {"context": context, "page": page, "extra_pages": extra_pages, "state": state, "dashboard_url": page.url}


async def _profile_recipe(entry, position):
    page = entry["page"]
    await page.goto(f"{BASE_URL}/portal/account/edit/", wait_until="domcontentloaded")
    body = (await page.locator("body").inner_text()).lower()
    portal_shell = "esfe portal" in body and "informations de compte" in body
    public_absent = "biographie" not in body and "domaine d'expertise" not in body
    phone = page.locator('input[name="phone"]')
    if await phone.count():
        await phone.fill(f"+22370000{len(position):03d}")
    await page.locator("form").first.locator("button", has_text="Enregistrer").click()
    await page.wait_for_load_state("domcontentloaded")
    returned = "/portal/" in page.url or "/superadmin/" in page.url
    status = await entry["context"].request.get(f"{BASE_URL}/portal/session/status/", headers={"Accept": "application/json"})
    return {"portal_shell": portal_shell, "public_absent": public_absent, "returned_dashboard": returned, "session_continues": status.status == 200}


async def _wait_modal(page, timeout_ms=135000):
    modal = page.locator("#esfe-session-modal")
    await modal.wait_for(state="visible", timeout=timeout_ms)
    countdown = (await page.locator("#esfe-session-countdown").inner_text()).strip()
    return countdown


async def _run_recipe(accounts, password):
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    results = {position: {"position": label} for position, label in POSITIONS}
    diagnostics = {"defects": [], "timings": {}, "audit": {}}
    started = time.monotonic()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        normal = {}
        prolonged = {}
        login_jobs = []
        for position, _ in POSITIONS:
            login_jobs.extend((
                _login(browser, accounts[position], password),
                _login(
                    browser,
                    accounts[position],
                    password,
                    pages=3 if position == "annex_manager" else 1,
                ),
            ))
        logged_in = await asyncio.gather(*login_jobs)
        for index, (position, _) in enumerate(POSITIONS):
            normal[position] = logged_in[index * 2]
            prolonged[position] = logged_in[index * 2 + 1]
            results[position]["dashboard"] = "/login/" not in normal[position]["page"].url
        profile_results = await asyncio.gather(*(
            _profile_recipe(prolonged[position], position) for position, _ in POSITIONS
        ))
        for (position, _), profile_result in zip(POSITIONS, profile_results, strict=True):
            results[position]["profile"] = profile_result

        active = await _login(browser, accounts["active_secretary"], password)

        # Unsaved profile form remains open during the student warning.
        student_form_page = prolonged["student"]["page"]
        await student_form_page.goto(f"{BASE_URL}/portal/account/edit/", wait_until="domcontentloaded")
        first_name = student_form_page.locator('input[name="first_name"]')
        await first_name.fill("QA non enregistre")

        # Absolute timeout is checked immediately in an isolated session.
        absolute = await _login(browser, accounts["teacher"], password)
        cookies = await absolute["context"].cookies()
        session_cookie = next(item["value"] for item in cookies if item["name"] == "sessionid")
        await sync_to_async(_force_absolute_expiry, thread_sensitive=True)(session_cookie)
        absolute_response = await absolute["context"].request.get(
            f"{BASE_URL}/portal/session/status/",
            headers={"Accept": "application/json"},
        )
        diagnostics["absolute_timeout"] = absolute_response.status == 401
        await absolute["context"].close()

        revoked = await _login(browser, accounts["revoked_admin"], password)
        await sync_to_async(_administratively_revoke, thread_sensitive=True)(accounts["revoked_admin"]["user_id"])
        revoked_response = await revoked["context"].request.get(
            f"{BASE_URL}/portal/session/status/", headers={"Accept": "application/json"}
        )
        diagnostics["administrative_revocation"] = revoked_response.status == 401
        await revoked["context"].close()

        async def keep_active():
            while True:
                page = active["page"]
                for _ in range(12):
                    await page.keyboard.press("Tab")
                await asyncio.sleep(45)

        active_task = asyncio.create_task(keep_active())

        manager_pages = [prolonged["annex_manager"]["page"], *prolonged["annex_manager"]["extra_pages"]]

        # Wait on each session's authoritative timer instead of the machine clock.
        async def inspect_first_warning(position):
            page = normal[position]["page"]
            try:
                countdown = await _wait_modal(page, timeout_ms=180000)
                results[position]["modal"] = True
                results[position]["countdown"] = bool(countdown and ":" in countdown)
                await page.screenshot(path=str(ARTIFACT_DIR / f"{position}_warning.png"), full_page=True)
            except Exception as exc:
                results[position]["modal"] = False
                results[position]["countdown"] = False
                diagnostics["defects"].append(f"modal {position}: {exc}")
            normal[position]["ws_closed_before_expiry"] = normal[position]["state"]["websocket_closed"]

            ppage = prolonged[position]["page"]
            try:
                await _wait_modal(ppage, timeout_ms=180000)
                if position == "student":
                    results[position]["unsaved_form_warning"] = await student_form_page.locator(
                        "#esfe-session-dirty-warning"
                    ).is_visible()
                    results[position]["unsaved_field_preserved"] = (
                        await first_name.input_value() == "QA non enregistre"
                    )
                before = prolonged[position]["state"]["activity_requests"]
                await ppage.click("#esfe-session-continue")
                await ppage.locator("#esfe-session-modal").wait_for(state="hidden", timeout=10000)
                status = await prolonged[position]["context"].request.get(
                    f"{BASE_URL}/portal/session/status/", headers={"Accept": "application/json"}
                )
                payload = await status.json()
                results[position]["prolongation"] = (
                    status.status == 200 and payload.get("remaining_seconds", 0) >= 165
                )
                results[position]["throttled"] = (
                    prolonged[position]["state"]["activity_requests"] - before <= 2
                )
            except Exception as exc:
                results[position]["prolongation"] = False
                diagnostics["defects"].append(f"prolongation {position}: {exc}")

        await asyncio.gather(*(inspect_first_warning(position) for position, _ in POSITIONS))
        diagnostics["timings"]["first_warning_elapsed_seconds"] = round(time.monotonic() - started, 1)

        # Multi-tab synchronization for manager.
        await asyncio.sleep(1)
        results["annex_manager"]["multi_tabs_extended"] = all([
            not await page.locator("#esfe-session-modal").is_visible() for page in manager_pages
        ])

        # Normal sessions expire one minute after the warning.
        async def wait_for_login(page, timeout_ms=100000):
            try:
                await page.wait_for_url("**/accounts/login/**", timeout=timeout_ms)
            except Exception:
                pass

        await asyncio.gather(*(wait_for_login(normal[position]["page"]) for position, _ in POSITIONS))
        diagnostics["timings"]["idle_expiry_elapsed_seconds"] = round(time.monotonic() - started, 1)
        for position, _ in POSITIONS:
            page = normal[position]["page"]
            body = (await page.locator("body").inner_text()).lower()
            results[position]["redirect_login"] = "/login/" in page.url
            results[position]["expiry_message"] = "expir" in body
            hx = await normal[position]["context"].request.get(
                f"{BASE_URL}/portal/account/security/",
                headers={"HX-Request": "true"},
                fail_on_status_code=False,
            )
            ajax = await normal[position]["context"].request.get(
                f"{BASE_URL}/portal/account/security/",
                headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
                fail_on_status_code=False,
            )
            results[position]["htmx"] = hx.status == 401 and bool(hx.headers.get("hx-redirect")) and not (await hx.body())
            results[position]["ajax"] = ajax.status == 401 and (await ajax.json()).get("error") == "session_expired"
            results[position]["polling_did_not_extend"] = results[position]["redirect_login"]
            results[position]["websocket_closed"] = normal[position]["state"]["websocket_closed"] > normal[position]["ws_closed_before_expiry"]
            await page.screenshot(path=str(ARTIFACT_DIR / f"{position}_expired_login.png"), full_page=True)

        # Second warning after extension; visual hiding alone must not extend.
        teacher_page = prolonged["teacher"]["page"]
        await _wait_modal(teacher_page, timeout_ms=180000)
        diagnostics["timings"]["second_warning_elapsed_seconds"] = round(time.monotonic() - started, 1)
        teacher_before = prolonged["teacher"]["state"]["activity_requests"]
        await teacher_page.evaluate("document.getElementById('esfe-session-modal').classList.add('hidden')")
        results["teacher"]["visual_hide_no_server_call"] = prolonged["teacher"]["state"]["activity_requests"] == teacher_before

        # Extended sessions must still expire one minute after their second warning.
        await asyncio.gather(*(wait_for_login(prolonged[position]["page"]) for position, _ in POSITIONS))
        diagnostics["timings"]["extended_expiry_elapsed_seconds"] = round(time.monotonic() - started, 1)
        await asyncio.sleep(2)
        for position, _ in POSITIONS:
            page = prolonged[position]["page"]
            results[position]["expires_after_extension"] = "/login/" in page.url
            if position == "annex_manager":
                results[position]["multi_tabs_expired"] = all(
                    "/login/" in tab.url for tab in manager_pages
                )

        active_task.cancel()
        try:
            await active_task
        except asyncio.CancelledError:
            pass
        active_status = await active["context"].request.get(
            f"{BASE_URL}/portal/session/status/", headers={"Accept": "application/json"}
        )
        diagnostics["real_activity_kept_session"] = active_status.status == 200
        diagnostics["activity_request_count"] = active["state"]["activity_requests"]
        diagnostics["activity_throttled"] = active["state"]["activity_requests"] <= 9
        await active["page"].locator('form[action*="logout"]').first.evaluate("form => form.submit()")
        await asyncio.sleep(1)

        for entry in [*normal.values(), *prolonged.values(), active]:
            await entry["context"].close()
        await browser.close()

    diagnostics["elapsed_seconds"] = round(time.monotonic() - started, 1)
    return results, diagnostics


async def _run_edge_recipe(accounts, password):
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        dirty = await _login(browser, accounts["student"], password)
        dirty_cookies = await dirty["context"].cookies()
        dirty_session = next(
            item["value"] for item in dirty_cookies if item["name"] == settings.SESSION_COOKIE_NAME
        )
        await sync_to_async(_force_idle_age, thread_sensitive=True)(dirty_session, 110)
        dirty_page = dirty["page"]
        await dirty_page.goto(f"{BASE_URL}/portal/account/edit/", wait_until="domcontentloaded")
        dirty_field = dirty_page.locator('input[name="first_name"]')
        await dirty_field.fill("QA sensible non enregistre")
        await _wait_modal(dirty_page, timeout_ms=30000)
        dirty_warning = await dirty_page.locator("#esfe-session-dirty-warning").is_visible()
        field_preserved = await dirty_field.input_value() == "QA sensible non enregistre"
        storage = await dirty_page.evaluate(
            "Object.fromEntries(Array.from({length: localStorage.length}, (_, i) => "
            "[localStorage.key(i), localStorage.getItem(localStorage.key(i))]))"
        )
        sensitive_not_stored = "QA sensible non enregistre" not in json.dumps(storage, ensure_ascii=False)
        await dirty_page.screenshot(
            path=str(ARTIFACT_DIR / "student_unsaved_warning.png"), full_page=True
        )
        await dirty_page.click("#esfe-session-continue")
        await dirty["context"].close()

        expired = await _login(browser, accounts["student"], password)
        expired_cookies = await expired["context"].cookies()
        expired_session = next(
            item["value"] for item in expired_cookies if item["name"] == settings.SESSION_COOKIE_NAME
        )
        await sync_to_async(_force_idle_age, thread_sensitive=True)(expired_session, 170)
        expired_page = expired["page"]
        await expired_page.reload(wait_until="domcontentloaded")
        await expired_page.wait_for_url("**/accounts/login/**", timeout=30000)
        expiry_message = await expired_page.locator("#session-expired-message").is_visible()

        await expired_page.go_back(wait_until="domcontentloaded")
        await expired_page.wait_for_timeout(1000)
        protected = await expired["context"].request.get(
            f"{BASE_URL}/portal/account/security/",
            headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
            fail_on_status_code=False,
        )
        old_page_not_exploitable = protected.status == 401
        await expired_page.screenshot(
            path=str(ARTIFACT_DIR / "student_back_after_expiry.png"), full_page=True
        )

        websocket_result = await expired_page.evaluate(
            """() => new Promise(resolve => {
              const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
              const socket = new WebSocket(`${scheme}://${location.host}/ws/notifications/`);
              let opened = false;
              let settled = false;
              const finish = value => { if (!settled) { settled = true; resolve(value); } };
              socket.onopen = () => { opened = true; };
              socket.onclose = event => finish({opened, code: event.code});
              socket.onerror = () => {};
              setTimeout(() => { try { socket.close(); } catch (_) {} finish({opened, code: 0, timeout: true}); }, 8000);
            })"""
        )
        await expired["context"].close()
        await browser.close()

    return {
        "dirty_warning": dirty_warning,
        "field_preserved": field_preserved,
        "sensitive_form_absent_from_local_storage": sensitive_not_stored,
        "expiry_message": expiry_message,
        "old_page_not_exploitable_after_back": old_page_not_exploitable,
        "websocket_reconnect_refused": (
            websocket_result.get("code") in {4401, 4403}
            or (not websocket_result.get("opened") and websocket_result.get("code") == 1006)
        ),
        "websocket_reconnect": websocket_result,
    }


def main():
    password = secrets.token_urlsafe(24)
    started_at = timezone.now()
    accounts = {}
    try:
        accounts = _create_accounts(password)
        run_options = {"loop_factory": asyncio.ProactorEventLoop} if sys.platform == "win32" else {}
        if os.getenv("ESFE_QA_EDGE_ONLY") == "1":
            edge_results = asyncio.run(_run_edge_recipe(accounts, password), **run_options)
            edge_report = {"passed": all(bool(value) for key, value in edge_results.items() if key != "websocket_reconnect"), "checks": edge_results}
            rendered_edge_report = json.dumps(edge_report, ensure_ascii=False, indent=2)
            (ARTIFACT_DIR / "edge_report.json").write_text(rendered_edge_report + "\n", encoding="utf-8")
            print(rendered_edge_report)
            return 0 if edge_report["passed"] else 1
        results, diagnostics = asyncio.run(_run_recipe(accounts, password), **run_options)
        rows, secret_free = _audit_snapshot([item["user_id"] for item in accounts.values()], started_at)
        event_types = sorted({row["event_type"] for row in rows})
        diagnostics["audit"] = {
            "events": event_types,
            "secret_free": secret_free,
            "login": AccountSecurityEvent.LOGIN_SUCCESS in event_types,
            "idle": AccountSecurityEvent.IDLE_TIMEOUT in event_types,
            "absolute": AccountSecurityEvent.ABSOLUTE_TIMEOUT in event_types,
            "voluntary_logout": AccountSecurityEvent.LOGOUT_VOLUNTARY in event_types,
            "administrative_revocation": AccountSecurityEvent.ADMIN_REVOKED in event_types,
        }
        for position, _ in POSITIONS:
            user_events = {row["event_type"] for row in rows if row["user_id"] == accounts[position]["user_id"]}
            results[position]["audit"] = AccountSecurityEvent.LOGIN_SUCCESS in user_events and AccountSecurityEvent.IDLE_TIMEOUT in user_events
        required_common = (
            "modal", "countdown", "prolongation", "redirect_login", "htmx",
            "ajax", "websocket_closed", "expires_after_extension",
        )
        passed = all(all(bool(row.get(key)) for key in required_common) for row in results.values())
        passed = passed and diagnostics["audit"]["secret_free"] and diagnostics["audit"]["idle"] and diagnostics["audit"]["absolute"]
        passed = passed and diagnostics["audit"]["administrative_revocation"] and diagnostics.get("administrative_revocation", False)
        passed = passed and diagnostics.get("real_activity_kept_session", False)
        report = {"passed": passed, "accounts": results, "diagnostics": diagnostics}
        rendered_report = json.dumps(report, ensure_ascii=False, indent=2)
        (ARTIFACT_DIR / "report.json").write_text(rendered_report + "\n", encoding="utf-8")
        print(rendered_report)
        return 0 if passed else 1
    finally:
        _cleanup_users()


if __name__ == "__main__":
    sys.exit(main())
