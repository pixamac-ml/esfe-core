import json
from datetime import date

from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseNotFound
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.dashboards.htmx_utils import manager_required, manager_honorarium_redirect_response, manager_salary_redirect_response
from accounts.models import PaymentSignatureSession, PayrollEntry, TeacherHonorariumEntry
from accounts.services.payment_signatures import (
    complete_payment,
    get_session_for_token,
    initiate_payment_signature,
    save_signature,
)


def _error(message, status=400):
    return HttpResponse(f"<div class='rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700'>{message}</div>", status=status)


@manager_required
@require_POST
def payment_signature_start(request, payment_type, pk):
    if payment_type == PaymentSignatureSession.TYPE_PAYROLL:
        entry = PayrollEntry.objects.select_related("employee", "branch").filter(pk=pk, branch=request.branch).first()
        remaining = entry.remaining_salary if entry else 0
    elif payment_type == PaymentSignatureSession.TYPE_HONORARIUM:
        entry = TeacherHonorariumEntry.objects.select_related("teacher", "branch").filter(pk=pk, branch=request.branch).first()
        remaining = entry.remaining_amount if entry else 0
    else:
        return _error("Type de paiement inconnu.", 404)
    if entry is None:
        return _error("Fiche introuvable.", 404)
    try:
        amount = int((request.POST.get("payment_amount") or "").strip())
        session, _raw = initiate_payment_signature(
            branch=request.branch, payment_type=payment_type, entry=entry,
            amount=amount, actor=request.user, base_url="",
        )
    except (ValueError, ValidationError) as exc:
        return _error(" ".join(exc.messages) if isinstance(exc, ValidationError) else "Montant invalide.")
    response = render(request, "accounts/dashboard/partials/payment_signature_started.html", {
        "session": session,
        "tablet_link": getattr(session, "_tablet_link", ""),
        "expires_minutes": max(1, int((session.expires_at - timezone.now()).total_seconds() // 60)),
    })
    response["HX-Trigger"] = json.dumps({"showToast": {"message": "Lien de signature créé. Faites signer le bénéficiaire sur la tablette.", "type": "info"}})
    return response


@require_GET
def payment_signature_tablet(request, token):
    session = get_session_for_token(token)
    if session is None:
        return HttpResponseNotFound("Lien de signature introuvable ou expiré.")
    return render(request, "accounts/payment_signature_tablet.html", {"session": session, "token": token})


@require_POST
def payment_signature_tablet_submit(request, token):
    session = get_session_for_token(token)
    if session is None:
        return HttpResponseNotFound("Lien de signature introuvable ou expiré.")
    try:
        save_signature(session=session, signature_data=request.POST.get("signature_data", ""), request=request)
    except ValidationError as exc:
        return render(request, "accounts/payment_signature_tablet.html", {"session": session, "token": token, "error": " ".join(exc.messages)}, status=400)
    return render(request, "accounts/payment_signature_tablet.html", {"session": session, "token": token})


@manager_required
@require_POST
def payment_signature_approve(request, pk):
    try:
        session, created = complete_payment(session_id=pk, branch=request.branch, approver=request.user)
    except (PaymentSignatureSession.DoesNotExist, ValidationError) as exc:
        message = "Session de paiement introuvable." if isinstance(exc, PaymentSignatureSession.DoesNotExist) else " ".join(exc.messages)
        return _error(message)
    period_month = date.fromisoformat(session.snapshot["period_month"])
    if session.payment_type == PaymentSignatureSession.TYPE_PAYROLL:
        response = manager_salary_redirect_response(period_month)
    else:
        response = manager_honorarium_redirect_response(period_month)
    response["HX-Trigger"] = json.dumps({"cashBalanceUpdated": True, "dashboardStatsUpdated": True, "showToast": {"message": "Paiement approuvé, enregistré et notifié au bénéficiaire.", "type": "success"}})
    return response
