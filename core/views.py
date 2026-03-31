# core/views.py

import logging
from datetime import timedelta

from django.shortcuts import render, get_object_or_404
from django.http import Http404, HttpResponse
from django.utils.html import strip_tags
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.db.models import Q
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.utils import OperationalError, ProgrammingError
from django.urls import NoReverseMatch, reverse

# PDF
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4

# Apps
from formations.models import Programme
from news.models import News, ResultSession
from blog.models import Article
from branches.models import Branch

from .models import (
    Institution,
    InstitutionPresentation,
    SiteConfiguration,
    InstitutionStat,
    Value,
    Infrastructure,
    Staff,
    Partner,
    Testimonial,
    LegalPage,
)

from .forms import ContactForm

logger = logging.getLogger(__name__)
User = get_user_model()


def get_site_configuration_safe():
    """Retourne la configuration site ou None si la migration n'est pas encore appliquee."""
    try:
        return SiteConfiguration.objects.first()
    except (ProgrammingError, OperationalError):
        return None


# ==========================================================
# CONTEXTE GLOBAL INSTITUTIONNEL
# ==========================================================

def get_institution_context():
    institution = Institution.objects.filter(is_active=True).first()
    site_configuration = get_site_configuration_safe()
    site_logo_url = site_configuration.site_logo.url if site_configuration and site_configuration.site_logo else ""

    if not institution:
        return {
            "institution": None,
            "site_configuration": site_configuration,
            "site_logo_url": site_logo_url,
            "institution_name": "Institution non configurée",
            "contact": {},
            "navigation": [],
            "legal_links": [],
        }

    return {
        "institution": institution,
        "site_configuration": site_configuration,
        "site_logo_url": site_logo_url,
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
            {"label": "Conditions d'utilisation", "url": "/conditions-utilisation/"},
            {"label": "Plan du site", "url": "/plan-du-site/"},
        ],
    }


# ==========================================================
# PLAN DU SITE
# ==========================================================

def _safe_reverse(url_name):
    try:
        return reverse(url_name)
    except NoReverseMatch:
        return None


def _sitemap_link(label, url_name, description=""):
    url = _safe_reverse(url_name)
    if not url:
        return None
    return {
        "label": label,
        "url": url,
        "description": description,
    }


def _clean_links(raw_links):
    return [item for item in raw_links if item]


def sitemap(request):
    sitemap_sections = [
        {
            "title": "Decouvrir ESFE",
            "icon": "fa-solid fa-compass",
            "links": _clean_links([
                _sitemap_link("Accueil", "core:home", "Vue d'ensemble et actualites principales."),
                _sitemap_link("A propos", "core:about", "Presentation de l'institution et des valeurs."),
                _sitemap_link("Contact", "core:contact", "Coordonnees et formulaire de contact."),
                _sitemap_link("Plan du site", "core:sitemap", "Structure complete des pages publiques."),
            ]),
        },
        {
            "title": "Admissions et formations",
            "icon": "fa-solid fa-graduation-cap",
            "links": _clean_links([
                _sitemap_link("Catalogue des formations", "formations:list", "Programmes disponibles par cycle."),
                _sitemap_link("Actualites", "news:list", "Informations officielles et annonces."),
                _sitemap_link("Galeries evenements", "news:event_list", "Evenements et vie de campus."),
                _sitemap_link("Portail resultats", "news:result_list", "Publication des resultats academiques."),
            ]),
        },
        {
            "title": "Vie academique",
            "icon": "fa-solid fa-users",
            "links": _clean_links([
                _sitemap_link("Blog", "blog:article_list", "Articles, conseils et contenus pedagogiques."),
                _sitemap_link("Communaute", "community:topic_list", "Questions, echanges et entraide."),
            ]),
        },
        {
            "title": "Informations legales",
            "icon": "fa-solid fa-scale-balanced",
            "links": _clean_links([
                _sitemap_link("Mentions legales", "core:legal_notice", "Cadre juridique du site."),
                _sitemap_link("Politique de confidentialite", "core:privacy_policy", "Protection des donnees personnelles."),
                _sitemap_link("Conditions d'utilisation", "core:terms_of_service", "Regles d'utilisation de la plateforme."),
            ]),
        },
    ]

    sitemap_stats = [
        {"label": "Formations actives", "value": Programme.objects.filter(is_active=True).count()},
        {"label": "Annexes actives", "value": Branch.objects.filter(is_active=True).count()},
        {"label": "Actualites publiees", "value": News.objects.filter(status="published").count()},
        {"label": "Sessions de resultats", "value": ResultSession.objects.filter(is_published=True).count()},
    ]

    context = {
        "page_title": "Plan du site",
        "meta_description": "Plan du site ESFE: accedez rapidement aux formations, actualites, blog, pages legales et contacts.",
        "og_type": "website",
        "hero_title": "Plan du site ESFE",
        "hero_subtitle": "Retrouvez rapidement toutes les pages essentielles de la plateforme ESFE.",
        "sitemap_sections": [section for section in sitemap_sections if section["links"]],
        "sitemap_stats": sitemap_stats,
        "updated_on": timezone.localdate(),
        **get_institution_context(),
    }
    return render(request, "sitemap.html", context)


def robots_txt(request):
    lines = ["User-agent: *"]
    if settings.DEBUG:
        lines.append("Disallow: /")
    else:
        lines.extend([
            "Disallow: /admin/",
            "Disallow: /superadmin/",
            "Disallow: /accounts/",
            "Disallow: /__reload__/",
            "Allow: /",
        ])

    lines.append(f"Sitemap: {settings.BASE_URL}/sitemap.xml")
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


# ==========================================================
# ABOUT
# ==========================================================

def about(request):
    institution = Institution.objects.filter(is_active=True).first()
    presentation = InstitutionPresentation.objects.first()
    site_configuration = get_site_configuration_safe()

    stats = InstitutionStat.objects.filter(
        is_active=True
    ).order_by("order")

    values = Value.objects.filter(
        is_active=True
    ).order_by("order")

    infrastructures = Infrastructure.objects.filter(
        is_active=True
    ).order_by("order")

    staff_direction = Staff.objects.filter(
        is_active=True,
        category="direction"
    ).order_by("order")

    staff_teachers = Staff.objects.filter(
        is_active=True,
        category="teacher"
    ).order_by("order")

    partners = Partner.objects.filter(
        is_active=True
    ).order_by("order")

    testimonials = Testimonial.objects.filter(
        is_active=True
    ).order_by("-is_featured", "order")

    formations = Programme.objects.filter(
        is_active=True
    ).select_related('cycle').order_by('-is_featured', 'title')[:6]

    branches = Branch.objects.filter(is_active=True).order_by("name")

    # Hero data
    hero_title = presentation.hero_title if presentation else (institution.name if institution else "Notre Institution")
    hero_subtitle = presentation.hero_subtitle if presentation else "Excellence académique et formation professionnelle de qualité"

    context = {
        "institution": institution,
        "site_configuration": site_configuration,
        "presentation": presentation,
        "stats": stats,
        "values": values,
        "infrastructures": infrastructures,
        "staff_direction": staff_direction,
        "staff_teachers": staff_teachers,
        "partners": partners,
        "testimonials": testimonials,
        "formations": formations,
        "branches": branches,
        "hero_title": hero_title,
        "hero_subtitle": hero_subtitle,
        **get_institution_context(),
    }

    return render(request, "core/about.html", context)


# ==========================================================
# HOME
# ==========================================================

def home(request):
    institution = Institution.objects.filter(is_active=True).first()
    presentation = InstitutionPresentation.objects.first()
    site_configuration = get_site_configuration_safe()
    home_hero_image_url = site_configuration.home_hero_image.url if site_configuration and site_configuration.home_hero_image else ""
    site_logo_url = site_configuration.site_logo.url if site_configuration and site_configuration.site_logo else ""

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

    values = Value.objects.filter(is_active=True).order_by("order")[:4]

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

    partners = Partner.objects.filter(is_active=True).order_by("order")

    testimonials = Testimonial.objects.filter(
        is_active=True,
        is_featured=True
    ).order_by("order")[:3]

    branches = Branch.objects.filter(is_active=True).select_related("manager").order_by("name")[:8]

    why_blocks = [
        {
            "title": "Formation professionnalisante",
            "desc": "Programmes alignes sur les besoins du terrain.",
            "image_url": site_configuration.home_why_image_1.url if site_configuration and site_configuration.home_why_image_1 else "",
        },
        {
            "title": "Encadrement de proximite",
            "desc": "Accompagnement pedagogique et suivi individualise.",
            "image_url": site_configuration.home_why_image_2.url if site_configuration and site_configuration.home_why_image_2 else "",
        },
        {
            "title": "Equipements modernes",
            "desc": "Plateaux techniques adaptes aux pratiques de sante.",
            "image_url": site_configuration.home_why_image_3.url if site_configuration and site_configuration.home_why_image_3 else "",
        },
        {
            "title": "Insertion rapide",
            "desc": "Competences operationnelles et employabilite renforcee.",
            "image_url": site_configuration.home_why_image_4.url if site_configuration and site_configuration.home_why_image_4 else "",
        },
    ]

    latest_results = ResultSession.objects.filter(is_published=True).order_by("-annee_academique", "-created_at")[:3]

    active_members_30d = User.objects.filter(
        Q(community_topics__created_at__gte=timezone.now() - timedelta(days=30))
        | Q(community_answers__created_at__gte=timezone.now() - timedelta(days=30))
    ).distinct().count()

    context = {
        "institution": institution,
        "presentation": presentation,
        "site_configuration": site_configuration,
        "home_hero_image_url": home_hero_image_url,
        "site_logo_url": site_logo_url,
        "pillars": pillars,
        "formations_home": formations_home,
        "stats": stats,
        "values": values,
        "latest_news": latest_news,
        "latest_articles": latest_articles,
        "latest_results": latest_results,
        "active_members_30d": active_members_30d,
        "partners": partners,
        "testimonials": testimonials,
        "why_blocks": why_blocks,
        "annexes": branches,
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


def fallback_404(request, unmatched_path=""):
    """Fallback explicite pour les URLs non resolues (utile aussi en mode debug)."""
    logger.warning(f"404 fallback | Path=/{unmatched_path}")
    return custom_404(request, exception=None)


def preview_error_page(request, error_code):
    """Apercu rapide des pages d'erreur pour validation visuelle."""
    if error_code == 400:
        return custom_400(request, exception=None)
    if error_code == 403:
        return custom_403(request, exception=None)
    if error_code == 404:
        return custom_404(request, exception=None)
    if error_code == 500:
        return custom_500(request)
    raise Http404("Code d'erreur non supporte")

