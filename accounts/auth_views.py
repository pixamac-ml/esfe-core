from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import AuthenticationForm
from django.urls import reverse_lazy
from portal.permissions import get_post_login_portal_url
from accounts.access import get_user_position
from .authentication import AuthenticationGate, safe_local_redirect_url


class PortalAuthenticationForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        AuthenticationGate.enforce(user)


class PortalLoginView(auth_views.LoginView):
    """Login view conservant next, puis redirection portail par rôle."""

    template_name = "registration/login.html"
    authentication_form = PortalAuthenticationForm
    session_expiry_messages = {
        "idle_timeout": "Votre session a expiré après une période d'inactivité. Reconnectez-vous pour continuer.",
        "absolute_timeout": "La durée maximale de votre session est atteinte. Reconnectez-vous pour continuer.",
        "session_required": "Votre session n'est plus active. Reconnectez-vous pour continuer.",
        "admin_revoked": "Votre session a été fermée par l'administration. Reconnectez-vous si nécessaire.",
        "password_changed": "Votre session a été fermée après un changement de mot de passe. Reconnectez-vous.",
        "account_restricted": "Votre session a été fermée car l'accès au compte a changé.",
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        reason = (self.request.GET.get("session_expired") or "").strip().lower()
        context["session_expired_message"] = self.session_expiry_messages.get(reason, "")
        return context

    def get_success_url(self):
        next_url = safe_local_redirect_url(
            self.request,
            self.get_redirect_url(),
        )
        if next_url:
            return next_url
        return get_post_login_portal_url(self.request.user)


class PortalPasswordChangeView(auth_views.PasswordChangeView):
    template_name = "registration/password_change_form.html"
    success_url = reverse_lazy("accounts:password_change_done")

    def get_template_names(self):
        if get_user_position(self.request.user):
            return ["portal/system_password_change.html"]
        return [self.template_name]

    def get_success_url(self):
        if get_user_position(self.request.user):
            return reverse_lazy("accounts_portal:system_security")
        return super().get_success_url()

    def form_valid(self, form):
        response = super().form_valid(form)
        state = getattr(self.request.user, "support_state", None)
        if state and state.must_change_password:
            state.must_change_password = False
            state.save(update_fields=["must_change_password", "updated_at"])

        from .models import AccountSecurityEvent, AccountSessionRecord
        from .session_policy import SESSION_ID_KEY, log_security_event
        from .session_security import revoke_user_sessions
        log_security_event(
            user=self.request.user,
            event_type=AccountSecurityEvent.PASSWORD_CHANGED,
            request=self.request,
            identifier=self.request.session.get(SESSION_ID_KEY),
            reason=AccountSessionRecord.END_PASSWORD_CHANGED,
        )
        revoke_user_sessions(
            self.request.user,
            exclude_session_key=self.request.session.session_key,
            reason=AccountSessionRecord.END_PASSWORD_CHANGED,
        )
        return response

