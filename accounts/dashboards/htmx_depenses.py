import json
from calendar import monthrange
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.forms import BranchBankTransferForm, BranchExpenseForm, BranchMonthlyClosureForm, DonationForm
from accounts.models import BranchBankTransfer, BranchCashMovement, BranchExpense, BranchMonthlyClosure, Donation
from accounts.services.accounting_documents import (
    create_cash_movement,
    ensure_expense_reference,
)
from accounts.services.financial_integrity import assert_financial_period_open
from accounts.services.manager_intelligence import (
    branch_financial_orphan_report,
    get_branch_cash_balance,
    lock_branch_cash_balance,
    sync_bank_transfer_cash_movement,
    sync_donation_cash_movement,
)
from accounts.services.wallets import (
    configured_wallet_for_category,
    consume_wallet_for_cash_movement,
    wallet_balance,
)

from accounts.dashboards.htmx_utils import (
    manager_closure_redirect_response,
    manager_required,
    manager_section_notice_redirect_response,
    manager_section_redirect_response,
)


@manager_required
@require_POST
def expense_create(request: HttpRequest) -> HttpResponse:
    form = BranchExpenseForm(request.POST, request.FILES)
    if not form.is_valid():
        response = render(
            request,
            "accounts/dashboard/partials/manager_expense_form.html",
            {"expense_form": form},
        )
        response.status_code = 400
        return response

    try:
        assert_financial_period_open(request.branch, form.cleaned_data["expense_date"])
    except ValidationError as exc:
        return HttpResponse(" ".join(exc.messages), status=400)
    expense = form.save(commit=False)
    expense.branch = request.branch
    expense.created_by = request.user
    expense.status = BranchExpense.STATUS_SUBMITTED
    expense.save()
    ensure_expense_reference(expense)
    return manager_section_redirect_response("depenses")


@manager_required
@require_POST
def expense_approve(request: HttpRequest, pk: int) -> HttpResponse:
    expense = get_object_or_404(BranchExpense, pk=pk, branch=request.branch)
    if not expense.can_be_approved:
        return HttpResponse("Cette depense ne peut pas etre approuvee.", status=400)
    expense.status = BranchExpense.STATUS_APPROVED
    expense.approved_by = request.user
    expense.approved_at = timezone.now()
    expense.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return manager_section_redirect_response("depenses")


@manager_required
@require_POST
def expense_reject(request: HttpRequest, pk: int) -> HttpResponse:
    expense = get_object_or_404(BranchExpense, pk=pk, branch=request.branch)
    if expense.status == BranchExpense.STATUS_PAID:
        return HttpResponse("Une depense deja payee ne peut pas etre rejetee.", status=400)
    expense.status = BranchExpense.STATUS_REJECTED
    expense.save(update_fields=["status", "updated_at"])
    return manager_section_redirect_response("depenses")


@manager_required
@require_POST
def expense_pay(request: HttpRequest, pk: int) -> HttpResponse:
    with transaction.atomic():
        _locked_branch, available_cash = lock_branch_cash_balance(request.branch)
        expense = get_object_or_404(
            BranchExpense.objects.select_for_update(),
            pk=pk,
            branch=request.branch,
        )
        try:
            assert_financial_period_open(request.branch, expense.expense_date)
        except ValidationError as exc:
            return HttpResponse(" ".join(exc.messages), status=400)
        if not expense.can_be_paid:
            return HttpResponse("Cette depense doit etre approuvee avant paiement.", status=400)
        if expense.amount > available_cash:
            return HttpResponse(
                (
                    "<div class='rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700'>"
                    f"Caisse insuffisante pour payer cette depense. Disponible: {available_cash} FCFA."
                    "</div>"
                ),
                status=400,
            )
        expense_wallet = configured_wallet_for_category(request.branch, "expense")
        if expense_wallet and expense.amount > wallet_balance(expense_wallet):
            return HttpResponse(
                (
                    "<div class='rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700'>"
                    f"La mini-caisse Dépenses est insuffisante. Disponible : {wallet_balance(expense_wallet)} FCFA."
                    "</div>"
                ),
                status=400,
            )
        expense.status = BranchExpense.STATUS_PAID
        expense.paid_by = request.user
        expense.paid_at = timezone.now()
        expense.save(update_fields=["status", "paid_by", "paid_at", "updated_at"])
        ensure_expense_reference(expense)
        cash_movement = create_cash_movement(
            branch=request.branch,
            movement_type=BranchCashMovement.TYPE_OUT,
            source=BranchCashMovement.SOURCE_EXPENSE,
            amount=expense.amount,
            label=expense.title,
            movement_date=expense.expense_date,
            expense=expense,
            source_reference=expense.reference,
            notes=expense.notes,
            created_by=request.user,
        )
        if expense_wallet:
            consume_wallet_for_cash_movement(
                wallet=expense_wallet,
                cash_movement=cash_movement,
                actor=request.user,
                label="Paiement de dépense",
                notes=expense.reference,
            )
    response = manager_section_redirect_response("depenses")
    response["HX-Trigger"] = json.dumps({"cashBalanceUpdated": True, "dashboardStatsUpdated": True})
    return response


@manager_required
@require_POST
def monthly_closure_create(request: HttpRequest) -> HttpResponse:
    closure_form = BranchMonthlyClosureForm(request.POST)
    available_cash_balance = get_branch_cash_balance(request.branch)
    suggested_transfer_amount = max(available_cash_balance - request.branch.cash_reserve_target, 0)
    if not closure_form.is_valid():
        response = render(
            request,
            "accounts/dashboard/partials/monthly_closure_form.html",
            {
                "closure_form": closure_form,
                "transfer_form": BranchBankTransferForm(request.POST, request.FILES),
                "available_cash_balance": available_cash_balance,
                "cash_reserve_target": request.branch.cash_reserve_target,
                "suggested_transfer_amount": suggested_transfer_amount,
                "closure_error": "Verifiez les champs du formulaire de cloture.",
            },
        )
        response.status_code = 400
        return response

    period_month = closure_form.cleaned_data["period_month"]
    transfer_amount = closure_form.cleaned_data["bank_transfer_amount"] or 0

    orphan_report = branch_financial_orphan_report(request.branch, period_month)
    if any(orphan_report.values()):
        response = render(
            request,
            "accounts/dashboard/partials/monthly_closure_form.html",
            {
                "closure_form": closure_form,
                "transfer_form": BranchBankTransferForm(request.POST, request.FILES),
                "available_cash_balance": available_cash_balance,
                "cash_reserve_target": request.branch.cash_reserve_target,
                "suggested_transfer_amount": suggested_transfer_amount,
                "closure_error": _format_financial_orphan_message(orphan_report),
                "report_closure_blockers": [_format_financial_orphan_message(orphan_report)],
            },
        )
        response.status_code = 400
        return response

    existing_closure = BranchMonthlyClosure.objects.filter(
        branch=request.branch, period_month=period_month,
    ).first()
    if existing_closure and existing_closure.status != BranchMonthlyClosure.STATUS_DRAFT:
        response = render(
            request,
            "accounts/dashboard/partials/monthly_closure_form.html",
            {
                "closure_form": closure_form,
                "transfer_form": BranchBankTransferForm(request.POST, request.FILES),
                "available_cash_balance": get_branch_cash_balance(request.branch),
                "closure_error": "Cette periode est deja validee ou cloturee. Elle ne peut plus etre modifiee.",
            },
        )
        response.status_code = 400
        return response

    period_end = date(period_month.year, period_month.month, monthrange(period_month.year, period_month.month)[1])
    report_movements = BranchCashMovement.objects.filter(
        branch=request.branch,
        movement_date__gte=period_month,
        movement_date__lte=period_end,
    )
    total_entries = report_movements.filter(movement_type=BranchCashMovement.TYPE_IN).aggregate(total=Sum("amount"))["total"] or 0
    total_exits = report_movements.filter(movement_type=BranchCashMovement.TYPE_OUT).aggregate(total=Sum("amount"))["total"] or 0
    student_revenue = report_movements.filter(
        movement_type=BranchCashMovement.TYPE_IN,
        source=BranchCashMovement.SOURCE_STUDENT_PAYMENT,
    ).aggregate(total=Sum("amount"))["total"] or 0
    shop_revenue = report_movements.filter(
        movement_type=BranchCashMovement.TYPE_IN,
        source=BranchCashMovement.SOURCE_SHOP,
    ).aggregate(total=Sum("amount"))["total"] or 0
    salary_paid = report_movements.filter(
        movement_type=BranchCashMovement.TYPE_OUT,
        source=BranchCashMovement.SOURCE_PAYROLL,
    ).aggregate(total=Sum("amount"))["total"] or 0
    honorarium_paid = report_movements.filter(
        movement_type=BranchCashMovement.TYPE_OUT,
        source=BranchCashMovement.SOURCE_HONORARIUM,
    ).aggregate(total=Sum("amount"))["total"] or 0
    expenses_paid = report_movements.filter(
        movement_type=BranchCashMovement.TYPE_OUT,
        source=BranchCashMovement.SOURCE_EXPENSE,
    ).aggregate(total=Sum("amount"))["total"] or 0
    result_amount = total_entries - total_exits
    transfer_form = BranchBankTransferForm(request.POST, request.FILES)
    transfer_is_valid = True
    if transfer_amount > 0:
        transfer_is_valid = transfer_form.is_valid()
        if transfer_is_valid:
            required_transfer_fields = [
                transfer_form.cleaned_data.get("bank_name"),
                transfer_form.cleaned_data.get("reference"),
                transfer_form.cleaned_data.get("transfer_date"),
            ]
            if not all(required_transfer_fields):
                transfer_is_valid = False
    if not transfer_is_valid:
        response = render(
            request,
            "accounts/dashboard/partials/monthly_closure_form.html",
            {
                "closure_form": closure_form,
                "transfer_form": transfer_form,
                "available_cash_balance": available_cash_balance,
                "cash_reserve_target": request.branch.cash_reserve_target,
                "suggested_transfer_amount": suggested_transfer_amount,
                "closure_error": "Verifiez les champs du versement bancaire.",
            },
        )
        response.status_code = 400
        return response

    with transaction.atomic():
        _locked_branch, locked_cash_balance = lock_branch_cash_balance(request.branch)
        if transfer_amount > locked_cash_balance:
            response = render(
                request,
                "accounts/dashboard/partials/monthly_closure_form.html",
                {
                    "closure_form": closure_form,
                    "transfer_form": transfer_form,
                    "available_cash_balance": locked_cash_balance,
                    "cash_reserve_target": request.branch.cash_reserve_target,
                    "suggested_transfer_amount": max(
                        locked_cash_balance - request.branch.cash_reserve_target,
                        0,
                    ),
                    "closure_error": (
                        "Le versement bancaire depasse la caisse disponible "
                        f"({locked_cash_balance} FCFA)."
                    ),
                },
            )
            response.status_code = 400
            return response
        closure, _ = BranchMonthlyClosure.objects.update_or_create(
            branch=request.branch,
            period_month=period_month,
            defaults={
                "total_entries": total_entries,
                "total_exits": total_exits,
                "student_revenue": student_revenue,
                "shop_revenue": shop_revenue,
                "salary_paid": salary_paid,
                "honorarium_paid": honorarium_paid,
                "expenses_paid": expenses_paid,
                "result_amount": result_amount,
                "bank_transfer_amount": transfer_amount,
                "status": BranchMonthlyClosure.STATUS_DRAFT,
                "notes": closure_form.cleaned_data.get("notes", ""),
                "created_by": request.user,
            },
        )
        if transfer_amount > 0:
            transfer, _ = BranchBankTransfer.objects.update_or_create(
                closure=closure,
                defaults={
                    "branch": request.branch,
                    "bank_name": transfer_form.cleaned_data["bank_name"],
                    "reference": transfer_form.cleaned_data["reference"],
                    "transfer_date": transfer_form.cleaned_data["transfer_date"],
                    "amount": transfer_amount,
                    "comment": transfer_form.cleaned_data.get("comment", ""),
                    "created_by": request.user,
                },
            )
            if transfer_form.cleaned_data.get("proof"):
                transfer.proof = transfer_form.cleaned_data["proof"]
                transfer.save(update_fields=["proof", "updated_at"])
            sync_bank_transfer_cash_movement(transfer, user=request.user)

    return manager_closure_redirect_response(period_month)


@manager_required
@require_POST
def monthly_closure_validate(request: HttpRequest, pk: int) -> HttpResponse:
    closure = get_object_or_404(BranchMonthlyClosure, pk=pk, branch=request.branch)
    if closure.status != BranchMonthlyClosure.STATUS_DRAFT:
        return manager_section_notice_redirect_response("cloture", "cloture_non_brouillon")
    orphan_report = branch_financial_orphan_report(request.branch, closure.period_month)
    if any(orphan_report.values()):
        return HttpResponse(_format_financial_orphan_message(orphan_report), status=400)
    if get_branch_cash_balance(request.branch) < 0:
        return HttpResponse("Cloture impossible: la caisse de l'annexe est negative.", status=400)

    closure.status = BranchMonthlyClosure.STATUS_VALIDATED
    closure.validated_by = request.user
    closure.validated_at = timezone.now()
    closure.save(update_fields=["status", "validated_by", "validated_at", "updated_at"])

    return manager_closure_redirect_response(closure.period_month)


@manager_required
@require_POST
def monthly_closure_close(request: HttpRequest, pk: int) -> HttpResponse:
    closure = get_object_or_404(BranchMonthlyClosure, pk=pk, branch=request.branch)
    if closure.status != BranchMonthlyClosure.STATUS_VALIDATED:
        return manager_section_notice_redirect_response("cloture", "cloture_non_validee")
    orphan_report = branch_financial_orphan_report(request.branch, closure.period_month)
    if any(orphan_report.values()):
        return HttpResponse(_format_financial_orphan_message(orphan_report), status=400)
    if get_branch_cash_balance(request.branch) < 0:
        return HttpResponse("Cloture impossible: la caisse de l'annexe est negative.", status=400)

    closure.status = BranchMonthlyClosure.STATUS_CLOSED
    closure.closed_at = timezone.now()
    closure.save(update_fields=["status", "closed_at", "updated_at"])

    return manager_closure_redirect_response(closure.period_month)


@manager_required
@require_POST
def donation_create(request: HttpRequest) -> HttpResponse:
    form = DonationForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "accounts/dashboard/partials/donation_form.html",
            {"donation_form": form},
        )

    with transaction.atomic():
        donation = form.save(commit=False)
        donation.branch = request.branch
        donation.created_by = request.user
        donation.save()
        sync_donation_cash_movement(donation, user=request.user)

    response = render(
        request,
        "accounts/dashboard/partials/donation_row.html",
        {"donation": donation},
    )
    response["HX-Trigger"] = json.dumps({
        "cashBalanceUpdated": True, "dashboardStatsUpdated": True,
        "showToast": {"message": f"Don de {donation.donor_name} enregistre ({donation.amount:,} FCFA).", "type": "success"},
    })
    return response


def _format_financial_orphan_message(orphan_report: dict[str, list]) -> str:
    labels = {
        "payments": "paiement(s) etudiant valide(s) sans mouvement de caisse",
        "shop_payments": "paiement(s) boutique valide(s) sans mouvement de caisse",
        "donations": "don(s) sans mouvement de caisse",
        "expenses": "depense(s) payee(s) sans mouvement de caisse",
        "payroll_entries": "fiche(s) de paie payee(s) ou partielle(s) sans mouvement de caisse",
        "honorarium_entries": "honoraire(s) enseignant(s) paye(s) ou partiel(s) sans mouvement de caisse",
        "bank_transfers": "versement(s) bancaire(s) sans mouvement de sortie",
    }
    pieces = [
        f"{len(items)} {labels[key]}"
        for key, items in orphan_report.items()
        if items
    ]
    return "Cloture bloquee : " + "; ".join(pieces) + "."
