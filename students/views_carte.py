"""
Vues carte étudiant ESFE :
  - Génération PDF (WeasyPrint)
  - Aperçu HTML
  - Portail de vérification public
  - Authentification par scan QR + PIN
"""

import base64
import logging
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_POST

from students.models import CarteEtudiant, VerificationLog
from students.services.card_security import (
    carte_pin_verrouillee,
    generer_code_lisible,
    generer_qr_png,
    generer_qr_svg,
    incrementer_tentatives_pin,
    reinitialiser_tentatives_pin,
    signer_carte,
    verif_rate_limitee,
    verifier_token,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------

def _get_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")


def _carte_url(request, carte: CarteEtudiant) -> str:
    token = signer_carte(
        carte.etudiant.matricule,
        carte.annee,
        carte.code_annexe,
    )
    return request.build_absolute_uri(f"/carte/v/{token}/")


def _get_classe(carte: CarteEtudiant) -> str:
    try:
        enrollment = carte.etudiant.current_academic_enrollment
        if enrollment:
            return str(enrollment.academic_class)
    except Exception:
        pass
    return ""


def _logo_data_uri() -> str:
    """Lit le logo ESFE depuis static/img/ et le retourne en data-URI (fiable WeasyPrint)."""
    logo_path = Path(settings.BASE_DIR) / "static" / "img" / "logo_esfe.png"
    try:
        data = logo_path.read_bytes()
        return "data:image/png;base64," + base64.b64encode(data).decode()
    except FileNotFoundError:
        return ""


# ---------------------------------------------------------------
# Aperçu HTML (debug / preview)
# ---------------------------------------------------------------

def _carte_context(request, carte: CarteEtudiant) -> dict:
    token = signer_carte(carte.etudiant.matricule, carte.annee, carte.code_annexe)
    url = _carte_url(request, carte)
    return {
        "carte": carte,
        "etudiant": carte.etudiant,
        "classe": _get_classe(carte),
        "qr_png": generer_qr_png(url),
        "qr_svg": generer_qr_svg(url),
        "code_verification": generer_code_lisible(token),
        "logo_data_uri": _logo_data_uri(),
    }


def carte_apercu_view(request, carte_id: int):
    carte = get_object_or_404(CarteEtudiant, pk=carte_id)
    return render(request, "students/carte_etudiant.html", _carte_context(request, carte))


# ---------------------------------------------------------------
# PDF WeasyPrint
# ---------------------------------------------------------------

def carte_pdf_view(request, carte_id: int):
    from weasyprint import HTML
    from django.template.loader import render_to_string

    carte = get_object_or_404(CarteEtudiant, pk=carte_id)
    ctx = _carte_context(request, carte)
    html_str = render_to_string("students/carte_etudiant.html", ctx, request=request)
    pdf = HTML(string=html_str, base_url=request.build_absolute_uri("/")).write_pdf()

    matricule = carte.etudiant.matricule
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="carte_{matricule}.pdf"'
    return response


# ---------------------------------------------------------------
# Portail de vérification public
# ---------------------------------------------------------------

@csrf_protect
@require_http_methods(["GET", "POST"])
def portail_verification_view(request):
    if request.method == "GET":
        return render(request, "students/portail_verification.html")

    ip = _get_ip(request)
    if verif_rate_limitee(ip):
        messages.error(request, "Trop de tentatives. Veuillez patienter avant de réessayer.")
        return render(request, "students/portail_verification.html", status=429)

    code = request.POST.get("code", "").strip().upper()
    if not code:
        messages.error(request, "Veuillez saisir un code de vérification.")
        return render(request, "students/portail_verification.html")

    # Chercher les cartes actives dont le code correspond
    cartes = CarteEtudiant.objects.filter(statut="active").select_related("etudiant")
    carte_trouvee = None
    for carte in cartes:
        token = signer_carte(carte.etudiant.matricule, carte.annee, carte.code_annexe)
        if generer_code_lisible(token) == code:
            carte_trouvee = carte
            break

    if carte_trouvee and carte_trouvee.is_valide:
        VerificationLog.objects.create(
            carte=carte_trouvee, code_tente=code, ip=ip, resultat="valide"
        )
        ctx = {
            "resultat": {
                "valide": True,
                "carte": carte_trouvee,
                "classe": _get_classe(carte_trouvee),
            }
        }
    else:
        VerificationLog.objects.create(code_tente=code, ip=ip, resultat="invalide")
        raison = "Carte expirée ou révoquée." if carte_trouvee else "Code inconnu ou invalide."
        ctx = {
            "resultat": {
                "valide": False,
                "message": raison,
            }
        }

    return render(request, "students/portail_verification.html", ctx)


@require_http_methods(["GET"])
def portail_verify_token_view(request, token: str):
    """Endpoint direct depuis le scan QR (/carte/v/<token>/)."""
    ip = _get_ip(request)
    if verif_rate_limitee(ip):
        messages.error(request, "Trop de tentatives. Veuillez patienter.")
        return render(request, "students/portail_verification.html", status=429)

    payload = verifier_token(token)
    if not payload:
        VerificationLog.objects.create(ip=ip, resultat="signature_invalide")
        ctx = {"resultat": {"valide": False, "message": "Carte non authentique ou QR illisible."}}
        return render(request, "students/portail_verification.html", ctx)

    try:
        carte = CarteEtudiant.objects.select_related("etudiant").get(
            etudiant__matricule=payload["matricule"],
            annee=payload["annee"],
            code_annexe=payload["annexe"],
        )
    except CarteEtudiant.DoesNotExist:
        VerificationLog.objects.create(ip=ip, resultat="carte_inconnue")
        ctx = {"resultat": {"valide": False, "message": "Aucune carte correspondante en base."}}
        return render(request, "students/portail_verification.html", ctx)

    if carte.is_valide:
        VerificationLog.objects.create(carte=carte, ip=ip, resultat="valide")
        ctx = {"resultat": {"valide": True, "carte": carte, "classe": _get_classe(carte)}}
    else:
        VerificationLog.objects.create(carte=carte, ip=ip, resultat=carte.statut)
        msg = {
            "revoquee": "Carte révoquée par l'établissement.",
            "perdue": "Carte déclarée perdue. Contactez l'administration.",
            "expiree": "Carte expirée.",
        }.get(carte.statut, "Carte non valide.")
        ctx = {"resultat": {"valide": False, "message": msg}}

    return render(request, "students/portail_verification.html", ctx)


# ---------------------------------------------------------------
# Authentification par scan QR + PIN (HTMX)
# ---------------------------------------------------------------

@require_http_methods(["GET", "POST"])
@csrf_protect
def card_scan_verify_view(request):
    """
    Étape 1 : reçoit le token décodé du QR depuis le JS navigateur.
    Vérifie signature + statut + expiration.
    Si valide → renvoie le formulaire PIN (step=pin).
    """
    if request.method == "GET":
        return render(request, "students/partials/card_scan_login.html", {"step": "camera"})

    token = request.POST.get("token", "").strip()
    if not token:
        ctx = {"step": "error", "message": "Token manquant."}
        return render(request, "students/partials/card_scan_login.html", ctx)

    payload = verifier_token(token)
    if not payload:
        ctx = {"step": "error", "message": "QR non reconnu ou carte falsifiée."}
        return render(request, "students/partials/card_scan_login.html", ctx)

    try:
        carte = CarteEtudiant.objects.select_related("etudiant__inscription__candidature").get(
            etudiant__matricule=payload["matricule"],
            annee=payload["annee"],
            code_annexe=payload["annexe"],
        )
    except CarteEtudiant.DoesNotExist:
        ctx = {"step": "error", "message": "Votre carte n'est pas enregistrée dans le système."}
        return render(request, "students/partials/card_scan_login.html", ctx)

    if not carte.is_valide:
        msg = {
            "revoquee": "Votre carte a été révoquée. Contactez l'administration.",
            "perdue": "Votre carte est déclarée perdue. Contactez l'administration.",
            "expiree": "Votre carte est expirée. Munissez-vous d'une carte en cours de validité.",
        }.get(carte.statut, "Votre carte n'est pas valide. Munissez-vous d'une carte en cours de validité.")
        ctx = {"step": "error", "message": msg}
        return render(request, "students/partials/card_scan_login.html", ctx)

    if not carte.etudiant.has_pin:
        ctx = {"step": "error", "message": "Aucun code PIN défini. Contactez l'informaticien de votre annexe."}
        return render(request, "students/partials/card_scan_login.html", ctx)

    ctx = {
        "step": "pin",
        "carte_id": carte.pk,
        "nom_etudiant": carte.etudiant.full_name,
    }
    return render(request, "students/partials/card_scan_login.html", ctx)


@require_POST
@csrf_protect
def card_pin_verify_view(request):
    """
    Étape 2 : vérifie le PIN, ouvre la session Django si correct.
    Rate limiting : blocage après 5 tentatives (30 min).
    """
    carte_id = request.POST.get("carte_id", "")
    raw_pin = request.POST.get("pin", "")

    try:
        carte_id = int(carte_id)
        carte = CarteEtudiant.objects.select_related("etudiant__user").get(pk=carte_id)
    except (ValueError, CarteEtudiant.DoesNotExist):
        ctx = {"step": "error", "message": "Session expirée. Recommencez le scan."}
        return render(request, "students/partials/card_scan_login.html", ctx)

    if not carte.is_valide:
        ctx = {"step": "error", "message": "Votre carte n'est plus valide."}
        return render(request, "students/partials/card_scan_login.html", ctx)

    if carte_pin_verrouillee(carte_id):
        ctx = {
            "step": "pin",
            "carte_id": carte_id,
            "nom_etudiant": carte.etudiant.full_name,
            "erreur_pin": "Compte temporairement verrouillé après trop d'essais. Réessayez dans 30 minutes.",
        }
        return render(request, "students/partials/card_scan_login.html", ctx)

    if not carte.etudiant.check_pin(raw_pin):
        tentatives = incrementer_tentatives_pin(carte_id)
        restants = max(0, 5 - tentatives)
        msg = f"PIN incorrect. {restants} tentative(s) restante(s)." if restants else "Compte verrouillé pour 30 minutes."
        ctx = {
            "step": "pin",
            "carte_id": carte_id,
            "nom_etudiant": carte.etudiant.full_name,
            "erreur_pin": msg,
        }
        return render(request, "students/partials/card_scan_login.html", ctx)

    # PIN correct → connexion
    reinitialiser_tentatives_pin(carte_id)
    user = carte.etudiant.user
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")

    from portal.permissions import get_post_login_portal_url
    redirect_url = get_post_login_portal_url(user)

    # HTMX : déclencher une redirection via HX-Redirect
    response = HttpResponse(status=204)
    response["HX-Redirect"] = redirect_url
    return response
