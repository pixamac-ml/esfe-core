import json
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth import login
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.test import RequestFactory, TestCase, override_settings
from django.contrib.sessions.middleware import SessionMiddleware
from django.urls import reverse
from django.utils import timezone

from branches.models import Branch
from portal.models import AccountSupportState
from accounts.models import AccountSecurityEvent, AccountSessionRecord, Profile
from accounts.session_policy import SESSION_ACTIVITY_KEY, SESSION_ID_KEY, SESSION_STARTED_KEY, close_session_record, log_security_event, policy_for_position
from portal.services.it_support_service import get_scoped_staff_queryset
from accounts.access_context import build_access_context
from accounts.access import can_access, get_user_position
from accounts.policy_v2 import decide
from accounts.position_registry import POSITION_REGISTRY
from accounts.shadow_access import compare_access_classification
from portal.permissions import get_post_login_portal_url


User = get_user_model()


@override_settings(
    SYSTEM_SESSION_IDLE_TIMEOUTS={
        "student": 10,
        "teacher": 10,
        "annex_manager": 6,
        "secretary": 8,
        "super_admin": 6,
    },
    SYSTEM_SESSION_DEFAULT_IDLE_TIMEOUT=8,
    SYSTEM_SESSION_WARNING_SECONDS=2,
    SYSTEM_SESSION_ABSOLUTE_TIMEOUT=20,
)
class SystemSessionExpirationTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name="Annexe session", code="SES", slug="annexe-session")
        self.user = User.objects.create_user(username="system-session-user", password="pass1234")
        profile = self.user.profile
        profile.position = "student"
        profile.branch = self.branch
        profile.save(update_fields=["position", "branch", "updated_at"])
        self.client.force_login(self.user)
        self.base = timezone.now()
        self._set_times(started=self.base, activity=self.base)

    def _set_times(self, *, started, activity):
        session = self.client.session
        session[SESSION_STARTED_KEY] = started.timestamp()
        session[SESSION_ACTIVITY_KEY] = activity.timestamp()
        session.save()

    def test_position_policy_uses_central_registry(self):
        self.assertEqual(policy_for_position("student").idle_seconds, 10)
        self.assertEqual(policy_for_position("annex_manager").idle_seconds, 6)
        self.assertEqual(policy_for_position("secretary").idle_seconds, 8)

    def test_system_page_is_available_before_idle_limit(self):
        with patch("accounts.session_policy.timezone.now", return_value=self.base + timedelta(seconds=9)):
            response = self.client.get(reverse("accounts_portal:system_security"))
        self.assertEqual(response.status_code, 200)

    def test_classic_request_redirects_after_idle_limit_and_audits(self):
        with patch("accounts.session_policy.timezone.now", return_value=self.base + timedelta(seconds=11)):
            response = self.client.get(reverse("accounts_portal:system_security"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)
        self.assertIn("next=", response.url)
        self.assertTrue(AccountSecurityEvent.objects.filter(user=self.user, event_type=AccountSecurityEvent.IDLE_TIMEOUT).exists())
        self.assertFalse(self.client.session.get("_auth_user_id"))

    def test_login_page_explains_known_session_expiry_without_reflecting_unknown_reason(self):
        self.client.logout()
        response = self.client.get(reverse("accounts:login"), {"session_expired": "idle_timeout"})
        self.assertContains(response, 'id="session-expired-message"')
        self.assertContains(response, "Votre session a expiré")

        unknown = self.client.get(reverse("accounts:login"), {"session_expired": "<script>injected</script>"})
        self.assertNotContains(unknown, 'id="session-expired-message"')
        self.assertNotContains(unknown, "injected")

    def test_htmx_expiration_returns_401_with_hx_redirect(self):
        with patch("accounts.session_policy.timezone.now", return_value=self.base + timedelta(seconds=11)):
            response = self.client.get(reverse("accounts_portal:system_security"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 401)
        self.assertIn(reverse("accounts:login"), response.headers["HX-Redirect"])

    def test_ajax_expiration_returns_structured_401(self):
        with patch("accounts.session_policy.timezone.now", return_value=self.base + timedelta(seconds=11)):
            response = self.client.get(
                reverse("accounts_portal:system_security"),
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
                HTTP_ACCEPT="application/json",
            )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "session_expired")

    def test_htmx_after_administrative_revocation_does_not_receive_login_html(self):
        from accounts.session_security import revoke_user_sessions

        revoke_user_sessions(self.user, global_scope=True)
        response = self.client.get(reverse("accounts_portal:system_security"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 401)
        self.assertIn(reverse("accounts:login"), response.headers["HX-Redirect"])
        self.assertEqual(response.content, b"")

    def test_expired_post_does_not_execute_business_update(self):
        with patch("accounts.session_policy.timezone.now", return_value=self.base + timedelta(seconds=11)):
            response = self.client.post(
                reverse("accounts_portal:system_profile_edit"),
                {"first_name": "Ne doit pas changer", "last_name": "Bloque"},
            )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertNotEqual(self.user.first_name, "Ne doit pas changer")

    def test_absolute_timeout_wins_despite_recent_activity(self):
        self._set_times(started=self.base, activity=self.base + timedelta(seconds=19))
        with patch("accounts.session_policy.timezone.now", return_value=self.base + timedelta(seconds=21)):
            response = self.client.get(reverse("accounts_portal:system_security"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(AccountSecurityEvent.objects.filter(user=self.user, event_type=AccountSecurityEvent.ABSOLUTE_TIMEOUT).exists())

    def test_polling_status_does_not_extend_activity(self):
        original = self.client.session[SESSION_ACTIVITY_KEY]
        with patch("accounts.session_policy.timezone.now", return_value=self.base + timedelta(seconds=5)):
            response = self.client.get(reverse("accounts_portal:system_session_status"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session[SESSION_ACTIVITY_KEY], original)

    def test_real_activity_endpoint_extends_session(self):
        with patch("accounts.session_policy.timezone.now", return_value=self.base + timedelta(seconds=5)):
            response = self.client.post(reverse("accounts_portal:system_session_activity"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session[SESSION_ACTIVITY_KEY], (self.base + timedelta(seconds=5)).timestamp())

    def test_voluntary_logout_is_audited(self):
        response = self.client.post(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(AccountSecurityEvent.objects.filter(user=self.user, event_type=AccountSecurityEvent.LOGOUT_VOLUNTARY).exists())
        self.assertTrue(AccountSessionRecord.objects.filter(user=self.user, end_reason=AccountSessionRecord.END_VOLUNTARY).exists())

    def test_public_account_is_not_subject_to_system_timeout(self):
        public = User.objects.create_user(username="public-session-user", password="pass1234")
        self.client.force_login(public)
        session = self.client.session
        session[SESSION_STARTED_KEY] = (self.base - timedelta(days=1)).timestamp()
        session[SESSION_ACTIVITY_KEY] = (self.base - timedelta(days=1)).timestamp()
        session.save()
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)

    def test_common_portal_shell_contains_multitab_and_unsaved_form_manager(self):
        response = self.client.get(reverse("accounts_portal:system_security"))
        self.assertContains(response, "BroadcastChannel")
        self.assertContains(response, "localStorage")
        self.assertContains(response, "modifications non enregistrees")

    def test_required_positions_expire_at_their_configured_limit(self):
        expected_limits = {
            "student": 10,
            "teacher": 10,
            "annex_manager": 6,
            "secretary": 8,
            "super_admin": 6,
        }
        for index, (position, limit) in enumerate(expected_limits.items()):
            with self.subTest(position=position):
                user = User.objects.create_user(username=f"timeout-position-{index}", password="pass1234")
                profile = user.profile
                profile.position = position
                profile.branch = None if position == "super_admin" else self.branch
                profile.save(update_fields=["position", "branch", "updated_at"])
                self.client.force_login(user)
                self._set_times(started=self.base, activity=self.base)
                with patch("accounts.session_policy.timezone.now", return_value=self.base + timedelta(seconds=limit - 1)):
                    before = self.client.get(reverse("accounts_portal:system_security"))
                self.assertEqual(before.status_code, 200)
                with patch("accounts.session_policy.timezone.now", return_value=self.base + timedelta(seconds=limit + 1)):
                    after = self.client.get(reverse("accounts_portal:system_security"))
                self.assertEqual(after.status_code, 302)


class SessionSecurityAuditTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name="Annexe audit session", code="AUS", slug="annexe-audit-session")
        self.user = User.objects.create_user(username="session-audit-user", password="pass1234")
        profile = self.user.profile
        profile.position = "teacher"
        profile.branch = self.branch
        profile.save(update_fields=["position", "branch", "updated_at"])

    def _request_with_session(self):
        request = RequestFactory().get("/accounts/login/")
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        return request

    def test_password_and_card_login_methods_are_audited_but_public_is_not(self):
        self.client.post(reverse("accounts:login"), {"username": self.user.username, "password": "pass1234"})
        self.assertTrue(AccountSecurityEvent.objects.filter(
            user=self.user,
            event_type=AccountSecurityEvent.LOGIN_SUCCESS,
            authentication_method="password",
        ).exists())

        card_user = User.objects.create_user(username="card-audit-user", password="pass1234")
        card_profile = card_user.profile
        card_profile.position = "student"
        card_profile.branch = self.branch
        card_profile.save(update_fields=["position", "branch", "updated_at"])
        request = self._request_with_session()
        request._esfe_authentication_method = "student_card"
        login(request, card_user, backend="django.contrib.auth.backends.ModelBackend")
        self.assertTrue(AccountSecurityEvent.objects.filter(
            user=card_user,
            event_type=AccountSecurityEvent.LOGIN_SUCCESS,
            authentication_method="student_card",
        ).exists())

        public = User.objects.create_user(username="public-no-session-audit", password="pass1234")
        self.client.force_login(public)
        self.assertFalse(AccountSessionRecord.objects.filter(user=public).exists())
        self.assertFalse(AccountSecurityEvent.objects.filter(user=public, event_type=AccountSecurityEvent.LOGIN_SUCCESS).exists())

    def test_suspension_and_blocking_transitions_are_audited_with_actor(self):
        actor = User.objects.create_user(username="security-actor", password="pass1234")
        state = AccountSupportState.objects.create(user=self.user, is_blocked=True, updated_by=actor)
        state.is_suspended = True
        state.save(update_fields=["is_suspended", "updated_at"])
        self.assertTrue(AccountSecurityEvent.objects.filter(user=self.user, actor=actor, event_type=AccountSecurityEvent.ACCOUNT_BLOCKED).exists())
        self.assertTrue(AccountSecurityEvent.objects.filter(user=self.user, event_type=AccountSecurityEvent.ACCOUNT_SUSPENDED).exists())

    def test_direct_institutional_position_and_branch_change_revokes_and_audits(self):
        self.client.force_login(self.user)
        session_key = self.client.session.session_key
        institutional = self.user.institutional_profile
        other_branch = Branch.objects.create(name="Autre annexe audit", code="AUA", slug="autre-annexe-audit")
        institutional.position = "academic_supervisor"
        institutional.branch = other_branch
        institutional.save(update_fields=["position", "branch", "updated_at"])
        self.assertFalse(Session.objects.filter(session_key=session_key).exists())
        self.assertTrue(AccountSecurityEvent.objects.filter(user=self.user, event_type=AccountSecurityEvent.POSITION_CHANGED).exists())
        self.assertTrue(AccountSecurityEvent.objects.filter(user=self.user, event_type=AccountSecurityEvent.BRANCH_CHANGED).exists())

    def test_terminal_event_is_idempotent_and_metadata_secrets_are_redacted(self):
        self.client.force_login(self.user)
        identifier = self.client.session[SESSION_ID_KEY]
        close_session_record(
            user=self.user,
            identifier=identifier,
            reason=AccountSessionRecord.END_IDLE_TIMEOUT,
            event_type=AccountSecurityEvent.IDLE_TIMEOUT,
        )
        close_session_record(
            user=self.user,
            identifier=identifier,
            reason=AccountSessionRecord.END_IDLE_TIMEOUT,
            event_type=AccountSecurityEvent.IDLE_TIMEOUT,
        )
        self.assertEqual(AccountSecurityEvent.objects.filter(
            user=self.user,
            session_identifier=identifier,
            event_type=AccountSecurityEvent.IDLE_TIMEOUT,
        ).count(), 1)
        event = log_security_event(
            user=self.user,
            event_type=AccountSecurityEvent.ADMIN_REVOKED,
            metadata={"password": "secret", "nested": {"session_key": "raw-key", "safe": "ok"}},
        )
        self.assertEqual(event.metadata["password"], "[REDACTED]")
        self.assertEqual(event.metadata["nested"]["session_key"], "[REDACTED]")
        self.assertEqual(event.metadata["nested"]["safe"], "ok")


class AuthenticationSecurityTests(TestCase):
    def setUp(self):
        self.password = "A-secure-test-password-123"
        self.user = User.objects.create_user(
            username="auth-security-user",
            email="auth-security@example.com",
            password=self.password,
        )

    def test_login_accepts_a_local_next_url(self):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "username": self.user.username,
                "password": self.password,
                "next": reverse("accounts:profile"),
            },
        )

        self.assertRedirects(
            response,
            reverse("accounts:profile"),
            fetch_redirect_response=False,
        )

    def test_login_rejects_an_external_next_url(self):
        response = self.client.post(
            f'{reverse("accounts:login")}?next=https://attacker.example/phishing',
            {"username": self.user.username, "password": self.password},
        )

        self.assertRedirects(
            response,
            reverse("accounts_portal:portal_dashboard"),
            fetch_redirect_response=False,
        )

    def test_suspended_account_is_rejected_by_authentication_gate(self):
        AccountSupportState.objects.update_or_create(
            user=self.user,
            defaults={"is_suspended": True},
        )

        response = self.client.post(
            reverse("accounts:login"),
            {"username": self.user.username, "password": self.password},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertContains(response, "Ce compte est suspendu")

    def test_temporary_password_state_forces_password_change(self):
        AccountSupportState.objects.update_or_create(
            user=self.user,
            defaults={"must_change_password": True},
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("accounts:profile"))

        self.assertRedirects(
            response,
            reverse("accounts:password_change"),
            fetch_redirect_response=False,
        )

    def test_password_change_clears_requirement(self):
        state, _ = AccountSupportState.objects.update_or_create(
            user=self.user,
            defaults={"must_change_password": True},
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": self.password,
                "new_password1": "A-new-secure-password-456",
                "new_password2": "A-new-secure-password-456",
            },
        )

        self.assertRedirects(
            response,
            reverse("accounts:password_change_done"),
            fetch_redirect_response=False,
        )
        state.refresh_from_db()
        self.assertFalse(state.must_change_password)

    def test_suspension_revokes_existing_session(self):
        self.client.force_login(self.user)
        session_key = self.client.session.session_key

        AccountSupportState.objects.create(user=self.user, is_suspended=True)

        self.assertFalse(Session.objects.filter(session_key=session_key).exists())

    def test_position_change_revokes_existing_session(self):
        self.client.force_login(self.user)
        session_key = self.client.session.session_key
        profile = self.user.profile

        profile.position = "secretary"
        profile.save(update_fields=["position", "updated_at"])

        self.assertFalse(Session.objects.filter(session_key=session_key).exists())


class PortalItV2AccessTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Annexe Auth IT",
            code="AIT",
            slug="annexe-auth-it",
        )

    def _user(self, username, position):
        user = User.objects.create_user(username=username, password="pass1234")
        profile = user.profile
        profile.position = position
        profile.branch = self.branch
        profile.save(update_fields=["position", "branch", "updated_at"])
        return user

    def test_non_it_system_user_is_forbidden(self):
        self.client.force_login(self._user("teacher-it-denied", "teacher"))

        response = self.client.get(reverse("accounts_portal:portal_it_v2"))

        self.assertEqual(response.status_code, 403)

    def test_it_support_user_can_open_dashboard(self):
        self.client.force_login(self._user("it-support-allowed", "it_support"))

        response = self.client.get(reverse("accounts_portal:portal_it_v2"))

        self.assertEqual(response.status_code, 200)

    def test_legacy_staff_marker_does_not_grant_it_access(self):
        user = self._user("legacy-student-staff", "student")
        profile = user.profile
        profile.user_type = "staff"
        profile.save(update_fields=["user_type", "updated_at"])
        self.client.force_login(user)

        response = self.client.get(reverse("accounts_portal:portal_it_v2"))

        self.assertEqual(response.status_code, 403)
        self.assertNotIn(user, get_scoped_staff_queryset(branch=self.branch))


class SystemProfileEditTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Annexe Profil System",
            code="APS",
            slug="annexe-profil-system",
        )
        self.user = User.objects.create_user(
            username="system-profile-user",
            password="pass1234",
            first_name="Avant",
            last_name="Systeme",
            email="avant.systeme@example.com",
        )
        profile = self.user.profile
        profile.position = "teacher"
        profile.branch = self.branch
        profile.user_type = "staff"
        profile.bio = "Bio publique"
        profile.main_domain = "Domaine public"
        profile.save(update_fields=["position", "branch", "user_type", "bio", "main_domain", "updated_at"])

    def test_system_profile_edit_uses_portal_template_and_ignores_forged_fields(self):
        self.client.force_login(self.user)
        public_profile = self.user.public_community_profile
        public_profile.bio = "Bio communautaire verrouillee"
        public_profile.save(update_fields=["bio", "updated_at"])

        response = self.client.get(reverse("accounts_portal:system_profile_edit"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "portal/system_profile_edit.html")
        self.assertTemplateUsed(response, "portal/system_account_base.html")
        self.assertNotContains(response, "Biographie")
        self.assertNotContains(response, "Domaine d'expertise")
        self.assertContains(response, "Email de connexion")

        response = self.client.post(
            reverse("accounts_portal:system_profile_edit"),
            {
                "first_name": "Nouveau",
                "last_name": "Nom",
                "email": "nouveau.systeme@example.com",
                "phone": "+22370000000",
                "address": "Bamako",
                "position": "super_admin",
                "branch": self.branch.id,
                "groups": "super_admin",
                "bio": "Do not accept",
                "main_domain": "Do not accept",
            },
        )

        self.assertRedirects(response, get_post_login_portal_url(self.user), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Nouveau")
        self.assertEqual(self.user.last_name, "Nom")
        self.assertEqual(self.user.email, "avant.systeme@example.com")
        self.assertEqual(self.user.profile.phone, "+22370000000")
        self.assertEqual(self.user.profile.address, "Bamako")
        self.assertEqual(self.user.profile.position, "teacher")
        self.assertEqual(self.user.profile.branch, self.branch)
        self.assertEqual(list(self.user.groups.values_list("name", flat=True)), ["teacher"])
        self.user.public_community_profile.refresh_from_db()
        self.assertEqual(self.user.public_community_profile.bio, "Bio communautaire verrouillee")
        self.assertEqual(self.user.profile.bio, "Bio publique")
        self.assertEqual(self.user.profile.main_domain, "Domaine public")

    def test_system_profile_detail_redirects_to_portal_edit(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("accounts:profile"))

        self.assertRedirects(response, reverse("accounts_portal:system_profile"), fetch_redirect_response=False)

    def test_legacy_system_edit_route_redirects_to_portal(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("accounts:edit_profile"))

        self.assertRedirects(response, reverse("accounts_portal:system_profile_edit"), fetch_redirect_response=False)

    def test_public_user_cannot_open_system_workspace(self):
        public = User.objects.create_user(username="public-profile-user", password="pass1234")
        self.client.force_login(public)

        response = self.client.get(reverse("accounts_portal:system_profile_edit"))

        self.assertRedirects(response, reverse("accounts:profile"), fetch_redirect_response=False)

    def test_password_change_is_available_in_portal_and_keeps_current_session(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("accounts_portal:system_change_password"),
            {
                "old_password": "pass1234",
                "new_password1": "A-new-secure-password-456",
                "new_password2": "A-new-secure-password-456",
            },
        )

        self.assertRedirects(response, reverse("accounts_portal:system_security"), fetch_redirect_response=False)
        self.assertTrue(self.client.session.get("_auth_user_id"))

    def test_all_system_positions_use_the_same_portal_profile_workspace(self):
        positions = (
            "student", "teacher", "annex_manager", "secretary", "admissions",
            "academic_supervisor", "director_of_studies", "it_support",
            "marketing_manager", "executive_director", "deputy_executive_director",
            "super_admin",
        )
        for index, position in enumerate(positions):
            user = User.objects.create_user(username=f"system-position-{index}", password="pass1234")
            profile = user.profile
            profile.position = position
            profile.branch = self.branch
            profile.save(update_fields=["position", "branch", "updated_at"])
            public_profile = user.public_community_profile
            public_profile.bio = f"Public {position}"
            public_profile.save(update_fields=["bio", "updated_at"])

            self.client.force_login(user)
            response = self.client.post(
                reverse("accounts_portal:system_profile_edit"),
                {"first_name": "Compte", "last_name": position, "phone": "+22370000000", "address": "Bamako"},
            )
            expected = reverse("accounts:dashboard_redirect") if position == "marketing_manager" else get_post_login_portal_url(user)
            self.assertRedirects(response, expected, fetch_redirect_response=False)
            public_profile.refresh_from_db()
            self.assertEqual(public_profile.bio, f"Public {position}")

    def test_system_email_route_is_not_an_unverified_edit_endpoint(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("accounts:update_email"), {"email": "attacker@example.com"})

        self.assertRedirects(response, reverse("accounts_portal:system_security"), fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "avant.systeme@example.com")


class AccessContextV2Tests(TestCase):
    def setUp(self):
        self.branch_a = Branch.objects.create(name="Annexe A", code="AA1", slug="annexe-a1")
        self.branch_b = Branch.objects.create(name="Annexe B", code="AB1", slug="annexe-b1")

    def test_public_user_has_no_system_position_or_scope(self):
        user = User.objects.create_user(username="public-context")

        context = build_access_context(user)

        self.assertEqual(context.context_type, "PUBLIC")
        self.assertIsNone(context.position)
        self.assertIsNone(context.scope)

    def test_legacy_role_does_not_become_an_official_v2_position(self):
        user = User.objects.create_user(username="legacy-role-only")
        profile = user.profile
        profile.role = "finance"
        profile.save(update_fields=["role", "updated_at"])

        context = build_access_context(user)

        self.assertEqual(context.context_type, "PUBLIC")
        self.assertIsNone(context.position)
        self.assertTrue(hasattr(user, "public_community_profile"))
        self.assertFalse(hasattr(user, "institutional_profile"))
        divergence = compare_access_classification(user, context=context)
        self.assertIsNotNone(divergence)
        self.assertEqual(divergence["old_position"], "finance_manager")
        self.assertFalse(divergence["new_is_system"])

    def test_annex_manager_category_and_scope_are_derived(self):
        user = User.objects.create_user(username="annex-manager-context")
        profile = user.profile
        profile.position = "annex_manager"
        profile.branch = self.branch_a
        profile.save(update_fields=["position", "branch", "updated_at"])

        context = build_access_context(user)

        self.assertEqual(context.position, "annex_manager")
        self.assertEqual(context.category, "ADMIN_STAFF")
        self.assertEqual(context.scope, "BRANCH")
        self.assertTrue(context.is_valid)
        self.assertEqual(user.institutional_profile.position, "annex_manager")
        self.assertEqual(user.institutional_profile.branch, self.branch_a)
        self.assertTrue(hasattr(user, "public_community_profile"))

    def test_policy_denies_cross_branch_resource(self):
        user = User.objects.create_user(username="branch-policy-context")
        profile = user.profile
        profile.position = "annex_manager"
        profile.branch = self.branch_a
        profile.save(update_fields=["position", "branch", "updated_at"])

        decision = decide(build_access_context(user), resource_branch=self.branch_b)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "cross_branch_denied")

    def test_clearing_legacy_position_removes_institutional_assignment(self):
        user = User.objects.create_user(username="clear-system-assignment")
        profile = user.profile
        profile.position = "teacher"
        profile.branch = self.branch_a
        profile.save(update_fields=["position", "branch", "updated_at"])
        self.assertTrue(hasattr(user, "institutional_profile"))

        profile.position = ""
        profile.branch = None
        profile.save(update_fields=["position", "branch", "updated_at"])

        user.refresh_from_db()
        self.assertFalse(hasattr(user, "institutional_profile"))
        self.assertEqual(build_access_context(user).context_type, "PUBLIC")


class AuditAccessStateCommandTests(TestCase):
    def test_dry_run_reports_but_does_not_change_deterministic_alias(self):
        user = User.objects.create_user(username="legacy-branch-manager")
        profile = user.profile
        profile.position = "branch_manager"
        profile.branch = self._branch()
        profile.save(update_fields=["position", "branch", "updated_at"])
        output = StringIO()

        call_command("audit_access_state", "--dry-run", "--json", stdout=output)

        profile.refresh_from_db()
        self.assertEqual(profile.position, "branch_manager")
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["mode"], "dry-run")
        self.assertGreaterEqual(payload["summary"]["fixable"], 1)

    def test_apply_normalizes_only_deterministic_alias(self):
        user = User.objects.create_user(username="apply-branch-manager")
        profile = user.profile
        profile.position = "branch_manager"
        profile.branch = self._branch()
        profile.save(update_fields=["position", "branch", "updated_at"])

        call_command("audit_access_state", "--apply", stdout=StringIO())

        profile.refresh_from_db()
        self.assertEqual(profile.position, "annex_manager")

    @staticmethod
    def _branch():
        return Branch.objects.create(
            name="Annexe audit accès",
            code="AUD",
            slug="annexe-audit-acces",
        )


@override_settings(AUTH_PORTAL_ROUTING_V2_ENABLED=True)
class PortalRoutingV2Tests(TestCase):
    def test_public_user_is_routed_to_community(self):
        user = User.objects.create_user(username="public-routing-v2")

        self.assertEqual(
            get_post_login_portal_url(user),
            reverse("community:topic_list"),
        )

    def test_system_user_without_required_branch_is_routed_to_regularization(self):
        user = User.objects.create_user(username="invalid-system-routing-v2")
        profile = user.profile
        profile.position = "teacher"
        profile.save(update_fields=["position", "updated_at"])

        self.assertEqual(
            get_post_login_portal_url(user),
            reverse("accounts_portal:access_regularization"),
        )

    def test_legacy_manager_page_redirects_to_single_portal_dashboard(self):
        branch = Branch.objects.create(name="Annexe route", code="RTE", slug="annexe-route")
        user = User.objects.create_user(username="manager-routing-v2")
        profile = user.profile
        profile.position = "annex_manager"
        profile.branch = branch
        profile.save(update_fields=["position", "branch", "updated_at"])
        self.client.force_login(user)

        response = self.client.get(reverse("accounts:manager_dashboard"))

        self.assertRedirects(
            response,
            reverse("accounts_portal:portal_annex_manager"),
            fetch_redirect_response=False,
        )

    def test_parallel_staff_dashboards_redirect_to_portal_entries(self):
        branch = Branch.objects.create(name="Annexe staff routes", code="SRV", slug="staff-routes")
        cases = (
            ("finance_manager", "accounts:finance_dashboard", "accounts_portal:portal_finance"),
            ("admissions", "accounts:admissions_dashboard", "accounts_portal:portal_admissions"),
            ("secretary", "secretary:secretary_dashboard", "accounts_portal:portal_secretary"),
        )
        for index, (position, legacy_name, portal_name) in enumerate(cases):
            with self.subTest(position=position):
                user = User.objects.create_user(username=f"staff-route-{index}")
                profile = user.profile
                profile.position = position
                profile.branch = branch
                profile.save(update_fields=["position", "branch", "updated_at"])
                self.client.force_login(user)

                response = self.client.get(reverse(legacy_name))

                self.assertRedirects(
                    response,
                    reverse(portal_name),
                    fetch_redirect_response=False,
                )
                self.client.logout()


@override_settings(AUTH_POLICY_V2_ENABLED=True)
class ManagerPolicyV2Tests(TestCase):
    def test_group_only_manager_is_denied(self):
        user = User.objects.create_user(username="group-only-manager-v2")
        user.groups.add(Group.objects.create(name="gestionnaire"))
        self.client.force_login(user)

        response = self.client.get(reverse("accounts:manager_dashboard"))

        self.assertEqual(response.status_code, 403)

    def test_official_annex_manager_is_allowed(self):
        branch = Branch.objects.create(name="Annexe policy", code="PLC", slug="annexe-policy")
        user = User.objects.create_user(username="official-manager-v2")
        profile = user.profile
        profile.position = "annex_manager"
        profile.branch = branch
        profile.save(update_fields=["position", "branch", "updated_at"])
        self.client.force_login(user)

        response = self.client.get(reverse("accounts:manager_dashboard"))

        self.assertEqual(response.status_code, 200)


@override_settings(AUTH_POLICY_V2_ENABLED=True)
class CentralAccessPolicyV2Tests(TestCase):
    def test_is_staff_alone_grants_no_portal(self):
        user = User.objects.create_user(username="is-staff-only-v2", is_staff=True)

        self.assertIsNone(get_user_position(user))
        self.assertFalse(can_access(user, "view_portal", "staff"))


class PositionRegistryTests(TestCase):
    @override_settings(ROOT_URLCONF="config.urls")
    def test_every_position_has_one_resolvable_primary_dashboard(self):
        for code, definition in POSITION_REGISTRY.items():
            with self.subTest(position=code):
                self.assertTrue(definition.dashboard_url_name)
                self.assertTrue(reverse(definition.dashboard_url_name))

    def test_categories_and_scopes_are_registry_derived(self):
        for code, definition in POSITION_REGISTRY.items():
            with self.subTest(position=code):
                self.assertIn(definition.category, {"STUDENT", "TEACHING_STAFF", "ADMIN_STAFF"})
                self.assertIn(definition.scope, {"BRANCH", "GLOBAL"})
                self.assertEqual(definition.branch_required, definition.scope == "BRANCH")


@override_settings(AUTH_POLICY_V2_ENABLED=True)
class SuperAdminBusinessPositionTests(TestCase):
    def test_business_super_admin_does_not_require_django_superuser(self):
        from superadmin.views import superuser_required

        user = User.objects.create_user(username="business-super-admin")
        profile = user.profile
        profile.position = "super_admin"
        profile.save(update_fields=["position", "updated_at"])

        self.assertFalse(user.is_superuser)
        self.assertTrue(superuser_required(user))

    def test_technical_superuser_does_not_imply_business_super_admin(self):
        from superadmin.views import superuser_required

        user = User.objects.create_superuser(
            username="technical-only-super-admin",
            email="technical-only@example.com",
            password="pass1234",
        )

        self.assertFalse(superuser_required(user))


@override_settings(AUTH_POLICY_V2_ENABLED=True)
class MarketingPositionPolicyTests(TestCase):
    def test_marketing_group_without_official_position_is_denied(self):
        from marketing.permissions import user_can_access_marketing

        user = User.objects.create_user(username="marketing-group-only")
        user.groups.add(Group.objects.create(name="marketing"))

        self.assertFalse(user_can_access_marketing(user))

    def test_official_marketing_manager_is_allowed_without_group(self):
        from marketing.permissions import user_can_access_marketing

        user = User.objects.create_user(username="official-marketing-manager")
        profile = user.profile
        profile.position = "marketing_manager"
        profile.save(update_fields=["position", "updated_at"])

        self.assertTrue(user_can_access_marketing(user))



@override_settings(AUTH_POLICY_V2_ENABLED=True)
class CentralAccessPolicyV2AdditionalTests(TestCase):
    def test_teacher_group_without_position_is_denied(self):
        user = User.objects.create_user(username="teacher-group-only-v2")
        teacher_group, _created = Group.objects.get_or_create(name="teacher")
        user.groups.add(teacher_group)

        self.assertFalse(can_access(user, "view_portal", "teacher"))

    def test_official_teacher_position_is_allowed(self):
        branch = Branch.objects.create(name="Annexe teacher policy", code="TPV", slug="teacher-policy-v2")
        user = User.objects.create_user(username="official-teacher-v2")
        profile = user.profile
        profile.position = "teacher"
        profile.branch = branch
        profile.save(update_fields=["position", "branch", "updated_at"])

        self.assertEqual(get_user_position(user), "teacher")
        self.assertTrue(can_access(user, "view_portal", "teacher"))

    def test_technical_superuser_without_business_position_gets_no_system_portal(self):
        user = User.objects.create_superuser(
            username="technical-superuser-v2",
            email="technical@example.com",
            password="pass1234",
        )

        self.assertIsNone(get_user_position(user))
        self.assertFalse(can_access(user, "view_portal", "staff"))
