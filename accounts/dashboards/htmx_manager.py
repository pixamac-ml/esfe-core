from calendar import monthrange
import json
from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from django.db.models import Q, Sum

from academics.models import AcademicClass
from academics.services.academic_positioning import get_positioning_context, get_positioning_fee_for_level
from admissions.models import Candidature
from accounts.forms import (
    BranchBankTransferForm,
    BranchCashMovementForm,
    BranchExpenseForm,
    BranchMonthlyClosureForm,
    DonationForm,
    PayrollEntryForm,
    TeacherHonorariumEntryForm,
)
from accounts.models import BranchBankTransfer, BranchCashMovement, BranchExpense, BranchMonthlyClosure, Donation, PayrollEntry, Profile, TeacherHonorariumEntry
from accounts.services.accounting_documents import (
    create_cash_movement,
    ensure_expense_reference,
    ensure_cash_movement_receipt,
    finalize_cash_movement_document,
)
from accounts.services.manager_intelligence import (
    get_branch_cash_balance,
    mark_ready_teacher_honorarium_entries_available,
    notify_teacher_honorarium_available,
    mark_ready_payroll_entries_available,
    notify_salary_available,
    payment_cash_reference,
    pay_ready_teacher_honorarium_entries,
    pay_ready_payroll_entries,
    payroll_cash_reference,
    prepare_missing_teacher_honorarium_entries,
    prepare_missing_payroll_entries,
    sync_student_payment_cash_movements,
)
from inscriptions.models import Inscription
from payments.models import CashPaymentSession, FinancialLog, Payment, PaymentAgent
from payments.services.corrections import correct_validated_payment_amount, financial_logs_for_payment

from accounts.dashboards.helpers import get_user_branch, is_manager
from accounts.services.excel_reports import export_branch_report_xlsx, xlsx_response


PAYABLE_INSCRIPTION_STATUSES = {
    Inscription.STATUS_CREATED,
    Inscription.STATUS_AWAITING_PAYMENT,
    Inscription.STATUS_PARTIAL,
}


def manager_required(view_func):
    """Decorateur gestionnaire."""

    def wrapper(request, *args, **kwargs):
        if not is_manager(request.user):
            return HttpResponse("Non autorise", status=403)
        branch = get_user_branch(request.user)
        if not branch:
            return HttpResponse("Annexe non trouvee", status=403)
        request.branch = branch
        return view_func(request, *args, **kwargs)

    return login_required(wrapper)


def get_current_agent(user, branch):
    return (
        PaymentAgent.objects
        .select_related("user", "branch")
        .filter(user=user, branch=branch, is_active=True)
        .first()
    )


def _render_manager_academic_positioning_modal(request, candidature, *, form_error="", selected_level="", selected_class_id=""):
    return render(
        request,
        "accounts/dashboard/partials/academic_positioning_body.html",
        {
            "candidature": candidature,
            "positioning": get_positioning_context(candidature=candidature),
            "form_error": form_error,
            "selected_level": (selected_level or "").strip().upper(),
            "selected_class_id": str(selected_class_id or "").strip(),
            "submit_url_name": "accounts:htmx_inscription_create",
        },
    )


def get_active_cash_session(inscription):
    return (
        CashPaymentSession.objects
        .filter(
            inscription=inscription,
            is_used=False,
            expires_at__gt=timezone.now(),
        )
        .select_related(
            "agent__user",
            "inscription",
            "inscription__candidature",
            "inscription__candidature__programme",
        )
        .order_by("-created_at")
        .first()
    )


def get_salary_period_from_request(request):
    raw_value = (request.GET.get("salary_month") or request.POST.get("period_month") or "").strip()
    if raw_value:
        try:
            return date.fromisoformat(f"{raw_value[:7]}-01")
        except ValueError:
            pass
    today = timezone.now().date()
    return today.replace(day=1)


def get_branch_staff_profile(branch, user_id):
    return get_object_or_404(
        Profile.objects.select_related("user", "branch").filter(
            branch=branch,
            user__is_active=True,
        ).exclude(position="student").exclude(user_type="public"),
        user_id=user_id,
    )


def get_branch_teacher_profile(branch, user_id):
    profile = get_branch_staff_profile(branch, user_id)
    if profile.position != "teacher":
        raise Http404("Profil enseignant introuvable")
    return profile


def manager_salary_redirect_response(period_month):
    response = HttpResponse("")
    response["HX-Redirect"] = (
        f"{reverse('accounts:manager_dashboard')}?section=salaires&salary_month={period_month.strftime('%Y-%m')}"
    )
    return response


def manager_closure_redirect_response(period_month):
    response = HttpResponse("")
    response["HX-Redirect"] = (
        f"{reverse('accounts:manager_dashboard')}?section=cloture&salary_month={period_month.strftime('%Y-%m')}"
    )
    return response


def manager_section_redirect_response(section):
    response = HttpResponse("")
    response["HX-Redirect"] = f"{reverse('accounts:manager_dashboard')}?section={section}"
    return response


def manager_section_notice_redirect_response(section, message):
    response = HttpResponse("")
    response["HX-Redirect"] = f"{reverse('accounts:manager_dashboard')}?section={section}&notice={message}"
    return response


@manager_required
@require_GET
def candidature_detail(request, pk):
    candidature = get_object_or_404(
        Candidature.objects.select_related("programme", "branch"),
        pk=pk,
        branch=request.branch,
    )
    documents = candidature.documents.select_related("document_type").all()
    return render(
        request,
        "accounts/dashboard/partials/candidature_modal.html",
        {
            "candidature": candidature,
            "documents": documents,
        },
    )


@manager_required
@require_POST
def candidature_under_review(request, pk):
    candidature = get_object_or_404(Candidature, pk=pk, branch=request.branch)

    if candidature.status != "submitted":
        return HttpResponse("Seules les candidatures soumises peuvent passer en analyse.", status=400)

    candidature.status = "under_review"
    candidature.reviewed_at = timezone.now()
    candidature.reviewed_by = request.user
    candidature.save(update_fields=["status", "reviewed_at", "reviewed_by"])

    response = render(
        request,
        "accounts/dashboard/partials/manager_candidature_row.html",
        {"candidature": candidature},
    )
    response["HX-Trigger"] = json.dumps(
        {
            "showToast": {
                "message": "Candidature passee en analyse.",
                "type": "info",
            }
        }
    )
    return response


@manager_required
@require_POST
def candidature_accept(request, pk):
    candidature = get_object_or_404(Candidature, pk=pk, branch=request.branch)
    candidature.status = "accepted"
    candidature.reviewed_at = timezone.now()
    candidature.reviewed_by = request.user
    candidature.save(update_fields=["status", "reviewed_at", "reviewed_by"])
    response = render(
        request,
        "accounts/dashboard/partials/manager_candidature_row.html",
        {"candidature": candidature},
    )
    response["HX-Trigger"] = (
        '{"openInscriptionPositioning": {"url": "%s"}, '
        '"showToast": {"message": "Candidature acceptee. Positionnement academique requis.", "type": "success"}}'
        % reverse("accounts:htmx_inscription_positioning", args=[candidature.id])
    )
    return response


@manager_required
@require_POST
def candidature_reject(request, pk):
    candidature = get_object_or_404(Candidature, pk=pk, branch=request.branch)
    candidature.status = "rejected"
    candidature.rejection_reason = (request.POST.get("reason") or "").strip() or "Rejeté par le gestionnaire."
    candidature.reviewed_at = timezone.now()
    candidature.reviewed_by = request.user
    candidature.save(update_fields=["status", "rejection_reason", "reviewed_at", "reviewed_by"])
    return render(
        request,
        "accounts/dashboard/partials/manager_candidature_row.html",
        {"candidature": candidature},
    )


@manager_required
@require_POST
def candidature_to_complete(request, pk):
    candidature = get_object_or_404(Candidature, pk=pk, branch=request.branch)
    candidature.status = "to_complete"
    candidature.completion_message = (request.POST.get("message") or "").strip() or "Compléments demandés par le gestionnaire."
    candidature.reviewed_at = timezone.now()
    candidature.reviewed_by = request.user
    candidature.save(update_fields=["status", "completion_message", "reviewed_at", "reviewed_by"])
    return render(
        request,
        "accounts/dashboard/partials/manager_candidature_row.html",
        {"candidature": candidature},
    )


@manager_required
@require_POST
def candidature_delete(request, pk):
    candidature = get_object_or_404(
        Candidature.objects.select_related("branch").prefetch_related("documents"),
        pk=pk,
        branch=request.branch,
        is_deleted=False,
    )

    if candidature.status != "rejected":
        return HttpResponse("Seules les candidatures rejetees peuvent etre supprimees.", status=400)

    if hasattr(candidature, "inscription"):
        return HttpResponse("Impossible de supprimer: une inscription est liee a cette candidature.", status=400)

    with transaction.atomic():
        candidature.documents.all().delete()
        candidature.is_deleted = True
        candidature.deleted_at = timezone.now()
        candidature.deleted_by = request.user
        candidature.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    response = HttpResponse("")
    response["HX-Trigger"] = json.dumps(
        {
            "candidatureDeleted": {"id": pk},
            "showToast": {
                "message": "Candidature supprimee.",
                "type": "warning",
            },
        }
    )
    return response


@manager_required
@require_GET
def inscription_detail(request, pk):
    inscription = get_object_or_404(
        Inscription.objects.select_related(
            "candidature",
            "candidature__programme",
            "candidature__branch",
        ).prefetch_related("payments"),
        pk=pk,
        candidature__branch=request.branch,
    )
    manager_agent = get_current_agent(request.user, request.branch)
    active_cash_session = get_active_cash_session(inscription)
    return render(
        request,
        "accounts/dashboard/partials/inscription_modal.html",
        {
            "inscription": inscription,
            "payments": inscription.payments.all().order_by("-created_at"),
            "manager_agent": manager_agent,
            "active_cash_session": active_cash_session,
            "can_create_cash_session": (
                manager_agent
                and inscription.status in PAYABLE_INSCRIPTION_STATUSES
                and inscription.balance > 0
                and active_cash_session is None
            ),
        },
    )


@manager_required
@require_GET
def inscription_positioning_modal(request, pk):
    candidature = get_object_or_404(
        Candidature,
        pk=pk,
        branch=request.branch,
        status__in=["accepted", "accepted_with_reserve"],
    )

    if hasattr(candidature, "inscription"):
        return HttpResponse("Inscription deja creee", status=400)

    return _render_manager_academic_positioning_modal(request, candidature)


@manager_required
@require_POST
def inscription_create(request, pk):
    candidature = get_object_or_404(
        Candidature,
        pk=pk,
        branch=request.branch,
        status__in=["accepted", "accepted_with_reserve"],
    )

    if hasattr(candidature, "inscription"):
        return HttpResponse(
            '<tr><td colspan="5" class="px-6 py-4 text-sm text-red-600">Une inscription existe deja pour cette candidature.</td></tr>',
            status=400,
        )

    selected_level = request.POST.get("academic_level", "").strip().upper()
    academic_class_id = request.POST.get("academic_class", "").strip()
    academic_class = (
        AcademicClass.objects.select_related("programme", "branch", "academic_year")
        .filter(pk=academic_class_id)
        .first()
    )

    if not academic_class:
        return _render_manager_academic_positioning_modal(
            request,
            candidature,
            form_error="Selectionnez une classe existante avant de creer l'inscription.",
            selected_level=selected_level,
            selected_class_id=academic_class_id,
        )

    amount = get_positioning_fee_for_level(candidature.programme, academic_class.level) or 0
    if amount <= 0:
        return _render_manager_academic_positioning_modal(
            request,
            candidature,
            form_error="Aucun frais n'est configure pour ce niveau dans ce programme.",
            selected_level=selected_level or academic_class.level,
            selected_class_id=academic_class_id,
        )

    try:
        from inscriptions.services import create_inscription_from_candidature

        inscription = create_inscription_from_candidature(
            candidature=candidature,
            amount_due=amount,
            academic_class=academic_class,
            status=Inscription.STATUS_AWAITING_PAYMENT,
        )
    except Exception as e:
        return _render_manager_academic_positioning_modal(
            request,
            candidature,
            form_error=str(e),
            selected_level=selected_level or getattr(academic_class, "level", ""),
            selected_class_id=academic_class_id,
        )

    response = HttpResponse("")
    response["HX-Trigger"] = (
        '{"inscriptionCreated": {"candidature_id": %s, "inscription_id": %s}, '
        '"showToast": {"message": "Inscription creee avec succes.", "type": "success"}}'
        % (candidature.id, inscription.id)
    )
    return response


@manager_required
@require_GET
def payment_detail(request, pk):
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
def payment_correct(request, pk):
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
        correct_validated_payment_amount(
            payment=payment,
            new_amount=new_amount,
            reason=reason,
            actor=request.user,
        )
    except ValidationError as exc:
        payment.refresh_from_db()
        response = render(
            request,
            "accounts/dashboard/partials/payment_modal.html",
            {
                "payment": payment,
                "financial_logs": financial_logs_for_payment(payment)[:20],
                "corrections": payment.corrections.select_related("corrected_by").all()[:10],
                "correction_error": " ".join(exc.messages),
                "correction_new_amount": raw_amount,
                "correction_reason": reason,
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
            "correction_success": "Correction enregistree et caisse synchronisee.",
        },
    )
    response["HX-Trigger"] = '{"showToast": {"message": "Paiement corrige avec tracabilite.", "type": "success"}}'
    return response


@manager_required
@require_POST
def payment_validate(request, pk):
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
    return render(
        request,
        "accounts/dashboard/partials/manager_payment_row.html",
        {"payment": payment},
    )


@manager_required
@require_POST
def payment_cancel(request, pk):
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
    return render(
        request,
        "accounts/dashboard/partials/manager_payment_row.html",
        {"payment": payment},
    )


@manager_required
@require_GET
def global_search(request):
    q = request.GET.get("q", "").strip()
    branch = request.branch

    if len(q) < 2:
        return HttpResponse("")

    candidatures = Candidature.objects.filter(
        branch=branch,
        is_deleted=False,
    ).filter(
        Q(first_name__icontains=q)
        | Q(last_name__icontains=q)
        | Q(email__icontains=q)
    )[:5]
    inscriptions = Inscription.objects.filter(
        candidature__branch=branch,
        candidature__is_deleted=False,
        is_archived=False,
    ).filter(
        Q(candidature__first_name__icontains=q)
        | Q(candidature__last_name__icontains=q)
        | Q(public_token__icontains=q)
    ).select_related("candidature")[:5]
    payments = Payment.objects.filter(
        inscription__candidature__branch=branch,
        inscription__candidature__is_deleted=False,
        inscription__is_archived=False,
    ).filter(
        Q(reference__icontains=q)
        | Q(inscription__candidature__last_name__icontains=q)
    ).select_related("inscription__candidature")[:5]

    return render(
        request,
        "accounts/dashboard/partials/search_results.html",
        {
            "candidatures": candidatures,
            "inscriptions": inscriptions,
            "payments": payments,
            "query": q,
        },
    )


@manager_required
@require_POST
def cash_session_create(request, pk):
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
def cash_session_regenerate(request, pk):
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
def cash_session_complete(request, pk):
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

    return render(
        request,
        "accounts/dashboard/partials/cash_session_completed.html",
        {"session": session, "payment": payment},
    )


@manager_required
@require_POST
def cash_session_cancel(request, pk):
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
@require_GET
def salary_detail(request, pk):
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
def salary_upsert(request, pk):
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
def salary_pay(request, pk):
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
def salary_advance(request, pk):
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

    return manager_salary_redirect_response(payroll_entry.period_month)


@manager_required
@require_POST
def salary_prepare_all(request):
    payroll_month = get_salary_period_from_request(request)
    result = prepare_missing_payroll_entries(request.branch, payroll_month, request.user)
    return manager_section_notice_redirect_response(
        "salaires",
        f"paies_preparees_{result['created']}",
    )


@manager_required
@require_POST
def salary_pay_ready_all(request):
    payroll_month = get_salary_period_from_request(request)
    result = mark_ready_payroll_entries_available(request.branch, payroll_month, request.user)
    return manager_section_notice_redirect_response(
        "salaires",
        f"salaires_disponibles_{result['notified_count']}",
    )


@manager_required
@require_GET
def teacher_honorarium_detail(request, pk):
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
            "period_month": payroll_month,
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
def teacher_honorarium_upsert(request, pk):
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

    entry = form.save(commit=False)
    entry.branch = request.branch
    entry.teacher = profile.user
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


@manager_required
@require_POST
def teacher_honorarium_pay(request, pk):
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

    return manager_closure_redirect_response(honorarium_entry.period_month)


@manager_required
@require_POST
def teacher_honorarium_prepare_all(request):
    payroll_month = get_salary_period_from_request(request)
    result = prepare_missing_teacher_honorarium_entries(request.branch, payroll_month, request.user)
    return manager_section_notice_redirect_response(
        "cloture",
        f"honoraires_preparees_{result['created']}",
    )


@manager_required
@require_POST
def teacher_honorarium_pay_ready_all(request):
    payroll_month = get_salary_period_from_request(request)
    result = mark_ready_teacher_honorarium_entries_available(request.branch, payroll_month, request.user)
    return manager_section_notice_redirect_response(
        "cloture",
        f"honoraires_disponibles_{result['notified_count']}",
    )


@manager_required
@require_POST
def monthly_closure_create(request):
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
                "status": BranchMonthlyClosure.STATUS_CLOSED,
                "notes": closure_form.cleaned_data.get("notes", ""),
                "validated_by": request.user,
                "validated_at": timezone.now(),
                "closed_at": timezone.now(),
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
def expense_create(request):
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
def expense_approve(request, pk):
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
def expense_reject(request, pk):
    expense = get_object_or_404(BranchExpense, pk=pk, branch=request.branch)
    if expense.status == BranchExpense.STATUS_PAID:
        return HttpResponse("Une depense deja payee ne peut pas etre rejetee.", status=400)
    expense.status = BranchExpense.STATUS_REJECTED
    expense.save(update_fields=["status", "updated_at"])
    return manager_section_redirect_response("depenses")


@manager_required
@require_POST
def expense_pay(request, pk):
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
    return manager_section_redirect_response("depenses")


@manager_required
@require_POST
def cash_movement_create(request):
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
    return manager_section_redirect_response("caisse")


@manager_required
@require_POST
def cash_sync(request):
    result = sync_student_payment_cash_movements(request.branch, request.user)
    return manager_section_notice_redirect_response(
        "caisse",
        f"caisse_sync_{result['created']}",
    )


@manager_required
@require_GET
def cash_movement_receipt(request, pk):
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


@manager_required
@require_GET
def export_report_xlsx(request):
    from datetime import date
    from accounts.dashboards.manager_dashboard import _resolve_report_period
    from accounts.services.excel_reports import export_branch_report_xlsx, xlsx_response

    branch = request.branch
    today = date.today()
    report_period = _resolve_report_period(request, today)

    branch_staff_profiles = Profile.objects.filter(
        branch=branch, user__is_active=True,
    ).exclude(position="student").exclude(user_type="public").order_by("user__first_name")[:500]

    branch_teacher_profiles = branch_staff_profiles.filter(position="teacher")

    wb = export_branch_report_xlsx(
        branch=branch,
        report_period=report_period,
        branch_staff_profiles=branch_staff_profiles,
        branch_teacher_profiles=branch_teacher_profiles,
    )
    label = report_period["label"].replace(" ", "_")
    return xlsx_response(
        wb,
        filename=f"rapport_{branch.code}_{label}_{today.isoformat()}.xlsx",
    )


# =============================================================
# DONS / DONATIONS
# =============================================================

@manager_required
@require_POST
def donation_create(request):
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

    return render(
        request,
        "accounts/dashboard/partials/donation_row.html",
        {"donation": donation},
    )
