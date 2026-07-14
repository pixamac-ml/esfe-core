from calendar import monthrange
from datetime import datetime
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from academics.models import LessonLog
from accounts.models import (
    BranchExpense,
    BranchBankTransfer,
    BranchCashMovement,
    BranchMonthlyClosure,
    Donation,
    PayrollEntry,
    Profile,
    TeacherHonorariumEntry,
)
from accounts.services.accounting_documents import create_cash_movement
from notifier.models import NotificationMessage
from notifier.services import NotificationBus
from inscriptions.models import Inscription
from payments.models import Payment
from shop.models import ShopPayment
from branches.models import Branch


PAYROLL_REFERENCE_PREFIX = "PAYROLL-"
PAYMENT_REFERENCE_PREFIX = "PAY-"


def payment_cash_reference(payment):
    if payment.reference:
        return payment.reference
    return f"{PAYMENT_REFERENCE_PREFIX}{payment.pk}"


def payroll_cash_reference(payroll_entry, amount=None):
    suffix = f"-{amount}" if amount else ""
    return f"{PAYROLL_REFERENCE_PREFIX}{payroll_entry.pk}{suffix}"


def get_branch_cash_balance(branch):
    movements = BranchCashMovement.objects.filter(branch=branch)
    cash_in = movements.filter(
        movement_type=BranchCashMovement.TYPE_IN,
    ).aggregate(total=Sum("amount"))["total"] or 0
    cash_out = movements.filter(
        movement_type=BranchCashMovement.TYPE_OUT,
    ).aggregate(total=Sum("amount"))["total"] or 0
    return cash_in - cash_out


def lock_branch_cash_balance(branch):
    """Sérialise une sortie de caisse sur l'annexe puis retourne le solde réel."""
    locked_branch = Branch.objects.select_for_update().get(pk=branch.pk)
    return locked_branch, get_branch_cash_balance(locked_branch)


def sync_student_payment_cash_movements(branch, user):
    payments = (
        Payment.objects
        .filter(
            inscription__candidature__branch=branch,
            inscription__candidature__is_deleted=False,
            inscription__is_archived=False,
            status=Payment.STATUS_VALIDATED,
        )
        .select_related("inscription", "inscription__candidature")
    )
    created = 0
    for payment in payments:
        reference = payment_cash_reference(payment)
        movement = BranchCashMovement.objects.filter(
            branch=branch,
            source=BranchCashMovement.SOURCE_STUDENT_PAYMENT,
            source_reference=reference,
        ).first()
        if movement:
            continue
        create_cash_movement(
            branch=branch,
            source=BranchCashMovement.SOURCE_STUDENT_PAYMENT,
            source_reference=reference,
            movement_type=BranchCashMovement.TYPE_IN,
            amount=payment.amount,
            label=f"Paiement etudiant - {payment.inscription.candidature.full_name}",
            movement_date=payment.paid_at.date() if payment.paid_at else timezone.localdate(),
            notes=f"Synchronisation automatique paiement #{payment.pk}.",
            created_by=user,
        )
        created += 1
    return {"created": created, "scanned": payments.count()}


def _branch_month_bounds(period_month):
    if not period_month:
        return None, None
    period_end = period_month.replace(day=monthrange(period_month.year, period_month.month)[1])
    return period_month, period_end


def _movement_source_reference_exists(*, branch, source, source_reference):
    if not source_reference:
        return False
    return BranchCashMovement.objects.filter(
        branch=branch,
        source=source,
        source_reference=source_reference,
    ).exists()


def sync_donation_cash_movement(donation, user=None):
    with transaction.atomic():
        donation = Donation.objects.select_for_update().select_related("branch").get(pk=donation.pk)
        if donation.branch_id is None:
            raise ValidationError("Le don doit appartenir a une annexe valide.")
        source_reference = f"donation:{donation.pk}"
        movement, _created = BranchCashMovement.objects.update_or_create(
            branch=donation.branch,
            source=BranchCashMovement.SOURCE_DONATION,
            source_reference=source_reference,
            defaults={
                "movement_type": BranchCashMovement.TYPE_IN,
                "amount": donation.amount,
                "label": f"Don de {donation.donor_name}",
                "movement_date": donation.date,
                "notes": donation.description or "",
                "created_by": user or donation.created_by,
            },
        )
        if donation.cash_movement_id != movement.pk:
            donation.cash_movement = movement
            donation.save(update_fields=["cash_movement", "updated_at"])
        if not movement.reference or not movement.receipt_number or not movement.receipt_pdf:
            from accounts.services.accounting_documents import finalize_cash_movement_document

            finalize_cash_movement_document(movement)
        return movement


def sync_bank_transfer_cash_movement(transfer, user=None):
    with transaction.atomic():
        transfer = (
            BranchBankTransfer.objects
            .select_for_update()
            .select_related("branch", "closure")
            .get(pk=transfer.pk)
        )
        if transfer.branch_id != transfer.closure.branch_id:
            raise ValidationError("Le versement bancaire ne correspond pas a l'annexe de la cloture.")
        source_reference = f"bank_transfer:{transfer.pk}"
        movement, _created = BranchCashMovement.objects.update_or_create(
            branch=transfer.branch,
            source=BranchCashMovement.SOURCE_BANK_TRANSFER,
            source_reference=source_reference,
            defaults={
                "movement_type": BranchCashMovement.TYPE_OUT,
                "amount": transfer.amount,
                "label": f"Versement bancaire - {transfer.bank_name}",
                "movement_date": transfer.transfer_date,
                "notes": transfer.comment or f"Versement bancaire vers {transfer.bank_name}.",
                "created_by": user or transfer.created_by,
            },
        )
        if not movement.reference or not movement.receipt_number or not movement.receipt_pdf:
            from accounts.services.accounting_documents import finalize_cash_movement_document

            finalize_cash_movement_document(movement)
        return movement


def branch_financial_orphan_report(branch, period_month=None):
    start_date, end_date = _branch_month_bounds(period_month)

    payments = Payment.objects.filter(
        inscription__candidature__branch=branch,
        inscription__candidature__is_deleted=False,
        inscription__is_archived=False,
        status=Payment.STATUS_VALIDATED,
    )
    if start_date and end_date:
        payments = payments.filter(paid_at__date__range=(start_date, end_date))

    shop_payments = ShopPayment.objects.filter(order__branch=branch, status=ShopPayment.STATUS_VALIDATED)
    if start_date and end_date:
        shop_payments = shop_payments.filter(paid_at__date__range=(start_date, end_date))

    donations = Donation.objects.filter(branch=branch)
    if start_date and end_date:
        donations = donations.filter(date__range=(start_date, end_date))

    expenses = BranchExpense.objects.filter(branch=branch, status=BranchExpense.STATUS_PAID)
    if start_date and end_date:
        expenses = expenses.filter(paid_at__date__range=(start_date, end_date))

    payroll_entries = PayrollEntry.objects.filter(
        branch=branch,
        status__in=[PayrollEntry.STATUS_PAID, PayrollEntry.STATUS_PARTIAL],
        paid_amount__gt=0,
    )
    if period_month:
        payroll_entries = payroll_entries.filter(period_month=period_month)

    honorarium_entries = TeacherHonorariumEntry.objects.filter(
        branch=branch,
        status__in=[TeacherHonorariumEntry.STATUS_PAID, TeacherHonorariumEntry.STATUS_PARTIAL],
        paid_amount__gt=0,
    )
    if period_month:
        honorarium_entries = honorarium_entries.filter(period_month=period_month)

    bank_transfers = BranchBankTransfer.objects.filter(branch=branch)
    if start_date and end_date:
        bank_transfers = bank_transfers.filter(transfer_date__range=(start_date, end_date))

    orphan_payments = []
    for payment in payments.select_related("inscription", "inscription__candidature"):
        source_reference = payment_cash_reference(payment)
        if not _movement_source_reference_exists(
            branch=branch,
            source=BranchCashMovement.SOURCE_STUDENT_PAYMENT,
            source_reference=source_reference,
        ):
            orphan_payments.append(payment)

    orphan_shop_payments = []
    for payment in shop_payments.select_related("order", "order__branch"):
        source_reference = payment.reference or f"shop_payment:{payment.pk}"
        if not _movement_source_reference_exists(
            branch=branch,
            source=BranchCashMovement.SOURCE_SHOP,
            source_reference=source_reference,
        ):
            orphan_shop_payments.append(payment)

    orphan_donations = list(
        donations.filter(cash_movement__isnull=True).select_related("branch")
    )

    orphan_expenses = []
    for expense in expenses.select_related("branch"):
        source_reference = expense.reference or f"expense:{expense.pk}"
        if not _movement_source_reference_exists(
            branch=branch,
            source=BranchCashMovement.SOURCE_EXPENSE,
            source_reference=source_reference,
        ):
            orphan_expenses.append(expense)

    orphan_payroll_entries = []
    for entry in payroll_entries.select_related("employee"):
        source_reference_prefix = f"PAYROLL-{entry.pk}"
        if not BranchCashMovement.objects.filter(
            branch=branch,
            source=BranchCashMovement.SOURCE_PAYROLL,
        ).filter(
            Q(source_reference=source_reference_prefix) | Q(source_reference__startswith=f"{source_reference_prefix}-")
        ).exists():
            orphan_payroll_entries.append(entry)

    orphan_honorarium_entries = []
    for entry in honorarium_entries.select_related("teacher"):
        source_reference_prefix = f"HON-{entry.pk}"
        if not BranchCashMovement.objects.filter(
            branch=branch,
            source=BranchCashMovement.SOURCE_HONORARIUM,
        ).filter(
            Q(source_reference=source_reference_prefix) | Q(source_reference__startswith=f"{source_reference_prefix}-")
        ).exists():
            orphan_honorarium_entries.append(entry)

    orphan_bank_transfers = []
    for transfer in bank_transfers.select_related("closure"):
        source_reference = f"bank_transfer:{transfer.pk}"
        if not _movement_source_reference_exists(
            branch=branch,
            source=BranchCashMovement.SOURCE_BANK_TRANSFER,
            source_reference=source_reference,
        ):
            orphan_bank_transfers.append(transfer)

    return {
        "payments": orphan_payments,
        "shop_payments": orphan_shop_payments,
        "donations": orphan_donations,
        "expenses": orphan_expenses,
        "payroll_entries": orphan_payroll_entries,
        "honorarium_entries": orphan_honorarium_entries,
        "bank_transfers": orphan_bank_transfers,
    }


def reconcile_branch_financial_movements(branch, user=None, *, period_month=None, repair=True):
    report = branch_financial_orphan_report(branch, period_month=period_month)
    if not repair:
        return {
            "created": 0,
            "report": report,
        }

    created = 0
    for payment in report["payments"]:
        source_reference = payment_cash_reference(payment)
        if _movement_source_reference_exists(
            branch=branch,
            source=BranchCashMovement.SOURCE_STUDENT_PAYMENT,
            source_reference=source_reference,
        ):
            continue
        create_cash_movement(
            branch=branch,
            source=BranchCashMovement.SOURCE_STUDENT_PAYMENT,
            source_reference=source_reference,
            movement_type=BranchCashMovement.TYPE_IN,
            amount=payment.amount,
            label=f"Paiement etudiant - {payment.inscription.candidature.full_name}",
            movement_date=payment.paid_at.date() if payment.paid_at else timezone.localdate(),
            notes=f"Reconciliation automatique paiement #{payment.pk}.",
            created_by=user or getattr(getattr(payment, "agent", None), "user", None),
        )
        created += 1

    for payment in report["shop_payments"]:
        source_reference = payment.reference or f"shop_payment:{payment.pk}"
        if _movement_source_reference_exists(
            branch=branch,
            source=BranchCashMovement.SOURCE_SHOP,
            source_reference=source_reference,
        ):
            continue
        create_cash_movement(
            branch=branch,
            movement_type=BranchCashMovement.TYPE_IN,
            source=BranchCashMovement.SOURCE_SHOP,
            amount=payment.amount,
            label=f"Vente boutique - {payment.order.reference}",
            movement_date=payment.paid_at.date(),
            source_reference=source_reference,
            notes=f"Reconciliation automatique boutique commande {payment.order.reference}.",
            created_by=user or payment.created_by,
        )
        created += 1

    for donation in report["donations"]:
        sync_donation_cash_movement(donation, user=user)
        created += 1

    for expense in report["expenses"]:
        source_reference = expense.reference or None
        if not source_reference:
            source_reference = ensure_expense_reference(expense)
        if _movement_source_reference_exists(
            branch=branch,
            source=BranchCashMovement.SOURCE_EXPENSE,
            source_reference=source_reference,
        ):
            continue
        create_cash_movement(
            branch=branch,
            movement_type=BranchCashMovement.TYPE_OUT,
            source=BranchCashMovement.SOURCE_EXPENSE,
            amount=expense.amount,
            label=expense.title,
            movement_date=expense.expense_date,
            expense=expense,
            source_reference=source_reference,
            notes=expense.notes,
            created_by=user or expense.created_by,
        )
        created += 1

    for entry in report["payroll_entries"]:
        source_reference = payroll_cash_reference(entry, entry.paid_amount)
        if BranchCashMovement.objects.filter(
            branch=branch,
            source=BranchCashMovement.SOURCE_PAYROLL,
            source_reference=source_reference,
        ).exists():
            continue
        create_cash_movement(
            branch=branch,
            movement_type=BranchCashMovement.TYPE_OUT,
            source=BranchCashMovement.SOURCE_PAYROLL,
            amount=entry.paid_amount,
            label=f"Salaire - {entry.employee.get_full_name() or entry.employee.username}",
            movement_date=timezone.localdate(),
            source_reference=source_reference,
            notes=f"Reconciliation automatique paie {entry.period_month:%Y-%m}.",
            created_by=user or entry.updated_by or entry.created_by,
        )
        created += 1

    for entry in report["honorarium_entries"]:
        source_reference = f"HON-{entry.pk}-{entry.paid_amount}"
        if BranchCashMovement.objects.filter(
            branch=branch,
            source=BranchCashMovement.SOURCE_HONORARIUM,
            source_reference=source_reference,
        ).exists():
            continue
        create_cash_movement(
            branch=branch,
            movement_type=BranchCashMovement.TYPE_OUT,
            source=BranchCashMovement.SOURCE_HONORARIUM,
            amount=entry.paid_amount,
            label=f"Honoraire - {entry.teacher.get_full_name() or entry.teacher.username}",
            movement_date=timezone.localdate(),
            source_reference=source_reference,
            notes=f"Reconciliation automatique honoraires {entry.period_month:%Y-%m}.",
            created_by=user or entry.updated_by or entry.created_by,
        )
        created += 1

    for transfer in report["bank_transfers"]:
        sync_bank_transfer_cash_movement(transfer, user=user)
        created += 1

    return {
        "created": created,
        "report": branch_financial_orphan_report(branch, period_month=period_month),
    }


def prepare_missing_payroll_entries(branch, period_month, user):
    staff_profiles = (
        Profile.objects
        .select_related("user")
        .filter(branch=branch, user__is_active=True, employment_status="active")
        .exclude(position="student")
        .exclude(position="teacher")
        .exclude(user_type="public")
    )
    created = 0
    skipped_without_salary = 0
    for profile in staff_profiles:
        if profile.salary_base <= 0:
            skipped_without_salary += 1
            continue
        _, was_created = PayrollEntry.objects.get_or_create(
            branch=branch,
            employee=profile.user,
            period_month=period_month,
            defaults={
                "base_salary": profile.salary_base,
                "allowances": 0,
                "deductions": 0,
                "advances": 0,
                "paid_amount": 0,
                "status": PayrollEntry.STATUS_DRAFT,
                "created_by": user,
                "updated_by": user,
                "notes": "Paie pre-calculee automatiquement depuis le profil employe.",
            },
        )
        if was_created:
            created += 1
    return {"created": created, "skipped_without_salary": skipped_without_salary}


def _teacher_honorarium_hours(branch, teacher, period_month):
    logs = LessonLog.objects.filter(
        branch=branch,
        teacher=teacher,
        date__year=period_month.year,
        date__month=period_month.month,
        status=LessonLog.STATUS_DONE,
        validated_by__isnull=False,
    )
    total_minutes = 0
    for log in logs:
        start = datetime.combine(period_month, log.start_time)
        end = datetime.combine(period_month, log.end_time)
        if end <= start:
            continue
        total_minutes += int((end - start).total_seconds() // 60)
    return Decimal(total_minutes) / Decimal(60)


def refresh_teacher_honorarium_entry(branch, teacher, period_month, user=None):
    """Recalcule la fiche honoraire d'un enseignant pour un mois donné.

    Cette fonction est conçue pour être appelée automatiquement après chaque
    modification d'un cahier de texte (création, mise à jour, suppression).
    Elle ne modifie jamais une fiche déjà payée ou partiellement payée.
    """
    from accounts.models import Profile

    profile = Profile.objects.filter(user=teacher, branch=branch).first()
    if not profile or profile.teacher_hourly_rate <= 0:
        return None

    validated_hours = _teacher_honorarium_hours(branch, teacher, period_month)
    entry = TeacherHonorariumEntry.objects.filter(
        branch=branch,
        teacher=teacher,
        period_month=period_month,
    ).first()

    if entry is None:
        if validated_hours <= 0:
            return None
        return TeacherHonorariumEntry.objects.create(
            branch=branch,
            teacher=teacher,
            period_month=period_month,
            hourly_rate=profile.teacher_hourly_rate,
            validated_hours=validated_hours,
            adjustments=0,
            deductions=0,
            advances=0,
            paid_amount=0,
            status=TeacherHonorariumEntry.STATUS_DRAFT,
            created_by=user,
            updated_by=user,
            notes="Honoraire pre-calcule automatiquement depuis les cours valides.",
        )

    if entry.status in {TeacherHonorariumEntry.STATUS_PAID, TeacherHonorariumEntry.STATUS_PARTIAL}:
        return entry

    entry.hourly_rate = profile.teacher_hourly_rate
    entry.validated_hours = validated_hours
    entry.updated_by = user
    entry.save()
    return entry


def prepare_missing_teacher_honorarium_entries(branch, period_month, user):
    teacher_profiles = (
        Profile.objects
        .select_related("user")
        .filter(
            branch=branch,
            user__is_active=True,
            employment_status="active",
            position="teacher",
        )
        .exclude(user_type="public")
    )
    created = 0
    skipped_without_rate = 0
    for profile in teacher_profiles:
        if profile.teacher_hourly_rate <= 0:
            skipped_without_rate += 1
            continue
        validated_hours = _teacher_honorarium_hours(branch, profile.user, period_month)
        entry, was_created = TeacherHonorariumEntry.objects.get_or_create(
            branch=branch,
            teacher=profile.user,
            period_month=period_month,
            defaults={
                "hourly_rate": profile.teacher_hourly_rate,
                "validated_hours": validated_hours,
                "adjustments": 0,
                "deductions": 0,
                "advances": 0,
                "paid_amount": 0,
                "status": TeacherHonorariumEntry.STATUS_DRAFT,
                "created_by": user,
                "updated_by": user,
                "notes": "Honoraire pre-calcule automatiquement depuis les cours valides.",
            },
        )
        if not was_created:
            entry.hourly_rate = profile.teacher_hourly_rate
            entry.validated_hours = validated_hours
            entry.updated_by = user
            entry.save()
        else:
            created += 1
    return {"created": created, "skipped_without_rate": skipped_without_rate}


def notify_teacher_honorarium_available(entry, actor):
    existing_notification = NotificationMessage.objects.filter(
        recipient=entry.teacher,
        event_type="teacher_honorarium_available",
        legacy_source="teacher_honorarium_entry",
        legacy_object_id=str(entry.pk),
    ).exists()
    if existing_notification:
        return False
    NotificationBus.notify(
        recipient=entry.teacher,
        actor=actor,
        event_type="teacher_honorarium_available",
        title="Honoraire disponible",
        body=(
            f"Votre honoraire {entry.period_month:%m/%Y} est pret. "
            "Il peut etre consulte et retire selon la caisse disponible."
        ),
        source_app="accounts",
        channels=(NotificationMessage.CHANNEL_IN_APP, NotificationMessage.CHANNEL_WEBSOCKET),
        metadata={
            "honorarium_entry_id": entry.pk,
            "branch_id": entry.branch_id,
            "period_month": entry.period_month.isoformat(),
        },
        legacy_source="teacher_honorarium_entry",
        legacy_object_id=str(entry.pk),
    )
    return True


def mark_ready_teacher_honorarium_entries_available(branch, period_month, user):
    entries = (
        TeacherHonorariumEntry.objects
        .select_related("teacher")
        .filter(
            branch=branch,
            period_month=period_month,
            status=TeacherHonorariumEntry.STATUS_READY,
        )
    )
    notified_count = 0
    for entry in entries:
        if entry.remaining_amount <= 0:
            continue
        if notify_teacher_honorarium_available(entry, user):
            notified_count += 1
    return {"ready_count": entries.count(), "notified_count": notified_count}


def pay_ready_teacher_honorarium_entries(branch, period_month, user):
    with transaction.atomic():
        available_cash = get_branch_cash_balance(branch)
        entries = (
            TeacherHonorariumEntry.objects
            .select_for_update()
            .select_related("teacher")
            .filter(
                branch=branch,
                period_month=period_month,
                status__in=[TeacherHonorariumEntry.STATUS_READY, TeacherHonorariumEntry.STATUS_PARTIAL],
            )
        )
        paid_count = 0
        paid_amount = 0
        for entry in entries:
            amount = entry.remaining_amount
            if amount <= 0:
                continue
            if available_cash < amount:
                break
            entry.paid_amount += amount
            entry.updated_by = user
            entry.save()
            create_cash_movement(
                branch=branch,
                movement_type=BranchCashMovement.TYPE_OUT,
                source=BranchCashMovement.SOURCE_HONORARIUM,
                amount=amount,
                label=f"Honoraire - {entry.teacher.get_full_name() or entry.teacher.username}",
                movement_date=timezone.localdate(),
                source_reference=f"HON-{entry.pk}-{amount}",
                notes=f"Paiement automatique des honoraires {entry.period_month:%Y-%m}.",
                created_by=user,
            )
            available_cash -= amount
            paid_count += 1
            paid_amount += amount
    return {
        "paid_count": paid_count,
        "paid_amount": paid_amount,
        "remaining_cash": available_cash,
    }


def build_monthly_closure_snapshot(
    *,
    branch,
    period_month,
    total_entries,
    total_exits,
    student_revenue,
    shop_revenue,
    salary_paid,
    honorarium_paid,
    expenses_paid,
    bank_transfer_amount=0,
    status=BranchMonthlyClosure.STATUS_DRAFT,
    notes="",
):
    return {
        "branch": branch,
        "period_month": period_month,
        "total_entries": total_entries,
        "total_exits": total_exits,
        "student_revenue": student_revenue,
        "shop_revenue": shop_revenue,
        "salary_paid": salary_paid,
        "honorarium_paid": honorarium_paid,
        "expenses_paid": expenses_paid,
        "result_amount": total_entries - total_exits,
        "bank_transfer_amount": bank_transfer_amount,
        "status": status,
        "notes": notes,
    }


def notify_salary_available(payroll_entry, actor):
    existing_notification = NotificationMessage.objects.filter(
        recipient=payroll_entry.employee,
        event_type="salary_available",
        legacy_source="payroll_entry",
        legacy_object_id=str(payroll_entry.pk),
    ).exists()
    if existing_notification:
        return False
    NotificationBus.notify(
        recipient=payroll_entry.employee,
        actor=actor,
        event_type="salary_available",
        title="Salaire disponible",
        body=(
            f"Votre fiche de paie {payroll_entry.period_month:%m/%Y} est validee. "
            "Vous pouvez passer pour le retrait selon la disponibilite caisse."
        ),
        source_app="accounts",
        channels=(NotificationMessage.CHANNEL_IN_APP, NotificationMessage.CHANNEL_WEBSOCKET),
        metadata={
            "payroll_entry_id": payroll_entry.pk,
            "branch_id": payroll_entry.branch_id,
            "period_month": payroll_entry.period_month.isoformat(),
        },
        legacy_source="payroll_entry",
        legacy_object_id=str(payroll_entry.pk),
    )
    return True


def mark_ready_payroll_entries_available(branch, period_month, user):
    entries = (
        PayrollEntry.objects
        .select_related("employee")
        .filter(
            branch=branch,
            period_month=period_month,
            status=PayrollEntry.STATUS_READY,
        )
    )
    notified_count = 0
    for entry in entries:
        if entry.remaining_salary <= 0:
            continue
        if notify_salary_available(entry, user):
            notified_count += 1
    return {"ready_count": entries.count(), "notified_count": notified_count}


def pay_ready_payroll_entries(branch, period_month, user):
    with transaction.atomic():
        available_cash = get_branch_cash_balance(branch)
        entries = (
            PayrollEntry.objects
            .select_for_update()
            .select_related("employee")
            .filter(
                branch=branch,
                period_month=period_month,
                status__in=[PayrollEntry.STATUS_READY, PayrollEntry.STATUS_PARTIAL],
            )
        )
        paid_count = 0
        paid_amount = 0
        for entry in entries:
            amount = entry.remaining_salary
            if amount <= 0:
                continue
            if available_cash < amount:
                break
            entry.paid_amount += amount
            entry.updated_by = user
            entry.save()
            create_cash_movement(
                branch=branch,
                movement_type=BranchCashMovement.TYPE_OUT,
                source=BranchCashMovement.SOURCE_PAYROLL,
                amount=amount,
                label=f"Salaire - {entry.employee.get_full_name() or entry.employee.username}",
                movement_date=timezone.localdate(),
                source_reference=payroll_cash_reference(entry, amount),
                notes=f"Paiement automatique de la paie {entry.period_month:%Y-%m}.",
                created_by=user,
            )
            available_cash -= amount
            paid_count += 1
            paid_amount += amount
    return {
        "paid_count": paid_count,
        "paid_amount": paid_amount,
        "remaining_cash": available_cash,
    }


def build_manager_intelligence_context(
    *,
    branch,
    payroll_month,
    base_payments,
    base_inscriptions,
    payroll_stats,
    honorarium_stats,
    expense_stats,
    cash_stats,
    branch_staff_user_ids,
    branch_teacher_user_ids,
):
    synced_payment_refs = set(BranchCashMovement.objects.filter(
        branch=branch,
        source=BranchCashMovement.SOURCE_STUDENT_PAYMENT,
    ).values_list("source_reference", flat=True))
    validated_payments = list(base_payments.filter(status=Payment.STATUS_VALIDATED))
    unsynced_payments_count = sum(
        1 for payment in validated_payments
        if payment_cash_reference(payment) not in synced_payment_refs
    )

    missing_payroll_count = max(len(branch_staff_user_ids) - payroll_stats["prepared"], 0)
    missing_honorarium_count = max(len(branch_teacher_user_ids) - honorarium_stats["prepared"], 0)
    ready_payroll_amount = sum(
        entry.remaining_salary
        for entry in PayrollEntry.objects.filter(
            branch=branch,
            period_month=payroll_month,
            status=PayrollEntry.STATUS_READY,
        )
    )
    ready_honorarium_amount = sum(
        entry.remaining_amount
        for entry in TeacherHonorariumEntry.objects.filter(
            branch=branch,
            period_month=payroll_month,
            status=TeacherHonorariumEntry.STATUS_READY,
        )
    )
    approved_expenses = BranchExpense.objects.filter(
        branch=branch,
        status=BranchExpense.STATUS_APPROVED,
    )
    approved_expense_amount = approved_expenses.aggregate(total=Sum("amount"))["total"] or 0
    balance_after_commitments = (
        cash_stats["estimated_month_balance"]
        - payroll_stats["remaining_total"]
        - honorarium_stats["remaining_total"]
        - expense_stats["pending_amount"]
    )

    priorities = []
    if unsynced_payments_count:
        priorities.append({
            "level": "high",
            "title": "Synchroniser les encaissements",
            "message": f"{unsynced_payments_count} paiement(s) valide(s) absent(s) du journal de caisse.",
            "section": "caisse",
        })
    if missing_payroll_count:
        priorities.append({
            "level": "high",
            "title": "Preparer les paies manquantes",
            "message": f"{missing_payroll_count} employe(s) actif(s) sans fiche de paie ce mois.",
            "section": "salaires",
        })
    if missing_honorarium_count:
        priorities.append({
            "level": "high",
            "title": "Preparer les honoraires enseignants",
            "message": f"{missing_honorarium_count} enseignant(s) actif(s) sans honoraire ce mois.",
            "section": "cloture",
        })
    if payroll_stats["remaining_total"]:
        priorities.append({
            "level": "medium",
            "title": "Regler les salaires restants",
            "message": f"{payroll_stats['remaining_total']:,} FCFA restent a payer sur la paie du mois.".replace(",", " "),
            "section": "salaires",
        })
    if honorarium_stats["remaining_total"]:
        priorities.append({
            "level": "medium",
            "title": "Regler les honoraires restants",
            "message": f"{honorarium_stats['remaining_total']:,} FCFA restent a payer sur les honoraires du mois.".replace(",", " "),
            "section": "cloture",
        })
    if approved_expenses.exists():
        priorities.append({
            "level": "medium",
            "title": "Payer les depenses approuvees",
            "message": f"{approved_expenses.count()} depense(s) approuvee(s), {approved_expense_amount:,} FCFA a sortir.".replace(",", " "),
            "section": "depenses",
        })
    if base_inscriptions.filter(status=Inscription.STATUS_AWAITING_PAYMENT).exists():
        priorities.append({
            "level": "low",
            "title": "Relancer les soldes etudiants",
            "message": f"{base_inscriptions.filter(status=Inscription.STATUS_AWAITING_PAYMENT).count()} inscription(s) attendent un premier paiement.",
            "section": "inscriptions",
        })

    alerts = []
    if cash_stats["estimated_month_balance"] < 0:
        alerts.append({
            "level": "danger",
            "message": "Le solde estime de caisse est negatif.",
        })
    if balance_after_commitments < 0:
        alerts.append({
            "level": "danger",
            "message": "La caisse estimee ne couvre pas les salaires, honoraires et depenses en attente.",
        })
    if ready_payroll_amount > cash_stats.get("available_balance", 0):
        alerts.append({
            "level": "warning",
            "message": "La caisse disponible ne couvre pas toutes les fiches de paie deja disponibles.",
        })
    if ready_honorarium_amount > cash_stats.get("available_balance", 0):
        alerts.append({
            "level": "warning",
            "message": "La caisse disponible ne couvre pas tous les honoraires enseignants deja disponibles.",
        })
    if expense_stats["pending_amount"] > cash_stats["estimated_month_balance"] and expense_stats["pending_amount"] > 0:
        alerts.append({
            "level": "warning",
            "message": "Les depenses en attente depassent le solde estime disponible.",
        })

    return {
        "priorities": priorities[:6],
        "alerts": alerts,
        "unsynced_payments_count": unsynced_payments_count,
        "missing_payroll_count": missing_payroll_count,
        "missing_honorarium_count": missing_honorarium_count,
        "approved_expenses_count": approved_expenses.count(),
        "approved_expense_amount": approved_expense_amount,
        "ready_payroll_amount": ready_payroll_amount,
        "ready_honorarium_amount": ready_honorarium_amount,
        "balance_after_commitments": balance_after_commitments,
    }
