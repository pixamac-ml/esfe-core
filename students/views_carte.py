"""
Vues carte étudiant ESFE :
  - Génération PDF (WeasyPrint)
  - Aperçu HTML
  - Portail de vérification public
  - Authentification par scan QR + PIN
"""

import base64
import logging
import secrets
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.core import signing
from django.http import HttpResponse
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods, require_POST

from accounts.authentication import AuthenticationGate
from students.models import CarteEtudiant, VerificationLog
from students.services.card_security import (
    carte_pin_verrouillee,
    generer_code_lisible,
    generer_qr_png,
    generer_qr_svg,
    incrementer_tentatives_pin,
    reinitialiser_tentatives_pin,
    signer_carte,
    signer_carte_reference,
    verif_rate_limitee,
    verifier_token,
)

logger = logging.getLogger(__name__)

CARD_LOGIN_SALT = "students.card-login.v1"
CARD_LOGIN_SESSION_KEY = "card_login_nonce"
CARD_LOGIN_MAX_AGE_SECONDS = 300


def _card_login_signer():
    return signing.TimestampSigner(
        key=settings.CARD_SIGNING_KEY or settings.SECRET_KEY,
        salt=CARD_LOGIN_SALT,
    )


def _issue_card_login_challenge(request, carte):
    nonce = secrets.token_urlsafe(24)
    request.session[CARD_LOGIN_SESSION_KEY] = nonce
    payload = f"{carte.pk}:{nonce}"
    return _card_login_signer().sign(payload)


def _consume_card_login_challenge(request, challenge):
    expected_nonce = request.session.pop(CARD_LOGIN_SESSION_KEY, None)
    if not challenge or not expected_nonce:
        return None
    try:
        payload = _card_login_signer().unsign(
            challenge,
            max_age=CARD_LOGIN_MAX_AGE_SECONDS,
        )
        carte_id, nonce = payload.split(":", 1)
    except (signing.BadSignature, signing.SignatureExpired, ValueError):
        return None
    if not secrets.compare_digest(nonce, expected_nonce):
        return None
    try:
        return int(carte_id)
    except ValueError:
        return None

# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------

def _get_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")


def _carte_url(request, carte: CarteEtudiant) -> str:
    token = signer_carte_reference(
        reference=str(carte.public_reference),
        annee=carte.annee,
        annexe=carte.code_annexe,
        kind="student",
    )
    return f"{settings.BASE_URL}{reverse('students:portail_verify_token', args=[token])}"


def _student_card_tokens(carte: CarteEtudiant):
    """Émet le QR opaque courant et accepte v1 seulement avant réémission."""
    yield signer_carte_reference(
        reference=str(carte.public_reference), annee=carte.annee,
        annexe=carte.code_annexe, kind="student",
    )
    if carte.token_version == "v1":
        yield signer_carte(carte.etudiant.matricule, carte.annee, carte.code_annexe)


def _student_card_from_payload(payload):
    queryset = CarteEtudiant.objects.select_related("etudiant__inscription__candidature")
    if payload.get("kind") != "student":
        return None
    if payload.get("version") == "v2":
        return queryset.filter(
            public_reference=payload.get("reference"), annee=payload["annee"],
            code_annexe=payload["annexe"],
        ).first()
    return queryset.filter(
        etudiant__matricule=payload.get("matricule"), annee=payload["annee"],
        code_annexe=payload["annexe"], token_version="v1",
    ).first()


def _can_manage_card(request, carte: CarteEtudiant) -> bool:
    if request.user.is_superuser:
        return True
    profile = getattr(request.user, "profile", None)
    card_branch_id = carte.etudiant.inscription.candidature.branch_id
    return bool(profile and profile.position == "it_support" and profile.branch_id == card_branch_id)


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
    token = next(_student_card_tokens(carte))
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


def _carte_print_context(request, carte: CarteEtudiant) -> dict:
    card = _carte_context(request, carte)
    card["branch_name"] = carte.code_annexe
    return {"card_pages": [[card]], "card_type": "student"}


@login_required
def carte_apercu_view(request, carte_id: int):
    carte = get_object_or_404(CarteEtudiant, pk=carte_id)
    if not _can_manage_card(request, carte):
        return HttpResponseForbidden("Acces refuse.")
    return render(request, "students/cards_print_sheet.html", _carte_print_context(request, carte))


# ---------------------------------------------------------------
# PDF WeasyPrint
# ---------------------------------------------------------------

@login_required
def carte_pdf_view(request, carte_id: int):
    from weasyprint import HTML
    from django.template.loader import render_to_string

    carte = get_object_or_404(CarteEtudiant, pk=carte_id)
    if not _can_manage_card(request, carte):
        return HttpResponseForbidden("Acces refuse.")
    ctx = _carte_print_context(request, carte)
    html_str = render_to_string("students/cards_print_sheet.html", ctx, request=request)
    pdf = HTML(string=html_str, base_url=settings.BASE_URL).write_pdf()

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
        if any(generer_code_lisible(token) == code for token in _student_card_tokens(carte)):
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

    carte = _student_card_from_payload(payload)
    if carte is None:
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


@require_http_methods(["GET"])
def portail_verify_staff_token_view(request, token: str):
    """Vérification publique minimale des cartes professionnelles par QR."""
    from accounts.models import CartePersonnel

    ip = _get_ip(request)
    if verif_rate_limitee(ip):
        messages.error(request, "Trop de tentatives. Veuillez patienter.")
        return render(request, "students/portail_verification.html", status=429)
    payload = verifier_token(token)
    if not payload or payload.get("version") != "v2" or payload.get("kind") != "staff":
        VerificationLog.objects.create(ip=ip, resultat="signature_invalide")
        return render(request, "students/portail_verification.html", {
            "resultat": {"valide": False, "message": "Carte non authentique ou QR illisible."},
        })
    carte = CartePersonnel.objects.select_related("profile__user").filter(
        public_reference=payload["reference"], annee=payload["annee"],
        code_annexe=payload["annexe"],
    ).first()
    if not carte or not carte.is_valide:
        VerificationLog.objects.create(
            staff_card=carte,
            ip=ip,
            resultat=carte.statut if carte else "carte_inconnue",
        )
        return render(request, "students/portail_verification.html", {
            "resultat": {"valide": False, "message": "Carte professionnelle non valide."},
        })
    VerificationLog.objects.create(staff_card=carte, ip=ip, resultat="valide")
    return render(request, "students/portail_verification.html", {
        "resultat": {"valide": True, "carte": carte, "type": "staff"},
    })


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

    carte = _student_card_from_payload(payload)
    if carte is None:
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
        "card_challenge": _issue_card_login_challenge(request, carte),
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
    carte_id = _consume_card_login_challenge(
        request,
        request.POST.get("card_challenge", ""),
    )
    raw_pin = request.POST.get("pin", "")

    try:
        carte = CarteEtudiant.objects.select_related("etudiant__user").get(pk=carte_id)
    except (TypeError, CarteEtudiant.DoesNotExist):
        ctx = {"step": "error", "message": "Session expirée. Recommencez le scan."}
        return render(request, "students/partials/card_scan_login.html", ctx)

    if not carte.is_valide:
        ctx = {"step": "error", "message": "Votre carte n'est plus valide."}
        return render(request, "students/partials/card_scan_login.html", ctx)

    if carte_pin_verrouillee(carte_id):
        ctx = {
            "step": "pin",
            "card_challenge": _issue_card_login_challenge(request, carte),
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
            "card_challenge": _issue_card_login_challenge(request, carte),
            "nom_etudiant": carte.etudiant.full_name,
            "erreur_pin": msg,
        }
        return render(request, "students/partials/card_scan_login.html", ctx)

    # PIN correct → connexion
    reinitialiser_tentatives_pin(carte_id)
    user = carte.etudiant.user
    auth_decision = AuthenticationGate.evaluate(user)
    if not auth_decision.allowed:
        ctx = {"step": "error", "message": auth_decision.message}
        return render(request, "students/partials/card_scan_login.html", ctx)
    request._esfe_authentication_method = "student_card"
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")

    from portal.permissions import get_post_login_portal_url
    redirect_url = get_post_login_portal_url(user)

    # HTMX : déclencher une redirection via HX-Redirect
    response = HttpResponse(status=204)
    response["HX-Redirect"] = redirect_url
    return response
