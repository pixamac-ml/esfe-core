# payments/views.py
# ==================================================
# Vues pour la gestion des paiements avec HTMX
# Optimisé pour la fluidité et l'instantanéité
# ==================================================

from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.http import FileResponse, Http404, JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.db import transaction
from django.db.models import Q
import logging

from inscriptions.models import Inscription
from payments.models import Payment, PaymentAgent, CashPaymentSession
from payments.forms import StudentPaymentForm
from payments.services.cash import verify_agent_and_create_session, validate_cash_code

from django.utils import timezone
from datetime import timedelta
import random


logger = logging.getLogger(__name__)


def _can_initiate_payment(inscription, has_pending_payment):
    """Détermine si un dossier peut initier un nouveau paiement."""
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


def _has_inscription_access(request, inscription):
    session_key = f"inscription_access_{inscription.id}"
    return bool(request.session.get(session_key))


# ==================================================
# 1. INITIER UN PAIEMENT (HTMX - Instantané)
# ==================================================

@require_POST
def student_initiate_payment(request, token):
    """
    Initie une demande de paiement via HTMX.
    Retourne un fragment mis à jour sans recharger la page.
    """

    inscription = get_object_or_404(
        Inscription,
        public_token=token
    )

    if not _has_inscription_access(request, inscription):
        response = render(
            request,
            "payments/partials/payment_error.html",
            {"message": "Accès non autorisé."},
            status=403,
        )
        response["HX-Trigger"] = '{"toast": {"type": "error", "message": "Accès non autorisé."}}'
        return response

    # Récupérer le contexte actuel
    payments = inscription.payments.order_by("-paid_at")
    has_pending_payment = payments.filter(status="pending").exists()

    can_pay = _can_initiate_payment(inscription, has_pending_payment)

    # Initialiser le formulaire
    form = StudentPaymentForm(
        request.POST,
        inscription=inscription
    )

    # Réponse contexte de base
    context = {
        "inscription": inscription,
        "candidature": inscription.candidature,
        "programme": inscription.candidature.programme,
        "payments": payments,
        "can_pay": can_pay,
        "has_pending_payment": has_pending_payment,
        "payment_form": None,
    }

    # Validation du formulaire
    if not form.is_valid():
        logger.warning(
            "Formulaire paiement invalide: token=%s data=%s errors=%s",
            token,
            dict(request.POST),
            form.errors.get_json_data(),
        )
        context["payment_form"] = form
        context["can_pay"] = can_pay

        response = render(
            request,
            "payments/partials/payment_form.html",
            context,
            status=400
        )
        response["HX-Trigger"] = '{"toast": {"type": "error", "message": "Veuillez corriger les erreurs du formulaire."}}'
        return response

    # Validation métier supplémentaire
    amount = form.cleaned_data["amount"]
    method = form.cleaned_data["method"]

    if amount > inscription.balance:
        logger.warning(
            "Montant paiement invalide: inscription=%s amount=%s balance=%s method=%s",
            inscription.id,
            amount,
            inscription.balance,
            method,
        )
        form.add_error("amount", "Le montant dépasse le solde restant.")
        context["payment_form"] = form
        context["can_pay"] = can_pay

        response = render(
            request,
            "payments/partials/payment_form.html",
            context,
            status=400
        )
        response["HX-Trigger"] = '{"toast": {"type": "error", "message": "Le montant dépasse le solde restant."}}'
        return response

    if has_pending_payment:
        logger.warning(
            "Paiement refuse car un paiement pending existe deja: inscription=%s method=%s",
            inscription.id,
            method,
        )
        response = render(
            request,
            "payments/partials/payment_error.html",
            {"message": "Un paiement est déjà en attente de validation."}
        )
        response["HX-Trigger"] = '{"toast": {"type": "warning", "message": "Un paiement est déjà en attente."}}'
        return response

    with transaction.atomic():
        inscription = (
            Inscription.objects
            .select_for_update()
            .select_related("candidature", "candidature__programme")
            .get(pk=inscription.pk)
        )

        has_pending_payment = inscription.payments.filter(status=Payment.STATUS_PENDING).exists()
        can_pay = _can_initiate_payment(inscription, has_pending_payment)

        if not can_pay:
            logger.warning(
                "Paiement impossible pour inscription=%s status=%s balance=%s method=%s",
                inscription.id,
                inscription.status,
                inscription.balance,
                method,
            )
            response = render(
                request,
                "payments/partials/payment_error.html",
                {"message": "Paiement impossible pour ce dossier actuellement."},
            )
            response["HX-Trigger"] = '{"toast": {"type": "warning", "message": "Paiement impossible pour ce dossier actuellement."}}'
            return response

        payment = Payment.objects.create(
            inscription=inscription,
            amount=amount,
            method=method,
            status=Payment.STATUS_PENDING,
            reference="INITIATED_BY_STUDENT",
            agent=form.agent if method == Payment.METHOD_CASH else None,
            cash_session=form.cash_session if method == Payment.METHOD_CASH else None,
        )

        # Au premier paiement initié, le dossier passe en attente de paiement.
        if inscription.status == Inscription.STATUS_CREATED:
            inscription.status = Inscription.STATUS_AWAITING_PAYMENT
            inscription.save(update_fields=["status"])

    # Mettre à jour le contexte
    payments = inscription.payments.order_by("-paid_at")
    has_pending_payment = payments.filter(status="pending").exists()

    context.update({
        "payments": payments,
        "has_pending_payment": has_pending_payment,
        "can_pay": False,
        "payment_form": None,
        "last_payment": payment,
    })

    # Réponse HTMX
    response = render(
        request,
        "payments/partials/inscription_finance.html",
        context
    )

    # Toast de succès
    response["HX-Trigger"] = '{"toast": {"type": "success", "message": "Paiement de ' + str(amount) + ' F soumis avec succès!"}}'

    return response


# ==================================================
# 2. VÉRIFICATION AGENT EN TEMPS RÉEL (HTMX)
# ==================================================

@require_POST
def verify_agent(request, token):
    """
    Vérifie l'agent en temps réel lors de la saisie.
    """
    inscription = get_object_or_404(Inscription, public_token=token)

    if not _has_inscription_access(request, inscription):
        response = render(
            request,
            "payments/partials/agent_input.html",
            {"show_error": True, "error": "Accès non autorisé."},
            status=403,
        )
        response["HX-Trigger"] = '{"toast": {"type": "error", "message": "Accès non autorisé."}}'
        return response

    agent_name = request.POST.get("agent_name", "").strip()

    if not agent_name or len(agent_name) < 2:
        response = render(
            request,
            "payments/partials/agent_input.html",
            {"show_error": True, "error": "Veuillez entrer au moins 2 caractères."}
        )
        response["HX-Trigger"] = '{"toast": {"type": "error", "message": "Veuillez entrer au moins 2 caractères."}}'
        return response

    agent, error = verify_agent_and_create_session(inscription, agent_name)

    if error:
        response = render(
            request,
            "payments/partials/agent_input.html",
            {"show_error": True, "error": error}
        )
        response["HX-Trigger"] = '{"toast": {"type": "error", "message": "' + error + '"}}'
        return response

    session = CashPaymentSession.objects.filter(
        inscription=inscription, agent=agent, is_used=False, expires_at__gt=timezone.now()
    ).order_by("-created_at").first()

    response = render(
        request,
        "payments/partials/agent_confirmed.html",
        {"agent": agent, "agent_name": agent_name, "session": session}
    )
    response["HX-Trigger"] = '{"toast": {"type": "success", "message": "Agent vérifié avec succès!"}}'
    return response


# ==================================================
# 3. SESSION ESPÈCES (HTMX)
# ==================================================

@require_POST
def initiate_cash_session(request, token):
    inscription = get_object_or_404(Inscription, public_token=token)

    if not _has_inscription_access(request, inscription):
        return render(
            request,
            "payments/partials/agent_error.html",
            {"error": "Accès non autorisé."},
            status=403,
        )

    agent_name = request.POST.get("agent_name", "").strip()

    agent, error = verify_agent_and_create_session(inscription, agent_name)

    if error:
        return render(request, "payments/partials/agent_error.html", {"error": error}, status=400)

    session = CashPaymentSession.objects.filter(
        inscription=inscription, agent=agent, is_used=False, expires_at__gt=timezone.now()
    ).order_by("-created_at").first()

    return render(request, "payments/partials/agent_session_created.html", {"session": session, "agent": agent})


# ==================================================
# 4. AFFICHAGE REÇU
# ==================================================

def receipt_public_detail(request, receipt_number):
    payment = get_object_or_404(Payment, receipt_number=receipt_number, status="validated")
    inscription = payment.inscription

    return render(request, "payments/receipt_detail.html", {
        "payment": payment,
        "inscription": inscription,
        "candidature": inscription.candidature,
        "programme": inscription.candidature.programme,
    })


# ==================================================
# 5. TÉLÉCHARGEMENT REÇU PDF
# ==================================================

def receipt_pdf(request, receipt_number):
    payment = get_object_or_404(Payment, receipt_number=receipt_number, status="validated")

    if not payment.receipt_pdf:
        raise Http404("Le reçu PDF n'est pas disponible.")

    return FileResponse(payment.receipt_pdf.open("rb"), as_attachment=True, filename=f"recu-{payment.receipt_number}.pdf")


# ==================================================
# 6. API - LISTE AGENTS
# ==================================================

@require_GET
def agents_list(request):
    query = request.GET.get("q", "").strip()

    if len(query) < 2:
        return JsonResponse({"agents": []})

    agents = PaymentAgent.objects.select_related("user").filter(is_active=True).filter(
        Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query) | Q(agent_code__icontains=query)
    )[:10]

    return JsonResponse({"agents": [{"id": a.id, "name": a.user.get_full_name(), "code": a.agent_code} for a in agents]})


# ==================================================
# 7. API - STATUT PAIEMENT
# ==================================================

@require_GET
def payment_status(request, token):
    inscription = get_object_or_404(Inscription, public_token=token)

    if not _has_inscription_access(request, inscription):
        return JsonResponse({"error": "Accès non autorisé."}, status=403)

    payments = inscription.payments.order_by("-paid_at")
    latest_payment = payments.first()

    return JsonResponse({
        "inscription_status": inscription.status,
        "amount_paid": inscription.amount_paid,
        "amount_due": inscription.amount_due,
        "balance": inscription.balance,
        "has_pending_payment": payments.filter(status="pending").exists(),
        "can_pay": _can_initiate_payment(inscription, payments.filter(status="pending").exists()),
        "latest_payment": {
            "status": latest_payment.status, "amount": latest_payment.amount,
            "method": latest_payment.method, "receipt_number": latest_payment.receipt_number
        } if latest_payment else None,
    })


# ==================================================
# 8. REFRESH FINANCIER (HTMX)
# ==================================================

@require_GET
def refresh_finance(request, token):
    inscription = get_object_or_404(Inscription, public_token=token)

    if not _has_inscription_access(request, inscription):
        raise Http404("Accès non autorisé.")

    payments = inscription.payments.order_by("-paid_at")
    has_pending_payment = payments.filter(status="pending").exists()
    can_pay = _can_initiate_payment(inscription, has_pending_payment)
    payment_form = StudentPaymentForm(inscription=inscription) if can_pay else None

    return render(
        request,
        "payments/partials/inscription_finance.html",
        {
            "inscription": inscription,
            "candidature": inscription.candidature,
            "programme": inscription.candidature.programme,
            "payments": payments,
            "can_pay": can_pay,
            "has_pending_payment": has_pending_payment,
            "payment_form": payment_form,
        }
    )
