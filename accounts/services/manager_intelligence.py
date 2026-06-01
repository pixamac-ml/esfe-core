from datetime import datetime
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from academics.models import LessonLog
from accounts.models import (
    BranchBankTransfer,
    BranchCashMovement,
    BranchExpense,
    BranchMonthlyClosure,
    PayrollEntry,
    Profile,
    TeacherHonorariumEntry,
)
from accounts.services.accounting_documents import create_cash_movement
from communication.models import CommunicationNotification
from communication.services import NotificationService
from inscriptions.models import Inscription
from payments.models import Payment


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
    return max(cash_in - cash_out, 0)


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
    existing_notification = CommunicationNotification.objects.filter(
        recipient=entry.teacher,
        event_type="teacher_honorarium_available",
        legacy_source="teacher_honorarium_entry",
        legacy_object_id=str(entry.pk),
    ).exists()
    if existing_notification:
        return False
    NotificationService.notify_user(
        recipient=entry.teacher,
        actor=actor,
        event_type="teacher_honorarium_available",
        title="Honoraire disponible",
        body=(
            f"Votre honoraire {entry.period_month:%m/%Y} est pret. "
            "Il peut etre consulte et retire selon la caisse disponible."
        ),
        source_app="accounts",
        channels=(CommunicationNotification.CHANNEL_IN_APP, CommunicationNotification.CHANNEL_WEBSOCKET),
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
    existing_notification = CommunicationNotification.objects.filter(
        recipient=payroll_entry.employee,
        event_type="salary_available",
        legacy_source="payroll_entry",
        legacy_object_id=str(payroll_entry.pk),
    ).exists()
    if existing_notification:
        return False
    NotificationService.notify_user(
        recipient=payroll_entry.employee,
        actor=actor,
        event_type="salary_available",
        title="Salaire disponible",
        body=(
            f"Votre fiche de paie {payroll_entry.period_month:%m/%Y} est validee. "
            "Vous pouvez passer pour le retrait selon la disponibilite caisse."
        ),
        source_app="accounts",
        channels=(CommunicationNotification.CHANNEL_IN_APP, CommunicationNotification.CHANNEL_WEBSOCKET),
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
