from django.conf import settings

from .brevo import BrevoEmailProvider


def get_email_provider():
    provider_name = getattr(settings, "COMMUNICATION_EMAIL_PROVIDER", "brevo")
    if provider_name == "brevo":
        return BrevoEmailProvider()
    return BrevoEmailProvider()
