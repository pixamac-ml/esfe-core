# core/views.py

from django.shortcuts import render


# ==========================================================
# DONNÉES GLOBALES INSTITUTIONNELLES
# ==========================================================

def get_institution_context():
    return {
        "institution_name": "École Supérieure de Formation et d’Excellence",
        "description": (
            "Établissement d’enseignement supérieur dédié à la formation "
            "académique et professionnelle dans les sciences de la santé."
        ),
        "navigation": [
            {"label": "Accueil", "url": "/"},
            {"label": "Formations", "url": "/formations/"},
            {"label": "Candidatures", "url": "/candidature/"},
            {"label": "Contact", "url": "/contact/"},
        ],
        "contact": {
            "address": "Bamako, Mali",
            "phone": "+223 XX XX XX XX",
            "email": "contact@esfe.edu.ml",
        },
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
# MENTIONS LÉGALES
# ==========================================================

def legal_notice(request):

    context = {
        "page_title": "Mentions légales",
        **get_institution_context(),
    }

    return render(request, "legal_notice.html", context)


# ==========================================================
# POLITIQUE DE CONFIDENTIALITÉ
# ==========================================================

def privacy_policy(request):

    context = {
        "page_title": "Politique de confidentialité",
        **get_institution_context(),
    }

    return render(request, "privacy_policy.html", context)


# ==========================================================
# CONDITIONS D’UTILISATION
# ==========================================================

def terms_of_service(request):

    context = {
        "page_title": "Conditions générales d’utilisation",
        **get_institution_context(),
    }

    return render(request, "terms_of_service.html", context)


# ==========================================================
# PLAN DU SITE
# ==========================================================

def sitemap(request):

    context = {
        "page_title": "Plan du site",
        **get_institution_context(),
    }

    return render(request, "sitemap.html", context)
