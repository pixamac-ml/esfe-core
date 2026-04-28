from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from accounts.models import BranchCashMovement, BranchExpense, PayrollEntry, Profile
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
        _, was_created = BranchCashMovement.objects.get_or_create(
            branch=branch,
            source=BranchCashMovement.SOURCE_STUDENT_PAYMENT,
            reference=reference,
            defaults={
                "movement_type": BranchCashMovement.TYPE_IN,
                "amount": payment.amount,
                "label": f"Paiement etudiant - {payment.inscription.candidature.full_name}",
                "movement_date": payment.paid_at.date() if payment.paid_at else timezone.localdate(),
                "notes": f"Synchronisation automatique paiement #{payment.pk}.",
                "created_by": user,
            },
        )
        if was_created:
            created += 1
    return {"created": created, "scanned": payments.count()}


def prepare_missing_payroll_entries(branch, period_month, user):
    staff_profiles = (
        Profile.objects
        .select_related("user")
        .filter(branch=branch, user__is_active=True, employment_status="active")
        .exclude(position="student")
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
                "status": PayrollEntry.STATUS_READY,
                "created_by": user,
                "updated_by": user,
                "notes": "Paie preparee automatiquement depuis le profil employe.",
            },
        )
        if was_created:
            created += 1
    return {"created": created, "skipped_without_salary": skipped_without_salary}


def pay_ready_payroll_entries(branch, period_month, user):
    with transaction.atomic():
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
            entry.paid_amount += amount
            entry.updated_by = user
            entry.save()
            BranchCashMovement.objects.create(
                branch=branch,
                movement_type=BranchCashMovement.TYPE_OUT,
                source=BranchCashMovement.SOURCE_PAYROLL,
                amount=amount,
                label=f"Salaire - {entry.employee.get_full_name() or entry.employee.username}",
                movement_date=timezone.localdate(),
                reference=payroll_cash_reference(entry, amount),
                notes=f"Paiement automatique de la paie {entry.period_month:%Y-%m}.",
                created_by=user,
            )
            paid_count += 1
            paid_amount += amount
    return {"paid_count": paid_count, "paid_amount": paid_amount}


def build_manager_intelligence_context(
    *,
    branch,
    payroll_month,
    base_payments,
    base_inscriptions,
    payroll_stats,
    expense_stats,
    cash_stats,
    branch_staff_user_ids,
):
    synced_payment_refs = set(BranchCashMovement.objects.filter(
        branch=branch,
        source=BranchCashMovement.SOURCE_STUDENT_PAYMENT,
    ).values_list("reference", flat=True))
    validated_payments = list(base_payments.filter(status=Payment.STATUS_VALIDATED))
    unsynced_payments_count = sum(
        1 for payment in validated_payments
        if payment_cash_reference(payment) not in synced_payment_refs
    )

    missing_payroll_count = max(len(branch_staff_user_ids) - payroll_stats["prepared"], 0)
    ready_payroll_amount = sum(
        entry.remaining_salary
        for entry in PayrollEntry.objects.filter(
            branch=branch,
            period_month=payroll_month,
            status=PayrollEntry.STATUS_READY,
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
    if payroll_stats["remaining_total"]:
        priorities.append({
            "level": "medium",
            "title": "Regler les salaires restants",
            "message": f"{payroll_stats['remaining_total']:,} FCFA restent a payer sur la paie du mois.".replace(",", " "),
            "section": "salaires",
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
            "message": "La caisse estimee ne couvre pas les salaires restants et depenses en attente.",
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
        "approved_expenses_count": approved_expenses.count(),
        "approved_expense_amount": approved_expense_amount,
        "ready_payroll_amount": ready_payroll_amount,
        "balance_after_commitments": balance_after_commitments,
    }
