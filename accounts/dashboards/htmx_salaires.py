import json

from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.forms import PayrollEntryForm
from accounts.models import BranchCashMovement, PayrollEntry
from accounts.services.accounting_documents import create_cash_movement
from accounts.services.manager_intelligence import (
    get_branch_cash_balance,
    mark_ready_payroll_entries_available,
    notify_salary_available,
    payroll_cash_reference,
    prepare_missing_payroll_entries,
)

from accounts.dashboards.htmx_utils import (
    get_branch_staff_profile,
    get_salary_period_from_request,
    manager_required,
    manager_salary_redirect_response,
    manager_section_notice_redirect_response,
)


@manager_required
@require_GET
def salary_detail(request: HttpRequest, pk: int) -> HttpResponse:
    profile = get_branch_staff_profile(request.branch, pk)
    payroll_month = get_salary_period_from_request(request)
    payroll_entry = (
        PayrollEntry.objects
        .filter(
            branch=request.branch,
            employee=profile.user,
            period_month=payroll_month,
        )
        .select_related("employee", "employee__profile", "branch")
        .first()
    )
    form = PayrollEntryForm(instance=payroll_entry)
    if not payroll_entry:
        form.initial.update({
            "period_month": payroll_month,
            "base_salary": profile.salary_base,
        })
    return render(
        request,
        "accounts/dashboard/partials/payroll_modal.html",
        {
            "employee_profile": profile,
            "payroll_entry": payroll_entry,
            "payroll_form": form,
            "payroll_month": payroll_month,
            "available_cash_balance": get_branch_cash_balance(request.branch),
        },
    )


@manager_required
@require_POST
def salary_upsert(request: HttpRequest, pk: int) -> HttpResponse:
    profile = get_branch_staff_profile(request.branch, pk)
    payroll_month = get_salary_period_from_request(request)
    payroll_entry = (
        PayrollEntry.objects
        .filter(
            branch=request.branch,
            employee=profile.user,
            period_month=payroll_month,
        )
        .first()
    )
    form = PayrollEntryForm(request.POST, instance=payroll_entry)
    if not form.is_valid():
        response = render(
            request,
            "accounts/dashboard/partials/payroll_modal.html",
            {
                "employee_profile": profile,
                "payroll_entry": payroll_entry,
                "payroll_form": form,
                "payroll_month": payroll_month,
                "available_cash_balance": get_branch_cash_balance(request.branch),
            },
        )
        response.status_code = 400
        return response

    entry = form.save(commit=False)
    entry.branch = request.branch
    entry.employee = profile.user
    entry.updated_by = request.user
    if not entry.pk:
        entry.created_by = request.user
    previous_status = payroll_entry.status if payroll_entry else ""
    action = (request.POST.get("submit_action") or "draft").strip()
    if action == "ready" and entry.paid_amount == 0:
        entry.status = PayrollEntry.STATUS_READY
    elif entry.paid_amount == 0:
        entry.status = PayrollEntry.STATUS_DRAFT
    entry.save()
    if entry.status == PayrollEntry.STATUS_READY and previous_status != PayrollEntry.STATUS_READY:
        notify_salary_available(entry, request.user)

    if profile.salary_base != entry.base_salary:
        profile.salary_base = entry.base_salary
        profile.save(update_fields=["salary_base"])

    entry.refresh_from_db()
    return manager_salary_redirect_response(entry.period_month)


@manager_required
@require_POST
def salary_pay(request: HttpRequest, pk: int) -> HttpResponse:
    payroll_entry = get_object_or_404(
        PayrollEntry.objects.select_related("employee", "employee__profile", "branch"),
        pk=pk,
        branch=request.branch,
    )
    raw_amount = (request.POST.get("payment_amount") or "").strip()
    try:
        payment_amount = int(raw_amount)
    except (TypeError, ValueError):
        payment_amount = 0
    if payment_amount <= 0:
        return HttpResponse(
            "<div class='rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700'>Montant de paiement invalide.</div>",
            status=400,
        )
    if payment_amount > payroll_entry.remaining_salary:
        return HttpResponse(
            "<div class='rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700'>Le montant depasse le reste a payer sur cette paie.</div>",
            status=400,
        )
    available_cash = get_branch_cash_balance(request.branch)
    if payment_amount > available_cash:
        return HttpResponse(
            (
                "<div class='rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700'>"
                f"Caisse insuffisante pour ce paiement. Disponible: {available_cash} FCFA."
                "</div>"
            ),
            status=400,
        )

    payroll_entry.paid_amount += payment_amount
    payroll_entry.updated_by = request.user
    payroll_entry.save()
    create_cash_movement(
        branch=request.branch,
        movement_type=BranchCashMovement.TYPE_OUT,
        source=BranchCashMovement.SOURCE_PAYROLL,
        amount=payment_amount,
        label=f"Salaire - {payroll_entry.employee.get_full_name() or payroll_entry.employee.username}",
        movement_date=timezone.localdate(),
        source_reference=payroll_cash_reference(payroll_entry, payment_amount),
        notes=f"Paiement salaire {payroll_entry.period_month:%Y-%m}.",
        created_by=request.user,
    )

    return manager_salary_redirect_response(payroll_entry.period_month)


@manager_required
@require_POST
def salary_advance(request: HttpRequest, pk: int) -> HttpResponse:
    profile = get_branch_staff_profile(request.branch, pk)
    payroll_month = get_salary_period_from_request(request)
    payroll_entry = (
        PayrollEntry.objects
        .filter(
            branch=request.branch,
            employee=profile.user,
            period_month=payroll_month,
        )
        .first()
    )
    raw_amount = (request.POST.get("advance_amount") or "").strip()
    try:
        advance_amount = int(raw_amount)
    except (TypeError, ValueError):
        advance_amount = 0
    if advance_amount <= 0:
        return HttpResponse(
            "<div class='rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700'>Montant d'avance invalide.</div>",
            status=400,
        )
    available_cash = get_branch_cash_balance(request.branch)
    if advance_amount > available_cash:
        return HttpResponse(
            (
                "<div class='rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700'>"
                f"Caisse insuffisante pour cette avance. Disponible: {available_cash} FCFA."
                "</div>"
            ),
            status=400,
        )

    with transaction.atomic():
        if payroll_entry is None:
            payroll_entry = PayrollEntry.objects.create(
                branch=request.branch,
                employee=profile.user,
                period_month=payroll_month,
                base_salary=profile.salary_base,
                allowances=0,
                deductions=0,
                advances=0,
                paid_amount=0,
                status=PayrollEntry.STATUS_DRAFT,
                created_by=request.user,
                updated_by=request.user,
                notes="Fiche initiee par une avance sur salaire.",
            )
        if payroll_entry.status in {PayrollEntry.STATUS_READY, PayrollEntry.STATUS_PARTIAL, PayrollEntry.STATUS_PAID}:
            return HttpResponse(
                "<div class='rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700'>Utilisez le retrait de salaire pour une fiche deja disponible.</div>",
                status=400,
            )
        payroll_entry.advances += advance_amount
        payroll_entry.updated_by = request.user
        payroll_entry.save()
        create_cash_movement(
            branch=request.branch,
            movement_type=BranchCashMovement.TYPE_OUT,
            source=BranchCashMovement.SOURCE_PAYROLL,
            amount=advance_amount,
            label=f"Avance salaire - {profile.user.get_full_name() or profile.user.username}",
            movement_date=timezone.localdate(),
            source_reference=payroll_cash_reference(payroll_entry, f"ADV-{advance_amount}"),
            notes=f"Avance sur salaire avant disponibilite pour {payroll_entry.period_month:%Y-%m}.",
            created_by=request.user,
        )

    response = manager_salary_redirect_response(payroll_entry.period_month)
    response["HX-Trigger"] = json.dumps({"cashBalanceUpdated": True, "dashboardStatsUpdated": True})
    return response


@manager_required
@require_POST
def salary_prepare_all(request: HttpRequest) -> HttpResponse:
    payroll_month = get_salary_period_from_request(request)
    result = prepare_missing_payroll_entries(request.branch, payroll_month, request.user)
    return manager_section_notice_redirect_response(
        "salaires",
        f"paies_preparees_{result['created']}",
    )


@manager_required
@require_POST
def salary_pay_ready_all(request: HttpRequest) -> HttpResponse:
    payroll_month = get_salary_period_from_request(request)
    result = mark_ready_payroll_entries_available(request.branch, payroll_month, request.user)
    return manager_section_notice_redirect_response(
        "salaires",
        f"salaires_disponibles_{result['notified_count']}",
    )
