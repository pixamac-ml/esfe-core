"""
Socle de sécurité des cartes étudiantes ESFE.

Token format : v1.<payload_b64url>.<hmac_sha256_b64url>
Payload      : "matricule|annee|annexe"  (jamais de statut — il change en base)
Clé          : CARD_SIGNING_KEY (variable d'environnement, distincte de SECRET_KEY)
"""

import base64
import hashlib
import hmac
import io

import qrcode
from django.conf import settings


# -------------------------------------------------------------------
# Helpers base64url (sans padding)
# -------------------------------------------------------------------

def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    s += "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s)


def _signing_key() -> bytes:
    key = getattr(settings, "CARD_SIGNING_KEY", None)
    if not key:
        raise RuntimeError(
            "CARD_SIGNING_KEY n'est pas défini dans les paramètres. "
            "Ajoutez-le dans .env : CARD_SIGNING_KEY=<clé aléatoire>"
        )
    return key.encode()


# -------------------------------------------------------------------
# Signature / vérification
# -------------------------------------------------------------------

def signer_carte(matricule: str, annee: str, annexe: str) -> str:
    payload = f"{matricule}|{annee}|{annexe}".encode()
    sig = hmac.new(_signing_key(), payload, hashlib.sha256).digest()
    return f"v1.{_b64(payload)}.{_b64(sig)}"


def verifier_token(token: str) -> dict | None:
    """
    Vérifie la signature HMAC.
    Retourne {"matricule", "annee", "annexe"} si valide, None sinon.
    Ne vérifie PAS le statut/expiration — c'est le rôle de CarteEtudiant.is_valide.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3 or parts[0] != "v1":
            return None
        payload_bytes = _b64d(parts[1])
        expected_sig = hmac.new(_signing_key(), payload_bytes, hashlib.sha256).digest()
        provided_sig = _b64d(parts[2])
        if not hmac.compare_digest(expected_sig, provided_sig):
            return None
        matricule, annee, annexe = payload_bytes.decode().split("|")
        return {"matricule": matricule, "annee": annee, "annexe": annexe}
    except Exception:
        return None


# -------------------------------------------------------------------
# Code de vérification lisible (verso carte)
# Tronqué → usage vérification + rate limiting uniquement, pas auth forte.
# -------------------------------------------------------------------

def generer_code_lisible(token: str) -> str:
    """Ex. de sortie : 3F9A-7C21-D8E4"""
    try:
        sig_bytes = _b64d(token.split(".")[2])
        hex_part = sig_bytes[:6].hex().upper()
        return f"{hex_part[:4]}-{hex_part[4:8]}-{hex_part[8:]}"
    except Exception:
        return ""


def code_depuis_matricule_annee_annexe(matricule: str, annee: str, annexe: str) -> str:
    token = signer_carte(matricule, annee, annexe)
    return generer_code_lisible(token)


# -------------------------------------------------------------------
# Génération QR (data-URI base64, sans appel externe)
# -------------------------------------------------------------------

def generer_qr_png(url: str) -> str:
    """PNG base64 data URI — garanti rendu par WeasyPrint via <img>."""
    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0A2138", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def generer_qr_data_uri(url: str) -> str:
    return generer_qr_png(url)


def generer_qr_svg(url: str) -> str:
    """SVG inline généré module par module (rect).
    Garanti compatible WeasyPrint — aucun facteur image, aucun mm, aucun chemin complexe.
    """
    qr = qrcode.QRCode(
        version=2,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=1,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    matrix = qr.get_matrix()
    n = len(matrix)
    rects = []
    for y, row in enumerate(matrix):
        for x, cell in enumerate(row):
            if cell:
                rects.append(f'<rect x="{x}" y="{y}" width="1" height="1"/>')
    modules = "".join(rects)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" '
        f'style="width:100%;height:100%;display:block;">'
        f'<rect width="{n}" height="{n}" fill="#fff"/>'
        f'<g fill="#0A2138">{modules}</g>'
        f'</svg>'
    )


# -------------------------------------------------------------------
# Rate limiting PIN (cache Django)
# -------------------------------------------------------------------

def _pin_cache_key(carte_id: int) -> str:
    return f"card_pin_attempts_{carte_id}"


def incrementer_tentatives_pin(carte_id: int) -> int:
    from django.core.cache import cache
    key = _pin_cache_key(carte_id)
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=1800)  # 30 min
        return 1


def reinitialiser_tentatives_pin(carte_id: int) -> None:
    from django.core.cache import cache
    cache.delete(_pin_cache_key(carte_id))


def carte_pin_verrouillee(carte_id: int, limite: int = 5) -> bool:
    from django.core.cache import cache
    return (cache.get(_pin_cache_key(carte_id)) or 0) >= limite


# -------------------------------------------------------------------
# Rate limiting portail de vérification (anti-énumération)
# -------------------------------------------------------------------

def _verif_cache_key(ip: str) -> str:
    return f"card_verif_attempts_{ip}"


def verif_rate_limitee(ip: str, limite: int = 10, fenetre: int = 60) -> bool:
    from django.core.cache import cache
    key = _verif_cache_key(ip)
    count = cache.get(key, 0)
    if count >= limite:
        return True
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=fenetre)
    return False
