import hashlib
import json
from datetime import datetime


# ======================================================
# PAYLOAD NORMALISÉ
# ======================================================

def build_receipt_payload(payment):
    """
    Construit les données utilisées pour générer
    la signature numérique du reçu.
    """

    inscription = payment.inscription
    candidature = inscription.candidature

    payload = {
        "receipt_number": payment.receipt_number,
        "payment_reference": payment.reference,
        "amount": payment.amount,
        "method": payment.method,
        "status": payment.status,
        "paid_at": payment.paid_at.isoformat(),

        "inscription_reference": str(inscription.reference),

        "candidate": {
            "first_name": candidature.first_name,
            "last_name": candidature.last_name,
            "email": candidature.email,
            "phone": candidature.phone,
        },

        "programme": {
            "title": candidature.programme.title,
        },
    }

    return payload


# ======================================================
# HASH CRYPTOGRAPHIQUE
# ======================================================

def generate_receipt_hash(payment):
    """
    Génère un cachet numérique SHA256
    utilisé pour vérifier l’authenticité du reçu.
    """

    payload = build_receipt_payload(payment)

    payload_string = json.dumps(
        payload,
        sort_keys=True
    )

    hash_object = hashlib.sha256(payload_string.encode())

    return hash_object.hexdigest()


# ======================================================
# HASH COURT (AFFICHAGE)
# ======================================================

def generate_short_hash(payment):
    """
    Version courte du hash pour affichage
    sur le reçu PDF.
    """

    full_hash = generate_receipt_hash(payment)

    return full_hash[:20].upper()


# ======================================================
# TIMESTAMP SIGNATURE
# ======================================================

def generate_signature_timestamp():
    """
    Timestamp officiel du cachet numérique.
    """

    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")