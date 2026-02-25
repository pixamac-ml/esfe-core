# core/views.py

from django.shortcuts import render, get_object_or_404
from django.http import Http404, HttpResponse
from django.utils.html import strip_tags
from news.models import News
from blog.models import Article

from .models import Institution, LegalPage

# PDF
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4


# ==========================================================
# CONTEXTE GLOBAL INSTITUTIONNEL
# ==========================================================

def get_institution_context():
    """
    Récupère l'unique instance Institution.
    Fournit un fallback sécurisé si non configurée.
    """

    institution = Institution.objects.first()

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

from formations.models import Programme
from news.models import News
from blog.models import Article
from .models import InstitutionStat


def home(request):

    pillars = [
        {
            "title": "Sciences de la santé",
            "description": "Formations spécialisées adaptées aux exigences professionnelles.",
        },
        {
            "title": "Encadrement académique",
            "description": "Corps enseignant qualifié et expérimenté.",
        },
        {
            "title": "Exigence académique",
            "description": "Rigueur pédagogique et suivi personnalisé.",
        },
        {
            "title": "Ouverture",
            "description": "Étudiants nationaux et internationaux.",
        },
    ]

    formations_home = (
        Programme.objects
        .filter(is_active=True)
        .select_related("cycle", "diploma_awarded")
        .order_by("cycle__min_duration_years")[:3]
    )

    why_blocks = [
        {
            "img": "labo.png",
            "title": "Laboratoires modernes",
            "desc": "Équipements professionnels dernière génération.",
        },
        {
            "img": "enseignant.png",
            "title": "Encadrement expert",
            "desc": "Professionnels de santé et pédagogues qualifiés.",
        },
        {
            "img": "uniforme.png",
            "title": "Formation immersive",
            "desc": "Immersion progressive en milieu réel.",
        },
        {
            "img": "social.png",
            "title": "Impact social",
            "desc": "Professionnels engagés au service des communautés.",
        },
    ]

    stats = InstitutionStat.objects.all()

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
        "why_blocks": why_blocks,
        "stats": stats,
        "latest_news": latest_news,
        "latest_articles": latest_articles,
        **get_institution_context(),
    }

    return render(request, "home.html", context)

# ==========================================================
# MÉTHODE GÉNÉRIQUE POUR PAGES LÉGALES
# ==========================================================

def render_legal_page(request, page_type):

    page = get_object_or_404(
        LegalPage,
        page_type=page_type,
        status="published"
    )

    context = {
        "page": page,
        "sections": page.sections.all(),
        "sidebar_blocks": page.sidebar_blocks.all(),
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


# ==========================================================
# VUES SPÉCIFIQUES
# ==========================================================

def legal_notice(request):
    return render_legal_page(request, "legal")


def privacy_policy(request):
    return render_legal_page(request, "privacy")


def terms_of_service(request):
    return render_legal_page(request, "terms")


# ==========================================================
# EXPORT PDF OFFICIEL
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

    for section in page.sections.all():
        elements.append(Paragraph(section.title, styles["Heading2"]))
        elements.append(Spacer(1, 6))
        elements.append(
            Paragraph(strip_tags(section.content), styles["Normal"])
        )
        elements.append(Spacer(1, 12))

    doc.build(elements)

    return response


# ==========================================================
# PLAN DU SITE
# ==========================================================

def sitemap(request):

    context = {
        "page_title": "Plan du site",
        **get_institution_context(),
    }

    return render(request, "sitemap.html", context)



from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.utils import timezone
from django.db.models import Sum, Count, F
from admissions.models import Candidature
from inscriptions.models import Inscription
from payments.models import Payment


@staff_member_required
def superadmin_dashboard(request):

    now = timezone.now()
    current_month = now.month
    current_year = now.year

    # ======================================================
    # CANDIDATURES
    # ======================================================
    total_candidatures = Candidature.objects.count()
    under_review = Candidature.objects.filter(status="under_review").count()
    accepted = Candidature.objects.filter(
        status__in=["accepted", "accepted_with_reserve"]
    ).count()
    rejected = Candidature.objects.filter(status="rejected").count()
    to_complete = Candidature.objects.filter(status="to_complete").count()

    acceptance_rate = 0
    if total_candidatures > 0:
        acceptance_rate = round((accepted / total_candidatures) * 100, 2)

    # ======================================================
    # INSCRIPTIONS
    # ======================================================
    total_inscriptions = Inscription.objects.count()
    active_inscriptions = Inscription.objects.filter(status="active").count()
    suspended_inscriptions = Inscription.objects.filter(status="suspended").count()

    unpaid_inscriptions = Inscription.objects.filter(
        amount_paid__lt=F("amount_due")
    ).count()

    # ======================================================
    # PAYMENTS
    # ======================================================
    validated_payments = Payment.objects.filter(status="validated")

    total_payments = validated_payments.count()

    total_revenue = (
        validated_payments.aggregate(total=Sum("amount"))["total"] or 0
    )

    monthly_revenue = (
        validated_payments.filter(
            paid_at__month=current_month,
            paid_at__year=current_year
        ).aggregate(total=Sum("amount"))["total"] or 0
    )

    # ======================================================
    # FINANCES GLOBALES
    # ======================================================
    total_due = (
        Inscription.objects.aggregate(total=Sum("amount_due"))["total"] or 0
    )

    total_paid = (
        Inscription.objects.aggregate(total=Sum("amount_paid"))["total"] or 0
    )

    remaining_balance = total_due - total_paid

    # ======================================================
    # ACTIVITÉ RÉCENTE
    # ======================================================
    recent_candidatures = Candidature.objects.order_by("-submitted_at")[:5]
    recent_inscriptions = Inscription.objects.order_by("-created_at")[:5]
    recent_payments = Payment.objects.order_by("-paid_at")[:5]

    # ======================================================
    # CONTEXT FINAL
    # ======================================================
    context = {

        # Candidatures
        "total_candidatures": total_candidatures,
        "under_review": under_review,
        "accepted": accepted,
        "rejected": rejected,
        "to_complete": to_complete,
        "acceptance_rate": acceptance_rate,

        # Inscriptions
        "total_inscriptions": total_inscriptions,
        "active_inscriptions": active_inscriptions,
        "suspended_inscriptions": suspended_inscriptions,
        "unpaid_inscriptions": unpaid_inscriptions,

        # Paiements
        "total_payments": total_payments,
        "total_revenue": total_revenue,
        "monthly_revenue": monthly_revenue,

        # Finances
        "remaining_balance": remaining_balance,
        "total_due": total_due,
        "total_paid": total_paid,

        # Activité
        "recent_candidatures": recent_candidatures,
        "recent_inscriptions": recent_inscriptions,
        "recent_payments": recent_payments,
    }

    return render(request, "dashboard/superadmin_dashboard.html", context)


import logging

logger = logging.getLogger(__name__)


from formations.models import Programme

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
    logger.warning(
        f"403 | User={request.user} | Path={request.path}"
    )

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
    logger.warning(
        f"400 | Bad request | Path={request.path}"
    )

    context = {
        "error_code": 400,
        "error_title": "Requête invalide",
        "error_message": "La requête envoyée est invalide ou mal formée.",
        **get_institution_context(),
    }

    return render(request, "core/errors/400.html", context, status=400)




from django.db.models import Avg, F, ExpressionWrapper, DurationField
from django.db.models.functions import Extract


def changelist_view(self, request, extra_context=None):

    extra_context = extra_context or {}

    queryset = self.get_queryset(request)

    total = queryset.count()
    new_count = queryset.filter(status="new").count()
    answered_qs = queryset.filter(answered_at__isnull=False)

    answered_count = answered_qs.count()

    # Calcul durée moyenne (answered_at - created_at)
    duration_expr = ExpressionWrapper(
        F("answered_at") - F("created_at"),
        output_field=DurationField()
    )

    avg_duration = answered_qs.annotate(
        response_time=duration_expr
    ).aggregate(
        avg=Avg("response_time")
    )["avg"]

    avg_hours = None
    if avg_duration:
        avg_hours = round(avg_duration.total_seconds() / 3600, 2)

    extra_context["stats"] = {
        "total": total,
        "new": new_count,
        "answered": answered_count,
        "avg_response_hours": avg_hours,
    }

    return super().changelist_view(
        request,
        extra_context=extra_context
    )



from django.views.decorators.http import require_http_methods
from django.shortcuts import render
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings

from .forms import ContactForm
from .models import ContactMessage
from .utils import get_institution_context  # évite import circulaire


@require_http_methods(["GET", "POST"])
def contact_view(request):

    if request.method == "POST":

        form = ContactForm(request.POST)

        if form.is_valid():

            contact_message = form.save(commit=False)
            contact_message.ip_address = request.META.get("REMOTE_ADDR")
            contact_message.user_agent = request.META.get("HTTP_USER_AGENT", "")
            contact_message.save()

            # ===============================
            # Email interne HTML
            # ===============================
            internal_context = {
                "message_obj": contact_message
            }

            internal_html = render_to_string(
                "emails/contact_internal.html",
                internal_context
            )

            internal_text = strip_tags(internal_html)

            internal_email = EmailMultiAlternatives(
                subject=f"[CONTACT] {contact_message.get_subject_display()}",
                body=internal_text,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[settings.DEFAULT_FROM_EMAIL],
            )

            internal_email.attach_alternative(internal_html, "text/html")
            internal_email.send()

            # ===============================
            # Email automatique utilisateur
            # ===============================
            user_context = {
                "message_obj": contact_message
            }

            user_html = render_to_string(
                "emails/contact_received.html",
                user_context
            )

            user_text = strip_tags(user_html)

            user_email = EmailMultiAlternatives(
                subject="Votre demande a bien été reçue",
                body=user_text,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[contact_message.email],
            )

            user_email.attach_alternative(user_html, "text/html")
            user_email.send()

            # ===============================
            # HTMX
            # ===============================
            if request.headers.get("HX-Request"):
                return render(
                    request,
                    "core/contact_success.html",
                    {"reference": contact_message.reference}
                )

            return render(
                request,
                "core/contact_success.html",
                {
                    "reference": contact_message.reference,
                    **get_institution_context(),
                }
            )

        if request.headers.get("HX-Request"):
            return render(
                request,
                "core/contact_form_partial.html",
                {"form": form}
            )

    else:
        form = ContactForm()

    context = {
        "form": form,
        **get_institution_context(),
    }

    return render(request, "core/contact.html", context)


from django.shortcuts import render
from .models import Institution, InstitutionStat

from django.shortcuts import render, get_object_or_404
from .models import Institution, InstitutionStat, AboutSection

def about(request):
    institution = get_object_or_404(Institution)

    stats = InstitutionStat.objects.all()
    about_sections = AboutSection.objects.filter(is_active=True)

    return render(
        request,
        "core/about.html",
        {
            "institution": institution,
            "stats": stats,
            "about_sections": about_sections,
        },
    )