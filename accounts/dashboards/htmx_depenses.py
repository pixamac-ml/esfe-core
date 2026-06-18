import json
from calendar import monthrange
from datetime import date

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
    ensure_cash_movement_receipt,
    ensure_expense_reference,
    finalize_cash_movement_document,
)
from accounts.services.manager_intelligence import get_branch_cash_balance

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
        expense = get_object_or_404(
            BranchExpense.objects.select_for_update(),
            pk=pk,
            branch=request.branch,
        )
        if not expense.can_be_paid:
            return HttpResponse("Cette depense doit etre approuvee avant paiement.", status=400)
        expense.status = BranchExpense.STATUS_PAID
        expense.paid_by = request.user
        expense.paid_at = timezone.now()
        expense.save(update_fields=["status", "paid_by", "paid_at", "updated_at"])
        ensure_expense_reference(expense)
        create_cash_movement(
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
    response = manager_section_redirect_response("depenses")
    response["HX-Trigger"] = json.dumps({"cashBalanceUpdated": True, "dashboardStatsUpdated": True})
    return response


@manager_required
@require_POST
def monthly_closure_create(request: HttpRequest) -> HttpResponse:
    closure_form = BranchMonthlyClosureForm(request.POST)
    if not closure_form.is_valid():
        response = render(
            request,
            "accounts/dashboard/partials/monthly_closure_form.html",
            {
                "closure_form": closure_form,
                "transfer_form": BranchBankTransferForm(request.POST, request.FILES),
                "available_cash_balance": get_branch_cash_balance(request.branch),
                "closure_error": "Verifiez les champs du formulaire de cloture.",
            },
        )
        response.status_code = 400
        return response

    period_month = closure_form.cleaned_data["period_month"]
    transfer_amount = closure_form.cleaned_data["bank_transfer_amount"] or 0

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
                "available_cash_balance": get_branch_cash_balance(request.branch),
                "closure_error": "Verifiez les champs du versement bancaire.",
            },
        )
        response.status_code = 400
        return response

    with transaction.atomic():
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

    return manager_closure_redirect_response(period_month)


@manager_required
@require_POST
def monthly_closure_validate(request: HttpRequest, pk: int) -> HttpResponse:
    closure = get_object_or_404(BranchMonthlyClosure, pk=pk, branch=request.branch)
    if closure.status != BranchMonthlyClosure.STATUS_DRAFT:
        return manager_section_notice_redirect_response("cloture", "cloture_non_brouillon")

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

    donation = form.save(commit=False)
    donation.branch = request.branch
    donation.created_by = request.user
    donation.save()

    BranchCashMovement.objects.create(
        branch=request.branch,
        movement_type=BranchCashMovement.TYPE_IN,
        source=BranchCashMovement.SOURCE_DONATION,
        amount=donation.amount,
        label=f"Don de {donation.donor_name}",
        movement_date=donation.date,
        source_reference=f"donation_{donation.pk}",
        reference=f"DON-{donation.pk:06d}",
        notes=donation.description or "",
        created_by=request.user,
    )

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
