# core/views.py

from django.shortcuts import render, get_object_or_404
from django.http import Http404, HttpResponse
from django.utils.html import strip_tags

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


# ==========================================================
# PAGE D’ACCUEIL
# ==========================================================

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

    context = {
        "pillars": pillars,
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
