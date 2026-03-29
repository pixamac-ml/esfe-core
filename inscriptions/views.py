# inscriptions/views.py

from django.shortcuts import get_object_or_404, render
from django.http import Http404

from inscriptions.models import Inscription
from payments.forms import StudentPaymentForm


def _can_initiate_payment(inscription, has_pending_payment):
    payable_statuses = {
        Inscription.STATUS_CREATED,
        Inscription.STATUS_AWAITING_PAYMENT,
        Inscription.STATUS_PARTIAL,
    }
    return (
        inscription.status in payable_statuses
        and inscription.balance > 0
        and not has_pending_payment
    )


def inscription_public_detail(request, token):
    """
    Vue publique sécurisée du dossier d'inscription.
    - Accès protégé par access_code via session
    - Retourne soit la page complète, soit un fragment HTMX pour instantanéité
    """

    inscription = get_object_or_404(Inscription, public_token=token)

    # Vérification du code d'accès via session
    session_key = f"inscription_access_{inscription.id}"

    # Si accès non validé
    if not request.session.get(session_key):
        if request.method == "POST":
            entered_code = request.POST.get("access_code", "").strip()

            if entered_code == inscription.access_code:
                request.session[session_key] = True
            else:
                # Réponse HTMX si requête HTMX
                if request.headers.get("HX-Request"):
                    response = render(
                        request,
                        "payments/partials/access_form_error.html",
                        {"error": "Code d'accès incorrect."}
                    )
                    response["HX-Trigger"] = '{"toast": {"type": "error", "message": "Code d\'accès incorrect."}}'
                    return response
                return render(request, "inscriptions/access_required.html", {"error": "Code d'accès incorrect."})
        else:
            return render(request, "inscriptions/access_required.html")

    # Bloquer si suspendue
    if inscription.status == "suspended":
        raise Http404("Ce dossier est temporairement indisponible.")

    # Historique des paiements
    payments = inscription.payments.order_by("-paid_at")
    has_pending_payment = payments.filter(status="pending").exists()
    can_pay = _can_initiate_payment(inscription, has_pending_payment)
    payment_form = StudentPaymentForm(inscription=inscription) if can_pay else None

    context = {
        "inscription": inscription,
        "candidature": inscription.candidature,
        "programme": inscription.candidature.programme,
        "payments": payments,
        "payment_form": payment_form,
        "receipt_payment": payments.filter(status="validated", receipt_number__isnull=False).first(),
        "can_pay": can_pay,
        "has_pending_payment": has_pending_payment,
    }

    # Réponse HTMX
    if request.headers.get("HX-Request"):
        return render(request, "payments/partials/inscription_finance.html", context)

    # Réponse classique
    return render(request, "inscriptions/public_detail.html", context)

