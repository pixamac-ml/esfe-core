from datetime import date

from django.db.models import Sum
from django.utils import timezone

from accounts.models import BranchCashMovement, PayrollEntry


MONTH_LABELS = (
    "janvier", "fevrier", "mars", "avril", "mai", "juin",
    "juillet", "aout", "septembre", "octobre", "novembre", "decembre",
)


def parse_salary_period(raw_value):
    raw_value = (raw_value or "").strip()
    try:
        parsed = date.fromisoformat(f"{raw_value}-01") if raw_value else timezone.localdate()
    except ValueError:
        parsed = timezone.localdate()
    return parsed.replace(day=1)


def _shift_month(period, delta):
    month_index = period.year * 12 + period.month - 1 + delta
    return date(month_index // 12, month_index % 12 + 1, 1)


def _payment_movements(entry):
    if entry is None:
        return BranchCashMovement.objects.none()
    prefix = f"PAYROLL-{entry.pk}"
    return BranchCashMovement.objects.filter(
        branch=entry.branch,
        source=BranchCashMovement.SOURCE_PAYROLL,
        source_reference__startswith=prefix,
    ).order_by("-movement_date", "-created_at")


def build_director_salary_context(*, user, branch, period_month):
    """Build a read-only salary workspace for the authenticated employee only."""
    period_month = parse_salary_period(period_month)
    entries = PayrollEntry.objects.select_related("branch", "employee", "employee__profile").filter(
        employee=user,
    )
    if branch is not None:
        entries = entries.filter(branch=branch)

    current_entry = entries.filter(period_month=period_month).first()
    history = entries.order_by("-period_month", "-id")
    year_totals = entries.filter(period_month__year=period_month.year).aggregate(
        gross=Sum("base_salary") + Sum("allowances"),
        deductions=Sum("deductions") + Sum("advances"),
        paid=Sum("paid_amount"),
    )
    payment_movements = _payment_movements(current_entry)
    latest_payment = payment_movements.first()

    return {
        "salary_period": period_month,
        "salary_period_value": period_month.strftime("%Y-%m"),
        "salary_period_label": f"{MONTH_LABELS[period_month.month - 1]} {period_month.year}",
        "salary_prev_period": _shift_month(period_month, -1).strftime("%Y-%m"),
        "salary_next_period": _shift_month(period_month, 1).strftime("%Y-%m"),
        "salary_entry": current_entry,
        "salary_history_rows": history,
        "salary_payment_movements": payment_movements,
        "salary_latest_payment": latest_payment,
        "salary_reference": (
            f"SAL-{current_entry.period_month:%Y%m}-{current_entry.pk:05d}"
            if current_entry else ""
        ),
        "salary_year_totals": {
            "gross": year_totals.get("gross") or 0,
            "deductions": year_totals.get("deductions") or 0,
            "paid": year_totals.get("paid") or 0,
        },
    }
