import json
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.forms import TeacherHonorariumEntryForm
from accounts.models import BranchCashMovement, SensitiveActionRequest, TeacherHonorariumEntry
from accounts.services.accounting_documents import create_cash_movement
from accounts.services.manager_intelligence import (
    get_branch_cash_balance,
    mark_ready_teacher_honorarium_entries_available,
    notify_teacher_honorarium_available,
    prepare_missing_teacher_honorarium_entries,
)
from accounts.services.sensitive_actions import (
    SensitiveActionError,
    confirm_sensitive_action,
    request_sensitive_action,
)

from accounts.dashboards.htmx_utils import (
    get_branch_teacher_profile,
    get_salary_period_from_request,
    manager_closure_redirect_response,
    manager_required,
    manager_section_notice_redirect_response,
)


HONORARIUM_EDITABLE_FIELDS = ["hourly_rate", "validated_hours", "adjustments", "deductions", "advances", "notes"]


def _json_safe(value):
    if isinstance(value, Decimal):
        return str(value)
    return value


@manager_required
@require_GET
def teacher_honorarium_detail(request: HttpRequest, pk: int) -> HttpResponse:
    profile = get_branch_teacher_profile(request.branch, pk)
    payroll_month = get_salary_period_from_request(request)
    honorarium_entry = (
        TeacherHonorariumEntry.objects
        .filter(
            branch=request.branch,
            teacher=profile.user,
            period_month=payroll_month,
        )
        .select_related("teacher", "teacher__profile", "branch")
        .first()
    )
    form = TeacherHonorariumEntryForm(instance=honorarium_entry)
    if not honorarium_entry:
        form.initial.update({
            "hourly_rate": profile.teacher_hourly_rate,
        })
    return render(
        request,
        "accounts/dashboard/partials/teacher_honorarium_modal.html",
        {
            "teacher_profile": profile,
            "honorarium_entry": honorarium_entry,
            "honorarium_form": form,
            "payroll_month": payroll_month,
            "available_cash_balance": get_branch_cash_balance(request.branch),
        },
    )


@manager_required
@require_POST
def teacher_honorarium_upsert(request: HttpRequest, pk: int) -> HttpResponse:
    profile = get_branch_teacher_profile(request.branch, pk)
    payroll_month = get_salary_period_from_request(request)
    honorarium_entry = (
        TeacherHonorariumEntry.objects
        .filter(
            branch=request.branch,
            teacher=profile.user,
            period_month=payroll_month,
        )
        .first()
    )
    form = TeacherHonorariumEntryForm(request.POST, instance=honorarium_entry)
    if not form.is_valid():
        response = render(
            request,
            "accounts/dashboard/partials/teacher_honorarium_modal.html",
            {
                "teacher_profile": profile,
                "honorarium_entry": honorarium_entry,
                "honorarium_form": form,
                "payroll_month": payroll_month,
                "available_cash_balance": get_branch_cash_balance(request.branch),
            },
        )
        response.status_code = 400
        return response

    if honorarium_entry and honorarium_entry.paid_amount > 0:
        return _honorarium_request_correction_otp(request, profile, honorarium_entry, form, payroll_month)

    entry = form.save(commit=False)
    entry.branch = request.branch
    entry.teacher = profile.user
    entry.period_month = payroll_month
    entry.updated_by = request.user
    if not entry.pk:
        entry.created_by = request.user
    previous_status = honorarium_entry.status if honorarium_entry else ""
    action = (request.POST.get("submit_action") or "draft").strip()
    if action == "ready" and entry.paid_amount == 0:
        entry.status = TeacherHonorariumEntry.STATUS_READY
    elif entry.paid_amount == 0:
        entry.status = TeacherHonorariumEntry.STATUS_DRAFT
    entry.save()
    if entry.status == TeacherHonorariumEntry.STATUS_READY and previous_status != TeacherHonorariumEntry.STATUS_READY:
        notify_teacher_honorarium_available(entry, request.user)

    if profile.teacher_hourly_rate != entry.hourly_rate:
        profile.teacher_hourly_rate = entry.hourly_rate
        profile.save(update_fields=["teacher_hourly_rate"])

    entry.refresh_from_db()
    return manager_closure_redirect_response(entry.period_month)


def _honorarium_modal_context(profile, honorarium_entry, form, payroll_month, **extra):
    context = {
        "teacher_profile": profile,
        "honorarium_entry": honorarium_entry,
        "honorarium_form": form,
        "payroll_month": payroll_month,
        "available_cash_balance": get_branch_cash_balance(profile.branch),
    }
    context.update(extra)
    return context


def _honorarium_request_correction_otp(request, profile, honorarium_entry, form, payroll_month):
    reason = (request.POST.get("reason") or "").strip()
    confirmation = (request.POST.get("confirmation") or "").strip().upper()

    if confirmation != "CORRIGER":
        response = render(
            request,
            "accounts/dashboard/partials/teacher_honorarium_modal.html",
            _honorarium_modal_context(
                profile, honorarium_entry, form, payroll_month,
                correction_error="Tapez CORRIGER pour confirmer la modification de cet honoraire deja paye.",
                correction_reason=reason,
            ),
        )
        response.status_code = 400
        return response

    previous_state = {
        field: _json_safe(getattr(honorarium_entry, field)) for field in HONORARIUM_EDITABLE_FIELDS
    }
    requested_state = {
        field: _json_safe(form.cleaned_data[field]) for field in HONORARIUM_EDITABLE_FIELDS
    }

    try:
        otp_request = request_sensitive_action(
            branch=request.branch,
            action_type=SensitiveActionRequest.ACTION_HONORARIUM_EDIT,
            target_model="TeacherHonorariumEntry",
            target_id=honorarium_entry.pk,
            previous_state=previous_state,
            requested_state=requested_state,
            requested_by=request.user,
            reason=reason,
        )
    except SensitiveActionError as exc:
        response = render(
            request,
            "accounts/dashboard/partials/teacher_honorarium_modal.html",
            _honorarium_modal_context(
                profile, honorarium_entry, form, payroll_month,
                correction_error=str(exc),
                correction_reason=reason,
            ),
        )
        response.status_code = 400
        return response

    response = render(
        request,
        "accounts/dashboard/partials/teacher_honorarium_modal.html",
        _honorarium_modal_context(
            profile, honorarium_entry, form, payroll_month,
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
def teacher_honorarium_correct_confirm_otp(request: HttpRequest, pk: int) -> HttpResponse:
    honorarium_entry = get_object_or_404(
        TeacherHonorariumEntry.objects.select_related("teacher", "teacher__profile", "branch"),
        pk=pk,
        branch=request.branch,
    )
    profile = get_branch_teacher_profile(request.branch, honorarium_entry.teacher_id)
    payroll_month = honorarium_entry.period_month
    otp_request_id = request.POST.get("otp_request_id")
    otp_code = (request.POST.get("otp_code") or "").strip()

    def _apply(otp_request):
        for field, value in otp_request.requested_state.items():
            if field == "validated_hours":
                value = Decimal(str(value))
            setattr(honorarium_entry, field, value)
        honorarium_entry.updated_by = otp_request.requested_by
        honorarium_entry.save()
        if profile.teacher_hourly_rate != honorarium_entry.hourly_rate:
            profile.teacher_hourly_rate = honorarium_entry.hourly_rate
            profile.save(update_fields=["teacher_hourly_rate"])
        honorarium_entry.refresh_from_db()
        return {
            field: _json_safe(getattr(honorarium_entry, field)) for field in HONORARIUM_EDITABLE_FIELDS
        }

    try:
        confirm_sensitive_action(
            request_id=otp_request_id,
            code=otp_code,
            approver=request.user,
            apply_callback=_apply,
        )
    except (SensitiveActionError, ValidationError, SensitiveActionRequest.DoesNotExist) as exc:
        message = " ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
        honorarium_entry.refresh_from_db()
        response = render(
            request,
            "accounts/dashboard/partials/teacher_honorarium_modal.html",
            _honorarium_modal_context(
                profile, honorarium_entry, TeacherHonorariumEntryForm(instance=honorarium_entry), payroll_month,
                otp_request_id=otp_request_id,
                otp_error=message,
            ),
        )
        response.status_code = 400
        return response

    honorarium_entry.refresh_from_db()
    response = render(
        request,
        "accounts/dashboard/partials/teacher_honorarium_modal.html",
        _honorarium_modal_context(
            profile, honorarium_entry, TeacherHonorariumEntryForm(instance=honorarium_entry), payroll_month,
            correction_success="Modification validee par le DG/DGA et tracee dans l'audit financier.",
        ),
    )
    response["HX-Trigger"] = json.dumps({
        "dashboardStatsUpdated": True,
        "showToast": {"message": "Honoraire corrige avec tracabilite.", "type": "success"},
    })
    return response


@manager_required
@require_POST
def teacher_honorarium_pay(request: HttpRequest, pk: int) -> HttpResponse:
    honorarium_entry = get_object_or_404(
        TeacherHonorariumEntry.objects.select_related("teacher", "teacher__profile", "branch"),
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
    if payment_amount > honorarium_entry.remaining_amount:
        return HttpResponse(
            "<div class='rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700'>Le montant depasse le reste a payer sur cet honoraire.</div>",
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

    honorarium_entry.paid_amount += payment_amount
    honorarium_entry.updated_by = request.user
    honorarium_entry.save()
    create_cash_movement(
        branch=request.branch,
        movement_type=BranchCashMovement.TYPE_OUT,
        source=BranchCashMovement.SOURCE_HONORARIUM,
        amount=payment_amount,
        label=f"Honoraire - {honorarium_entry.teacher.get_full_name() or honorarium_entry.teacher.username}",
        movement_date=timezone.localdate(),
        source_reference=f"HON-{honorarium_entry.pk}-{payment_amount}",
        notes=f"Paiement honoraire {honorarium_entry.period_month:%Y-%m}.",
        created_by=request.user,
    )

    response = manager_closure_redirect_response(honorarium_entry.period_month)
    response["HX-Trigger"] = json.dumps({"cashBalanceUpdated": True, "dashboardStatsUpdated": True})
    return response


@manager_required
@require_POST
def teacher_honorarium_prepare_all(request: HttpRequest) -> HttpResponse:
    payroll_month = get_salary_period_from_request(request)
    result = prepare_missing_teacher_honorarium_entries(request.branch, payroll_month, request.user)
    return manager_section_notice_redirect_response(
        "cloture",
        f"honoraires_preparees_{result['created']}",
    )


@manager_required
@require_POST
def teacher_honorarium_pay_ready_all(request: HttpRequest) -> HttpResponse:
    payroll_month = get_salary_period_from_request(request)
    result = mark_ready_teacher_honorarium_entries_available(request.branch, payroll_month, request.user)
    return manager_section_notice_redirect_response(
        "cloture",
        f"honoraires_disponibles_{result['notified_count']}",
    )
