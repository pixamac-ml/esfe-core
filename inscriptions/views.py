# inscriptions/views.py

from django.shortcuts import get_object_or_404, render
from django.http import Http404

from inscriptions.models import Inscription
from payments.forms import StudentPaymentForm


def inscription_public_detail(request, token):
    """
    Vue publique sécurisée du dossier d’inscription.

    RÈGLES :
    - L’inscription DOIT exister
    - Accès protégé par access_code
    - Une inscription suspendue n’est pas payable
    """

    inscription = get_object_or_404(
        Inscription,
        public_token=token
    )

    # =====================================================
    # 🔐 SÉCURISATION PAR CODE D’ACCÈS
    # =====================================================
    session_key = f"inscription_access_{inscription.id}"

    # Si accès non validé
    if not request.session.get(session_key):

        if request.method == "POST":
            entered_code = request.POST.get("access_code", "").strip()

            if entered_code == inscription.access_code:
                request.session[session_key] = True
            else:
                return render(
                    request,
                    "inscriptions/access_required.html",
                    {"error": "Code d’accès incorrect."}
                )
        else:
            return render(
                request,
                "inscriptions/access_required.html"
            )

    # =====================================================
    # 🔒 BLOQUER SI SUSPENDUE
    # =====================================================
    if inscription.status == "suspended":
        raise Http404("Ce dossier est temporairement indisponible.")

    # =====================================================
    # HISTORIQUE DES PAIEMENTS
    # =====================================================
    payments = inscription.payments.order_by("-paid_at")

    # Paiement en attente
    has_pending_payment = payments.filter(status="pending").exists()

    # Autorisation de paiement
    can_pay = (
        inscription.status == "created"
        and inscription.balance > 0
        and not has_pending_payment
    )

    # =====================================================
    # INITIALISATION FORMULAIRE
    # =====================================================
    payment_form = None

    if can_pay:
        payment_form = StudentPaymentForm(
            inscription=inscription
        )

    # =====================================================
    # CONTEXTE FINAL
    # =====================================================
    context = {
        "inscription": inscription,
        "candidature": inscription.candidature,
        "programme": inscription.candidature.programme,

        "payments": payments,
        "payment_form": payment_form,

        "receipt_payment": (
            payments
            .filter(status="validated", receipt_number__isnull=False)
            .first()
        ),

        "can_pay": can_pay,
        "has_pending_payment": has_pending_payment,
    }

    return render(
        request,
        "inscriptions/public_detail.html",
        context
    )
