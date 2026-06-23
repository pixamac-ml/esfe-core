import json

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.forms import PayrollEntryForm
from accounts.models import BranchCashMovement, PayrollEntry, SensitiveActionRequest
from accounts.services.accounting_documents import create_cash_movement
from accounts.services.manager_intelligence import (
    get_branch_cash_balance,
    mark_ready_payroll_entries_available,
    notify_salary_available,
    payroll_cash_reference,
    prepare_missing_payroll_entries,
)
from accounts.services.sensitive_actions import (
    SensitiveActionError,
    confirm_sensitive_action,
    request_sensitive_action,
)

from accounts.dashboards.htmx_utils import (
    get_branch_staff_profile,
    get_salary_period_from_request,
    manager_required,
    manager_salary_redirect_response,
    manager_section_notice_redirect_response,
)


PAYROLL_EDITABLE_FIELDS = ["base_salary", "allowances", "deductions", "advances", "notes"]


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

    if payroll_entry and payroll_entry.paid_amount > 0:
        return _salary_request_correction_otp(request, profile, payroll_entry, form, payroll_month)

    entry = form.save(commit=False)
    entry.branch = request.branch
    entry.employee = profile.user
    entry.period_month = payroll_month
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


def _payroll_modal_context(profile, payroll_entry, form, payroll_month, **extra):
    context = {
        "employee_profile": profile,
        "payroll_entry": payroll_entry,
        "payroll_form": form,
        "payroll_month": payroll_month,
        "available_cash_balance": get_branch_cash_balance(profile.branch),
    }
    context.update(extra)
    return context


def _salary_request_correction_otp(request, profile, payroll_entry, form, payroll_month):
    reason = (request.POST.get("reason") or "").strip()
    confirmation = (request.POST.get("confirmation") or "").strip().upper()

    if confirmation != "CORRIGER":
        response = render(
            request,
            "accounts/dashboard/partials/payroll_modal.html",
            _payroll_modal_context(
                profile, payroll_entry, form, payroll_month,
                correction_error="Tapez CORRIGER pour confirmer la modification de cette fiche deja payee.",
                correction_reason=reason,
            ),
        )
        response.status_code = 400
        return response

    previous_state = {field: getattr(payroll_entry, field) for field in PAYROLL_EDITABLE_FIELDS}
    requested_state = {field: form.cleaned_data[field] for field in PAYROLL_EDITABLE_FIELDS}

    try:
        otp_request = request_sensitive_action(
            branch=request.branch,
            action_type=SensitiveActionRequest.ACTION_PAYROLL_EDIT,
            target_model="PayrollEntry",
            target_id=payroll_entry.pk,
            previous_state=previous_state,
            requested_state=requested_state,
            requested_by=request.user,
            reason=reason,
        )
    except SensitiveActionError as exc:
        response = render(
            request,
            "accounts/dashboard/partials/payroll_modal.html",
            _payroll_modal_context(
                profile, payroll_entry, form, payroll_month,
                correction_error=str(exc),
                correction_reason=reason,
            ),
        )
        response.status_code = 400
        return response

    response = render(
        request,
        "accounts/dashboard/partials/payroll_modal.html",
        _payroll_modal_context(
            profile, payroll_entry, form, payroll_month,
            otp_request_id=otp_request.pk,
            otp_validity_minutes=SensitiveActionRequest.OTP_VALIDITY_MINUTES,
        ),
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
def salary_correct_confirm_otp(request: HttpRequest, pk: int) -> HttpResponse:
    payroll_entry = get_object_or_404(
        PayrollEntry.objects.select_related("employee", "employee__profile", "branch"),
        pk=pk,
        branch=request.branch,
    )
    profile = get_branch_staff_profile(request.branch, payroll_entry.employee_id)
    payroll_month = payroll_entry.period_month
    otp_request_id = request.POST.get("otp_request_id")
    otp_code = (request.POST.get("otp_code") or "").strip()

    def _apply(otp_request):
        for field, value in otp_request.requested_state.items():
            setattr(payroll_entry, field, value)
        payroll_entry.updated_by = otp_request.requested_by
        payroll_entry.save()
        if profile.salary_base != payroll_entry.base_salary:
            profile.salary_base = payroll_entry.base_salary
            profile.save(update_fields=["salary_base"])
        payroll_entry.refresh_from_db()
        return {field: getattr(payroll_entry, field) for field in PAYROLL_EDITABLE_FIELDS}

    try:
        confirm_sensitive_action(
            request_id=otp_request_id,
            code=otp_code,
            approver=request.user,
            apply_callback=_apply,
        )
    except (SensitiveActionError, ValidationError, SensitiveActionRequest.DoesNotExist) as exc:
        message = " ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
        payroll_entry.refresh_from_db()
        response = render(
            request,
            "accounts/dashboard/partials/payroll_modal.html",
            _payroll_modal_context(
                profile, payroll_entry, PayrollEntryForm(instance=payroll_entry), payroll_month,
                otp_request_id=otp_request_id,
                otp_error=message,
            ),
        )
        response.status_code = 400
        return response

    payroll_entry.refresh_from_db()
    response = render(
        request,
        "accounts/dashboard/partials/payroll_modal.html",
        _payroll_modal_context(
            profile, payroll_entry, PayrollEntryForm(instance=payroll_entry), payroll_month,
            correction_success="Modification validee par le DG/DGA et tracee dans l'audit financier.",
        ),
    )
    response["HX-Trigger"] = json.dumps({
        "dashboardStatsUpdated": True,
        "showToast": {"message": "Fiche de paie corrigee avec tracabilite.", "type": "success"},
    })
    return response


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
