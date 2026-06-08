import json

from django.db import transaction
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.forms import BranchCashMovementForm
from accounts.models import BranchCashMovement
from accounts.services.accounting_documents import (
    create_cash_movement,
    ensure_cash_movement_receipt,
    finalize_cash_movement_document,
)
from accounts.services.manager_intelligence import (
    payment_cash_reference,
    sync_student_payment_cash_movements,
)
from inscriptions.models import Inscription
from payments.models import CashPaymentSession, FinancialLog, Payment, PaymentAgent

from accounts.dashboards.htmx_utils import (
    PAYABLE_INSCRIPTION_STATUSES,
    get_active_cash_session,
    get_current_agent,
    manager_required,
    manager_section_notice_redirect_response,
    manager_section_redirect_response,
)


@manager_required
@require_POST
def cash_session_create(request: HttpRequest, pk: int) -> HttpResponse:
    inscription = get_object_or_404(
        Inscription.objects.select_related(
            "candidature",
            "candidature__programme",
            "candidature__branch",
        ),
        pk=pk,
        candidature__branch=request.branch,
    )
    manager_agent = get_current_agent(request.user, request.branch)
    if not manager_agent:
        return HttpResponse(
            "<div class='rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700'>Aucun profil PaymentAgent actif n'est attribue a cette gestionnaire.</div>",
            status=403,
        )
    if inscription.status not in PAYABLE_INSCRIPTION_STATUSES or inscription.balance <= 0:
        return HttpResponse(
            "<div class='rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700'>Cette inscription n'est pas payable en l'etat.</div>",
            status=400,
        )

    existing_session = get_active_cash_session(inscription)
    if existing_session:
        return render(
            request,
            "accounts/dashboard/partials/manager_cash_session_card.html",
            {
                "session": existing_session,
                "manager_agent": manager_agent,
                "show_existing_notice": True,
            },
        )

    with transaction.atomic():
        session = CashPaymentSession.objects.create(
            inscription=inscription,
            agent=manager_agent,
            verification_code="000000",
            expires_at=timezone.now(),
        )
        session.generate_code()

    return render(
        request,
        "accounts/dashboard/partials/manager_cash_session_card.html",
        {
            "session": session,
            "manager_agent": manager_agent,
            "show_created_notice": True,
        },
    )


@manager_required
@require_POST
def cash_session_regenerate(request: HttpRequest, pk: int) -> HttpResponse:
    manager_agent = get_current_agent(request.user, request.branch)
    if not manager_agent:
        return HttpResponse("Aucun agent actif.", status=403)
    session = get_object_or_404(
        CashPaymentSession.objects.select_related(
            "agent__user",
            "inscription",
            "inscription__candidature",
            "inscription__candidature__programme",
        ),
        pk=pk,
        agent=manager_agent,
        is_used=False,
    )
    session.generate_code()
    return render(
        request,
        "accounts/dashboard/partials/manager_cash_session_card.html",
        {
            "session": session,
            "manager_agent": manager_agent,
            "show_regenerated_notice": True,
        },
    )


@manager_required
@require_POST
def cash_session_complete(request: HttpRequest, pk: int) -> HttpResponse:
    manager_agent = get_current_agent(request.user, request.branch)
    if not manager_agent:
        return HttpResponse("Aucun agent actif.", status=403)
    session = get_object_or_404(
        CashPaymentSession.objects.select_related(
            "inscription",
            "inscription__candidature",
            "inscription__candidature__programme",
        ),
        pk=pk,
        agent=manager_agent,
        is_used=False,
    )
    if timezone.now() > session.expires_at:
        session.is_used = True
        session.save(update_fields=["is_used"])
        return HttpResponse(
            "<div class='rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700'>Le code a expire. Regenerer une nouvelle session.</div>",
            status=400,
        )

    raw_amount = (request.POST.get("amount") or "").strip()
    try:
        amount = int(raw_amount)
    except (TypeError, ValueError):
        amount = 0
    if amount <= 0:
        return HttpResponse(
            "<div class='rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700'>Le montant saisi est invalide.</div>",
            status=400,
        )
    if amount > session.inscription.balance:
        return HttpResponse(
            "<div class='rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700'>Le montant depasse le solde restant de l'inscription.</div>",
            status=400,
        )

    with transaction.atomic():
        payment = Payment.objects.create(
            inscription=session.inscription,
            amount=amount,
            method=Payment.METHOD_CASH,
            status=Payment.STATUS_VALIDATED,
            paid_at=timezone.now(),
            agent=manager_agent,
            cash_session=session,
        )
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
            action=FinancialLog.ACTION_PAYMENT_CREATED,
            new_amount=payment.amount,
            reason="Paiement espece cree et valide depuis le dashboard gestionnaire.",
            actor=request.user,
            metadata={"payment_reference": payment.reference, "inscription_id": payment.inscription_id},
        )
        session.is_used = True
        session.save(update_fields=["is_used"])

    response = render(
        request,
        "accounts/dashboard/partials/cash_session_completed.html",
        {"session": session, "payment": payment},
    )
    response["HX-Trigger"] = json.dumps({
        "cashBalanceUpdated": True, "paymentUpdated": True, "dashboardStatsUpdated": True,
        "showToast": {"message": f"Paiement de {payment.amount:,} FCFA encaisse.", "type": "success"},
    })
    return response


@manager_required
@require_POST
def cash_session_cancel(request: HttpRequest, pk: int) -> HttpResponse:
    manager_agent = get_current_agent(request.user, request.branch)
    if not manager_agent:
        return HttpResponse("Aucun agent actif.", status=403)
    session = get_object_or_404(
        CashPaymentSession,
        pk=pk,
        agent=manager_agent,
        is_used=False,
    )
    session.is_used = True
    session.save(update_fields=["is_used"])
    return HttpResponse("")


@manager_required
@require_POST
def cash_movement_create(request: HttpRequest) -> HttpResponse:
    form = BranchCashMovementForm(request.POST)
    if not form.is_valid():
        response = render(
            request,
            "accounts/dashboard/partials/manager_cash_movement_form.html",
            {"cash_form": form},
        )
        response.status_code = 400
        return response

    movement = form.save(commit=False)
    movement.branch = request.branch
    movement.created_by = request.user
    movement.save()
    finalize_cash_movement_document(movement)
    response = manager_section_redirect_response("caisse")
    response["HX-Trigger"] = json.dumps({"cashBalanceUpdated": True, "dashboardStatsUpdated": True})
    return response


@manager_required
@require_POST
def cash_sync(request: HttpRequest) -> HttpResponse:
    result = sync_student_payment_cash_movements(request.branch, request.user)
    response = manager_section_notice_redirect_response(
        "caisse",
        f"caisse_sync_{result['created']}",
    )
    response["HX-Trigger"] = json.dumps({"cashBalanceUpdated": True, "dashboardStatsUpdated": True})
    return response


@manager_required
@require_GET
def cash_movement_receipt(request: HttpRequest, pk: int) -> FileResponse:
    movement = get_object_or_404(
        BranchCashMovement,
        pk=pk,
        branch=request.branch,
    )
    ensure_cash_movement_receipt(movement)
    if not movement.receipt_pdf:
        raise Http404("Piece de caisse indisponible.")
    return FileResponse(
        movement.receipt_pdf.open("rb"),
        as_attachment=True,
        filename=f"piece-caisse-{movement.receipt_number or movement.reference}.pdf",
    )
