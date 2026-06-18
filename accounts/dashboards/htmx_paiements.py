import json

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.models import BranchCashMovement, SensitiveActionRequest
from payments.models import FinancialLog, Payment

from accounts.services.accounting_documents import create_cash_movement
from accounts.services.manager_intelligence import payment_cash_reference
from accounts.services.sensitive_actions import (
    SensitiveActionError,
    confirm_sensitive_action,
    request_sensitive_action,
)
from payments.services.corrections import correct_validated_payment_amount, financial_logs_for_payment

from accounts.dashboards.htmx_utils import manager_required


@manager_required
@require_GET
def payment_detail(request: HttpRequest, pk: int) -> HttpResponse:
    payment = get_object_or_404(
        Payment.objects.select_related(
            "inscription__candidature",
            "inscription__candidature__programme",
            "agent__user",
            "cash_session",
            "cash_session__agent__user",
        ),
        pk=pk,
        inscription__candidature__branch=request.branch,
    )
    return render(
        request,
        "accounts/dashboard/partials/payment_modal.html",
        {
            "payment": payment,
            "financial_logs": financial_logs_for_payment(payment)[:20],
            "corrections": payment.corrections.select_related("corrected_by").all()[:10],
        },
    )


@manager_required
@require_POST
def payment_correct(request: HttpRequest, pk: int) -> HttpResponse:
    payment = get_object_or_404(
        Payment.objects.select_related(
            "inscription",
            "inscription__candidature",
            "inscription__candidature__branch",
        ),
        pk=pk,
        inscription__candidature__branch=request.branch,
        status=Payment.STATUS_VALIDATED,
    )
    raw_amount = (request.POST.get("new_amount") or "").strip()
    reason = (request.POST.get("reason") or "").strip()
    confirmation = (request.POST.get("confirmation") or "").strip().upper()

    try:
        new_amount = int(raw_amount)
    except (TypeError, ValueError):
        new_amount = 0

    if confirmation != "CORRIGER":
        response = render(
            request,
            "accounts/dashboard/partials/payment_modal.html",
            {
                "payment": payment,
                "financial_logs": financial_logs_for_payment(payment)[:20],
                "corrections": payment.corrections.select_related("corrected_by").all()[:10],
                "correction_error": "Tapez CORRIGER pour confirmer l'operation.",
                "correction_new_amount": raw_amount,
                "correction_reason": reason,
            },
        )
        response.status_code = 400
        return response

    try:
        otp_request = request_sensitive_action(
            branch=request.branch,
            action_type=SensitiveActionRequest.ACTION_PAYMENT_EDIT,
            target_model="Payment",
            target_id=payment.pk,
            previous_state={"amount": payment.amount},
            requested_state={"amount": new_amount},
            requested_by=request.user,
            reason=reason,
        )
    except SensitiveActionError as exc:
        response = render(
            request,
            "accounts/dashboard/partials/payment_modal.html",
            {
                "payment": payment,
                "financial_logs": financial_logs_for_payment(payment)[:20],
                "corrections": payment.corrections.select_related("corrected_by").all()[:10],
                "correction_error": str(exc),
                "correction_new_amount": raw_amount,
                "correction_reason": reason,
            },
        )
        response.status_code = 400
        return response

    response = render(
        request,
        "accounts/dashboard/partials/payment_modal.html",
        {
            "payment": payment,
            "financial_logs": financial_logs_for_payment(payment)[:20],
            "corrections": payment.corrections.select_related("corrected_by").all()[:10],
            "otp_request_id": otp_request.pk,
            "otp_new_amount": new_amount,
            "otp_reason": reason,
            "otp_validity_minutes": SensitiveActionRequest.OTP_VALIDITY_MINUTES,
        },
    )
    response["HX-Trigger"] = json.dumps({
        "showToast": {
            "message": "Code de validation envoye au DG et a la DGA. Saisissez-le pour confirmer.",
            "type": "info",
        },
    })
    return response


@manager_required
@require_POST
def payment_correct_confirm_otp(request: HttpRequest, pk: int) -> HttpResponse:
    payment = get_object_or_404(
        Payment.objects.select_related(
            "inscription",
            "inscription__candidature",
            "inscription__candidature__branch",
        ),
        pk=pk,
        inscription__candidature__branch=request.branch,
        status=Payment.STATUS_VALIDATED,
    )
    otp_request_id = request.POST.get("otp_request_id")
    otp_code = (request.POST.get("otp_code") or "").strip()

    def _apply(otp_request):
        new_amount = otp_request.requested_state.get("amount")
        correct_validated_payment_amount(
            payment=payment,
            new_amount=new_amount,
            reason=otp_request.reason,
            actor=otp_request.requested_by,
        )
        payment.refresh_from_db()
        return {"amount": payment.amount}

    try:
        confirm_sensitive_action(
            request_id=otp_request_id,
            code=otp_code,
            approver=request.user,
            apply_callback=_apply,
        )
    except (SensitiveActionError, ValidationError, SensitiveActionRequest.DoesNotExist) as exc:
        message = " ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
        payment.refresh_from_db()
        response = render(
            request,
            "accounts/dashboard/partials/payment_modal.html",
            {
                "payment": payment,
                "financial_logs": financial_logs_for_payment(payment)[:20],
                "corrections": payment.corrections.select_related("corrected_by").all()[:10],
                "otp_request_id": otp_request_id,
                "otp_error": message,
            },
        )
        response.status_code = 400
        return response

    payment.refresh_from_db()
    response = render(
        request,
        "accounts/dashboard/partials/payment_modal.html",
        {
            "payment": payment,
            "financial_logs": financial_logs_for_payment(payment)[:20],
            "corrections": payment.corrections.select_related("corrected_by").all()[:10],
            "correction_success": "Correction validee par le DG/DGA et caisse synchronisee.",
        },
    )
    response["HX-Trigger"] = json.dumps({
        "paymentUpdated": True, "cashBalanceUpdated": True, "dashboardStatsUpdated": True,
        "showToast": {"message": "Paiement corrige avec tracabilite.", "type": "success"},
    })
    return response


@manager_required
@require_POST
def payment_validate(request: HttpRequest, pk: int) -> HttpResponse:
    payment = get_object_or_404(
        Payment,
        pk=pk,
        inscription__candidature__branch=request.branch,
        status=Payment.STATUS_PENDING,
    )
    payment.status = Payment.STATUS_VALIDATED
    payment.paid_at = timezone.now()
    payment.save()
    existing_movement = BranchCashMovement.objects.filter(
        branch=request.branch,
        source=BranchCashMovement.SOURCE_STUDENT_PAYMENT,
        source_reference=payment_cash_reference(payment),
    ).first()
    if not existing_movement:
        create_cash_movement(
            branch=request.branch,
            source=BranchCashMovement.SOURCE_STUDENT_PAYMENT,
            source_reference=payment_cash_reference(payment),
            movement_type=BranchCashMovement.TYPE_IN,
            amount=payment.amount,
            label=f"Paiement etudiant - {payment.inscription.candidature.full_name}",
            movement_date=payment.paid_at.date(),
            notes=f"Synchronisation automatique paiement #{payment.pk}.",
            created_by=request.user,
        )
    FinancialLog.objects.create(
        branch=request.branch,
        payment=payment,
        action=FinancialLog.ACTION_PAYMENT_VALIDATED,
        new_amount=payment.amount,
        reason="Validation du paiement par la gestionnaire.",
        actor=request.user,
        metadata={"payment_reference": payment.reference, "inscription_id": payment.inscription_id},
    )
    payment.refresh_from_db()
    response = render(
        request,
        "accounts/dashboard/partials/manager_payment_row.html",
        {"payment": payment},
    )
    response["HX-Trigger"] = json.dumps({
        "paymentUpdated": True, "cashBalanceUpdated": True, "dashboardStatsUpdated": True,
        "showToast": {"message": "Paiement valide et caisse creditee.", "type": "success"},
    })
    return response


@manager_required
@require_POST
def payment_cancel(request: HttpRequest, pk: int) -> HttpResponse:
    payment = get_object_or_404(
        Payment,
        pk=pk,
        inscription__candidature__branch=request.branch,
        status=Payment.STATUS_PENDING,
    )
    payment.status = Payment.STATUS_CANCELLED
    payment.save()
    payment.inscription.update_financial_state()
    FinancialLog.objects.create(
        branch=request.branch,
        payment=payment,
        action=FinancialLog.ACTION_PAYMENT_CANCELLED,
        old_amount=payment.amount,
        delta_amount=-payment.amount,
        reason="Annulation du paiement en attente par la gestionnaire.",
        actor=request.user,
        metadata={"payment_reference": payment.reference, "inscription_id": payment.inscription_id},
    )
    payment.refresh_from_db()
    response = render(
        request,
        "accounts/dashboard/partials/manager_payment_row.html",
        {"payment": payment},
    )
    response["HX-Trigger"] = json.dumps({
        "paymentUpdated": True, "cashBalanceUpdated": True, "dashboardStatsUpdated": True,
        "showToast": {"message": "Paiement annule.", "type": "warning"},
    })
    return response
