# payments/views.py

from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.http import FileResponse, Http404

from inscriptions.models import Inscription
from payments.models import Payment
from payments.forms import StudentPaymentForm


# ==================================================
# DEMANDE DE PAIEMENT (ÉTUDIANT – LIEN PUBLIC)
# ==================================================
def student_initiate_payment(request, token):

    inscription = get_object_or_404(
        Inscription,
        public_token=token
    )

    if request.method != "POST":
        return redirect(inscription.get_public_url())

    form = StudentPaymentForm(
        request.POST,
        inscription=inscription
    )

    payments = inscription.payments.order_by("-paid_at")
    has_pending_payment = payments.filter(status="pending").exists()

    can_pay = (
        inscription.status == "created"
        and inscription.balance > 0
        and not has_pending_payment
    )

    if not form.is_valid():
        return render(
            request,
            "inscriptions/public_detail.html",
            {
                "inscription": inscription,
                "candidature": inscription.candidature,
                "programme": inscription.candidature.programme,
                "payments": payments,
                "payment_form": form,
                "can_pay": can_pay,
                "has_pending_payment": has_pending_payment,
            }
        )

    amount = form.cleaned_data["amount"]
    method = form.cleaned_data["method"]

    # 🔐 Sécurité serveur (toujours)
    if amount > inscription.balance:
        messages.error(request, "Le montant dépasse le solde restant.")
        return redirect(inscription.get_public_url())

    if has_pending_payment:
        messages.warning(
            request,
            "Un paiement est déjà en attente de validation."
        )
        return redirect(inscription.get_public_url())

    # ================================
    # Création paiement
    # ================================
    Payment.objects.create(
        inscription=inscription,
        amount=amount,
        method=method,
        status="pending",
        reference="INITIATED_BY_STUDENT",
        agent=form.agent if method == "cash" else None
    )

    messages.success(
        request,
        "Votre demande de paiement a été transmise à l’administration."
    )

    return redirect(inscription.get_public_url())


# ==================================================
# AFFICHAGE PUBLIC D’UN REÇU
# ==================================================
def receipt_public_detail(request, receipt_number):
    payment = get_object_or_404(
        Payment,
        receipt_number=receipt_number,
        status="validated"
    )

    inscription = payment.inscription

    return render(
        request,
        "payments/receipt_detail.html",
        {
            "payment": payment,
            "inscription": inscription,
            "candidature": inscription.candidature,
            "programme": inscription.candidature.programme,
        }
    )


# ==================================================
# TÉLÉCHARGEMENT DU REÇU PDF
# ==================================================
def receipt_pdf(request, receipt_number):
    payment = get_object_or_404(
        Payment,
        receipt_number=receipt_number,
        status="validated"
    )

    if not payment.receipt_pdf:
        raise Http404("Le reçu PDF n’est pas disponible.")

    return FileResponse(
        payment.receipt_pdf.open("rb"),
        as_attachment=True,
        filename=f"recu-{payment.receipt_number}.pdf"
    )

from django.http import JsonResponse
from django.views.decorators.http import require_GET
from payments.models import PaymentAgent


@require_GET
def verify_agent_ajax(request):

    name = request.GET.get("name", "").strip()

    if not name:
        return JsonResponse({"valid": False})

    parts = name.split()

    queryset = PaymentAgent.objects.select_related("user").filter(
        is_active=True
    )

    from django.db.models import Q

    query = Q()
    for part in parts:
        query &= (
            Q(user__first_name__icontains=part) |
            Q(user__last_name__icontains=part)
        )

    agent = queryset.filter(query).distinct().first()

    if not agent:
        return JsonResponse({"valid": False})

    return JsonResponse({
        "valid": True,
        "full_name": agent.user.get_full_name(),
        "agent_code": agent.agent_code
    })
