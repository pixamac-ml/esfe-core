from urllib.parse import urljoin
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.utils import timezone

from core.models import Institution


logger = logging.getLogger(__name__)


def get_formatted_from_email():
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@esfe-mali.org")
    from_name = getattr(settings, "EMAIL_FROM_NAME", "").strip()
    if from_name:
        return f"{from_name} <{from_email}>"
    return from_email


def get_email_branding_context():
    """Construit un contexte d'identite ecole pour tous les emails."""
    institution = Institution.objects.first()
    base_url = getattr(settings, "BASE_URL", "https://www.esfe-mali.org").rstrip("/")
    logo_path = getattr(settings, "EMAIL_LOGO_PATH", "static/images/logo-esfe.png").lstrip("/")

    if institution:
        institution_name = institution.name
        institution_short_name = institution.short_name or institution.name
        institution_email = institution.email or getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@esfe-mali.org")
        institution_phone = institution.phone or ""
        institution_address = ", ".join(filter(None, [institution.address, institution.city, institution.country]))
    else:
        institution_name = "ESFE - Ecole Privee de Sante Felix Houphouet-Boigny"
        institution_short_name = "ESFE"
        institution_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@esfe-mali.org")
        institution_phone = ""
        institution_address = "Bamako, Mali"

    return {
        "institution": institution,
        "institution_name": institution_name,
        "institution_short_name": institution_short_name,
        "institution_email": institution_email,
        "institution_phone": institution_phone,
        "institution_address": institution_address,
        "institution_website": base_url,
        "logo_url": urljoin(base_url + "/", logo_path),
        "year": timezone.now().year,
    }


def send_templated_email(
    *,
    subject,
    recipient,
    text_template=None,
    html_template=None,
    context=None,
    attachments=None,
    fallback_text="",
    fail_silently=False,
):
    """Envoi standardise texte + HTML avec contexte institutionnel."""
    if not recipient:
        return False

    merged_context = {}
    merged_context.update(get_email_branding_context())
    if context:
        merged_context.update(context)

    text_body = ""
    html_body = ""

    if text_template:
        try:
            text_body = render_to_string(text_template, merged_context)
        except TemplateDoesNotExist:
            logger.warning("Template texte introuvable: %s", text_template)
        except Exception:
            logger.exception("Echec rendu template texte: %s", text_template)
    if html_template:
        try:
            html_body = render_to_string(html_template, merged_context)
        except TemplateDoesNotExist:
            logger.warning("Template HTML introuvable: %s", html_template)
        except Exception:
            logger.exception("Echec rendu template HTML: %s", html_template)

    if not text_body and html_body:
        text_body = fallback_text or "Veuillez consulter la version HTML de cet email."
    elif not text_body:
        text_body = fallback_text or ""

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=get_formatted_from_email(),
        to=[recipient],
    )

    if html_body:
        message.attach_alternative(html_body, "text/html")

    for attachment in attachments or []:
        path = attachment.get("path")
        if not path:
            continue
        try:
            with open(path, "rb") as file_obj:
                message.attach(
                    attachment.get("name") or path.split("/")[-1].split("\\")[-1],
                    file_obj.read(),
                    attachment.get("mimetype") or "application/octet-stream",
                )
        except FileNotFoundError:
            logger.warning("Piece jointe email introuvable: %s", path)
        except Exception:
            logger.exception("Echec attachement email: %s", path)

    message.send(fail_silently=fail_silently)
    return True

