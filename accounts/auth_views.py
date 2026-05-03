from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError

from portal.permissions import get_post_login_portal_url
from portal.services.it_support_service import get_account_support_state


class PortalAuthenticationForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        state = get_account_support_state(user)
        if state.is_suspended:
            raise ValidationError(
                "Ce compte est suspendu. Contactez l'informaticien de votre annexe.",
                code="account_suspended",
            )
        if state.is_blocked:
            raise ValidationError(
                "Ce compte est bloque. Contactez l'informaticien de votre annexe.",
                code="account_blocked",
            )


class PortalLoginView(auth_views.LoginView):
    """Login view conservant next, puis redirection portail par rôle."""

    template_name = "registration/login.html"
    authentication_form = PortalAuthenticationForm

    def get_success_url(self):
        return get_post_login_portal_url(self.request.user)

