from datetime import date

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from django.db.models import Q

from admissions.models import Candidature
from accounts.forms import BranchCashMovementForm, BranchExpenseForm, PayrollEntryForm
from accounts.models import BranchCashMovement, BranchExpense, PayrollEntry, Profile
from accounts.services.accounting_documents import (
    create_cash_movement,
    ensure_expense_reference,
    ensure_cash_movement_receipt,
    finalize_cash_movement_document,
)
from accounts.services.manager_intelligence import (
    payment_cash_reference,
    pay_ready_payroll_entries,
    payroll_cash_reference,
    prepare_missing_payroll_entries,
    sync_student_payment_cash_movements,
)
from inscriptions.models import Inscription
from payments.models import CashPaymentSession, Payment, PaymentAgent

from accounts.dashboards.helpers import get_user_branch, is_manager


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


def manager_salary_redirect_response(period_month):
    response = HttpResponse("")
    response["HX-Redirect"] = (
        f"{reverse('accounts:manager_dashboard')}?section=salaires&salary_month={period_month.strftime('%Y-%m')}"
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
def candidature_accept(request, pk):
    candidature = get_object_or_404(Candidature, pk=pk, branch=request.branch)
    candidature.status = "accepted"
    candidature.reviewed_at = timezone.now()
    candidature.reviewed_by = request.user
    candidature.save(update_fields=["status", "reviewed_at", "reviewed_by"])
    return render(
        request,
        "accounts/dashboard/partials/manager_candidature_row.html",
        {"candidature": candidature},
    )


@manager_required
@require_POST
def candidature_reject(request, pk):
    candidature = get_object_or_404(Candidature, pk=pk, branch=request.branch)
    candidature.status = "rejected"
    candidature.rejection_reason = request.POST.get("reason", "")
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
    candidature.completion_message = request.POST.get("message", "")
    candidature.reviewed_at = timezone.now()
    candidature.reviewed_by = request.user
    candidature.save(update_fields=["status", "completion_message", "reviewed_at", "reviewed_by"])
    return render(
        request,
        "accounts/dashboard/partials/manager_candidature_row.html",
        {"candidature": candidature},
    )


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

    amount = candidature.programme.get_inscription_amount_for_year(candidature.entry_year) or 500000
    inscription = Inscription.objects.create(
        candidature=candidature,
        amount_due=amount,
        status=Inscription.STATUS_AWAITING_PAYMENT,
    )
    return render(
        request,
        "accounts/dashboard/partials/inscription_created.html",
        {
            "inscription": inscription,
            "candidature": candidature,
        },
    )


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
        {"payment": payment},
    )


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
    action = (request.POST.get("submit_action") or "draft").strip()
    if action == "ready" and entry.paid_amount == 0:
        entry.status = PayrollEntry.STATUS_READY
    elif entry.paid_amount == 0:
        entry.status = PayrollEntry.STATUS_DRAFT
    entry.save()

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
    result = pay_ready_payroll_entries(request.branch, payroll_month, request.user)
    return manager_section_notice_redirect_response(
        "salaires",
        f"salaires_payes_{result['paid_count']}",
    )


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
