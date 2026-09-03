from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from accounts.models import PayrollEntry, Profile, SensitiveActionRequest, TeacherHonorariumEntry
from accounts.services.sensitive_actions import SensitiveActionError, confirm_sensitive_action
from payments.models import Payment
from payments.services.corrections import correct_validated_payment_amount


EXECUTIVE_POSITIONS = {"executive_director", "deputy_executive_director"}


def _require_financial_approver(request: HttpRequest) -> None:
    if not Profile.objects.filter(
        user=request.user,
        user__is_active=True,
        position__in=EXECUTIVE_POSITIONS,
    ).exists():
        raise PermissionDenied("Seul le DG ou la DGA peut valider une correction financiere.")


def _apply_sensitive_action(action: SensitiveActionRequest):
    if action.action_type == SensitiveActionRequest.ACTION_ANNUAL_DELIBERATION_PUBLISH:
        from academic_cycle.models import BranchAcademicCycle
        from academics.models import AcademicClass
        from academics.services.annual_deliberation import finalise_class_deliberation

        academic_class = AcademicClass.objects.select_related("branch", "academic_year").get(
            pk=action.target_id,
            branch=action.branch,
            academic_year_id=action.requested_state.get("academic_year_id"),
        )
        cycle = BranchAcademicCycle.objects.get(
            branch=action.branch,
            academic_year=academic_class.academic_year,
        )
        result = finalise_class_deliberation(
            academic_class=academic_class,
            actor=action.requested_by,
            branch_cycle=cycle,
        )
        from academic_cycle.models import ClassDeliberationSession
        ClassDeliberationSession.objects.filter(
            academic_class=academic_class,
            branch=action.branch,
            academic_year=academic_class.academic_year,
        ).update(status=ClassDeliberationSession.STATUS_OFFICIAL)
        return {
            "class_id": academic_class.id,
            "academic_year_id": academic_class.academic_year_id,
            "finalised": not result["idempotent"],
        }

    if action.action_type == SensitiveActionRequest.ACTION_PAYROLL_EDIT:
        entry = PayrollEntry.objects.select_related("employee__profile").get(
            pk=action.target_id, branch=action.branch
        )
        for field in ("base_salary", "allowances", "deductions", "advances", "notes"):
            setattr(entry, field, action.requested_state[field])
        entry.updated_by = action.requested_by
        entry.save()
        entry.employee.profile.salary_base = entry.base_salary
        entry.employee.profile.save(update_fields=["salary_base", "updated_at"])
        return {field: getattr(entry, field) for field in ("base_salary", "allowances", "deductions", "advances", "notes")}

    if action.action_type == SensitiveActionRequest.ACTION_HONORARIUM_EDIT:
        entry = TeacherHonorariumEntry.objects.select_related("teacher__profile").get(
            pk=action.target_id, branch=action.branch
        )
        for field in ("hourly_rate", "adjustments", "deductions", "advances", "notes"):
            setattr(entry, field, action.requested_state[field])
        entry.updated_by = action.requested_by
        entry.save()
        entry.teacher.profile.teacher_hourly_rate = entry.hourly_rate
        entry.teacher.profile.save(update_fields=["teacher_hourly_rate", "updated_at"])
        return {field: getattr(entry, field) for field in ("hourly_rate", "adjustments", "deductions", "advances", "notes")}

    if action.action_type == SensitiveActionRequest.ACTION_PAYMENT_EDIT:
        payment = Payment.objects.get(
            pk=action.target_id,
            inscription__candidature__branch=action.branch,
            status=Payment.STATUS_VALIDATED,
        )
        correct_validated_payment_amount(
            payment=payment,
            new_amount=action.requested_state["amount"],
            reason=action.reason,
            actor=action.requested_by,
        )
        payment.refresh_from_db()
        return {"amount": payment.amount}

    raise SensitiveActionError("Ce type d'action ne peut pas etre approuve depuis ce circuit.")


@login_required
@require_GET
def financial_approval_detail(request: HttpRequest, pk: int) -> HttpResponse:
    _require_financial_approver(request)
    action = get_object_or_404(SensitiveActionRequest, pk=pk)
    annual_rows = []
    if action.action_type == SensitiveActionRequest.ACTION_ANNUAL_DELIBERATION_PUBLISH:
        from academics.models import AcademicClass
        from academic_cycle.models import ClassDeliberationSession
        from academics.services.annual_deliberation import get_class_deliberation_rows

        academic_class = (
            AcademicClass.objects.filter(
                pk=action.target_id,
                branch=action.branch,
                academic_year_id=action.requested_state.get("academic_year_id"),
            )
            .prefetch_related("semesters")
            .first()
        )
        if academic_class is None:
            raise PermissionDenied("La classe concernee par cette demande est introuvable.")
        session = ClassDeliberationSession.objects.filter(academic_class=academic_class).first()
        annual_rows = (
            (session.transmission_snapshot or {}).get("rows", [])
            if session and session.transmission_snapshot
            else get_class_deliberation_rows(academic_class=academic_class)
        )
    return render(request, "accounts/financial_approval.html", {"action": action, "annual_rows": annual_rows})


@login_required
@require_POST
def financial_approval_confirm(request: HttpRequest, pk: int) -> HttpResponse:
    _require_financial_approver(request)
    action = get_object_or_404(SensitiveActionRequest, pk=pk)
    try:
        confirm_sensitive_action(
            request_id=action.pk,
            code=(request.POST.get("otp_code") or "").strip(),
            approver=request.user,
            apply_callback=_apply_sensitive_action,
        )
    except (SensitiveActionError, ValidationError, KeyError, PayrollEntry.DoesNotExist, TeacherHonorariumEntry.DoesNotExist, Payment.DoesNotExist) as exc:
        return render(request, "accounts/financial_approval.html", {"action": action, "error": str(exc)}, status=400)
    messages.success(request, "Correction financiere approuvee et tracee.")
    return redirect("accounts:financial_approval_detail", pk=action.pk)
