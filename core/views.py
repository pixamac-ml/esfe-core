# core/views.py

import logging

from django.shortcuts import render, get_object_or_404
from django.http import Http404, HttpResponse
from django.utils.html import strip_tags
from django.utils import timezone
from django.db.models import Sum, Count, F, Avg, ExpressionWrapper, DurationField
from django.db.models.functions import Extract
from django.views.decorators.http import require_http_methods
from django.contrib.admin.views.decorators import staff_member_required
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.db.models import Prefetch

# PDF
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4

# Apps
from formations.models import Programme
from news.models import News
from blog.models import Article
from admissions.models import Candidature
from inscriptions.models import Inscription
from payments.models import Payment

# core/views.py

import logging

from django.shortcuts import render, get_object_or_404
from django.http import Http404, HttpResponse
from django.utils.html import strip_tags
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import (
    Sum, Count, F, Avg,
    ExpressionWrapper, DurationField, Prefetch
)
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

# PDF
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4

# Apps
from formations.models import Programme
from news.models import News
from blog.models import Article
from admissions.models import Candidature
from inscriptions.models import Inscription
from payments.models import Payment

from .models import (
    Institution,
    InstitutionStat,
    LegalPage,
    AboutSection,
    ContactMessage,
)

from .forms import ContactForm

logger = logging.getLogger(__name__)


# ==========================================================
# CONTEXTE GLOBAL INSTITUTIONNEL
# ==========================================================

def get_institution_context():
    institution = Institution.objects.filter(is_active=True).first()

    if not institution:
        return {
            "institution": None,
            "institution_name": "Institution non configurée",
            "contact": {},
            "navigation": [],
            "legal_links": [],
        }

    return {
        "institution": institution,
        "institution_name": institution.name,
        "contact": {
            "address": f"{institution.address}, {institution.city}, {institution.country}",
            "phone": institution.phone,
            "email": institution.email,
        },
        "navigation": [
            {"label": "Accueil", "url": "/"},
            {"label": "Formations", "url": "/formations/"},
            {"label": "Candidatures", "url": "/candidature/"},
            {"label": "Contact", "url": "/contact/"},
        ],
        "legal_links": [
            {"label": "Mentions légales", "url": "/mentions-legales/"},
            {"label": "Politique de confidentialité", "url": "/confidentialite/"},
            {"label": "Conditions d’utilisation", "url": "/conditions-utilisation/"},
            {"label": "Plan du site", "url": "/plan-du-site/"},
        ],
    }


# ==========================================================
# PLAN DU SITE (RESTÉ INTACT)
# ==========================================================

def sitemap(request):
    context = {
        "page_title": "Plan du site",
        **get_institution_context(),
    }
    return render(request, "sitemap.html", context)


# ==========================================================
# ABOUT
# ==========================================================

def about(request):

    institution = Institution.objects.filter(is_active=True).first()

    stats = InstitutionStat.objects.filter(
        is_active=True
    ).order_by("order")

    sections = (
        AboutSection.objects
        .filter(is_active=True)
        .order_by("order")
    )

    # Hero data - on peut le rendre dynamique via l'admin plus tard
    hero_title = institution.name if institution else "Notre Institution"
    hero_subtitle = "Excellence académique et formation professionnelle de qualité"

    context = {
        "institution": institution,
        "stats": stats,
        "sections": sections,  # Renommé pour correspondre au template
        "hero_title": hero_title,
        "hero_subtitle": hero_subtitle,
        **get_institution_context(),
    }

    return render(request, "core/about.html", context)


# ==========================================================
# HOME
# ==========================================================

def home(request):

    pillars = [
        {"title": "Sciences de la santé", "description": "Formations spécialisées adaptées aux exigences professionnelles."},
        {"title": "Encadrement académique", "description": "Corps enseignant qualifié et expérimenté."},
        {"title": "Exigence académique", "description": "Rigueur pédagogique et suivi personnalisé."},
        {"title": "Ouverture", "description": "Étudiants nationaux et internationaux."},
    ]

    formations_home = (
        Programme.objects
        .filter(is_active=True)
        .select_related("cycle", "diploma_awarded")
        .order_by("cycle__min_duration_years")[:3]
    )

    stats = InstitutionStat.objects.filter(is_active=True).order_by("order")

    latest_news = (
        News.objects
        .filter(status="published")
        .order_by("-published_at")[:3]
    )

    latest_articles = (
        Article.objects
        .filter(status="published")
        .order_by("-published_at")[:3]
    )

    context = {
        "pillars": pillars,
        "formations_home": formations_home,
        "stats": stats,
        "latest_news": latest_news,
        "latest_articles": latest_articles,
        **get_institution_context(),
    }

    return render(request, "home.html", context)


# ==========================================================
# LEGAL PAGES
# ==========================================================

def render_legal_page(request, page_type):

    page = get_object_or_404(
        LegalPage,
        page_type=page_type,
        status="published"
    )

    context = {
        "page": page,
        "sections": page.sections.filter(is_active=True),
        "sidebar_blocks": page.sidebar_blocks.filter(is_active=True),
        **get_institution_context(),
    }

    template_map = {
        "legal": "legal_notice.html",
        "privacy": "privacy_policy.html",
        "terms": "terms_of_service.html",
    }

    template_name = template_map.get(page_type)
    if not template_name:
        raise Http404("Page non trouvée")

    return render(request, template_name, context)


def legal_notice(request):
    return render_legal_page(request, "legal")


def privacy_policy(request):
    return render_legal_page(request, "privacy")


def terms_of_service(request):
    return render_legal_page(request, "terms")


# ==========================================================
# PDF EXPORT
# ==========================================================

def legal_page_pdf(request, page_type):

    page = get_object_or_404(
        LegalPage,
        page_type=page_type,
        status="published"
    )

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{page.page_type}.pdf"'

    doc = SimpleDocTemplate(response, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(page.title, styles["Heading1"]))
    elements.append(Spacer(1, 12))

    for section in page.sections.filter(is_active=True):
        elements.append(Paragraph(section.title, styles["Heading2"]))
        elements.append(Spacer(1, 6))
        elements.append(
            Paragraph(strip_tags(section.content), styles["Normal"])
        )
        elements.append(Spacer(1, 12))

    doc.build(elements)
    return response



# ==========================================================
# CONTACT
# ==========================================================

@require_http_methods(["GET", "POST"])
def contact_view(request):

    if request.method == "POST":
        form = ContactForm(request.POST)

        if form.is_valid():
            contact_message = form.save(commit=False)
            contact_message.ip_address = request.META.get("REMOTE_ADDR")
            contact_message.user_agent = request.META.get("HTTP_USER_AGENT", "")
            contact_message.save()

            # Email interne
            internal_html = render_to_string(
                "emails/contact_internal.html",
                {"message_obj": contact_message}
            )
            internal_email = EmailMultiAlternatives(
                subject=f"[CONTACT] {contact_message.get_subject_display()}",
                body=strip_tags(internal_html),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[settings.DEFAULT_FROM_EMAIL],
            )
            internal_email.attach_alternative(internal_html, "text/html")
            internal_email.send()

            # Email utilisateur
            user_html = render_to_string(
                "emails/contact_received.html",
                {"message_obj": contact_message}
            )
            user_email = EmailMultiAlternatives(
                subject="Votre demande a bien été reçue",
                body=strip_tags(user_html),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[contact_message.email],
            )
            user_email.attach_alternative(user_html, "text/html")
            user_email.send()

            return render(
                request,
                "core/contact_success.html",
                {
                    "reference": contact_message.reference,
                    **get_institution_context(),
                }
            )

    else:
        form = ContactForm()

    return render(
        request,
        "core/contact.html",
        {
            "form": form,
            **get_institution_context(),
        }
    )


# ==========================================================
# CUSTOM ERROR HANDLERS
# ==========================================================

def custom_404(request, exception):
    formations_home = (
        Programme.objects
        .filter(is_active=True)
        .select_related("cycle")
        .order_by("cycle__min_duration_years")[:3]
    )

    context = {
        "error_code": 404,
        "error_title": "Page introuvable",
        "error_message": "La page demandée n'existe pas ou a été déplacée.",
        "formations_home": formations_home,
        **get_institution_context(),
    }

    return render(request, "core/errors/404.html", context, status=404)


def custom_403(request, exception):
    logger.warning(f"403 | User={request.user} | Path={request.path}")

    context = {
        "error_code": 403,
        "error_title": "Accès restreint",
        "error_message": "Vous n'êtes pas autorisé à accéder à cette ressource.",
        **get_institution_context(),
    }

    return render(request, "core/errors/403.html", context, status=403)


def custom_500(request):
    logger.error("500 | Internal server error")

    context = {
        "error_code": 500,
        "error_title": "Erreur interne",
        "error_message": "Une erreur inattendue s'est produite. Notre équipe technique a été informée.",
        **get_institution_context(),
    }

    return render(request, "core/errors/500.html", context, status=500)


def custom_400(request, exception):
    logger.warning(f"400 | Bad request | Path={request.path}")

    context = {
        "error_code": 400,
        "error_title": "Requête invalide",
        "error_message": "La requête envoyée est invalide ou mal formée.",
        **get_institution_context(),
    }

    return render(request, "core/errors/400.html", context, status=400)