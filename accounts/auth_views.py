from django.contrib.auth import views as auth_views

from portal.permissions import get_post_login_portal_url


class PortalLoginView(auth_views.LoginView):
    """Login view conservant next, puis redirection portail par rôle."""

    template_name = "registration/login.html"

    def get_success_url(self):
        return get_post_login_portal_url(self.request.user)

