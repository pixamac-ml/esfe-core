from django.http import Http404
import logging

logger = logging.getLogger(__name__)


class SecurityShieldMiddleware:

    BLOCKED_KEYWORDS = [
        "wp-admin",
        "wp-login",
        "phpmyadmin",
        ".env",
        ".git",
        "config.php",
        "composer.json",
    ]

    SENSITIVE_PREFIXES = [
        "/dashboard/",
        "/admin/",
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        path = request.path.lower()

        for keyword in self.BLOCKED_KEYWORDS:
            if keyword in path:
                logger.warning(f"Blocked suspicious path: {path}")
                raise Http404()

        for prefix in self.SENSITIVE_PREFIXES:
            if path.startswith(prefix):
                if not request.user.is_authenticated:
                    raise Http404()
                if not request.user.is_staff:
                    raise Http404()

        response = self.get_response(request)
        return response