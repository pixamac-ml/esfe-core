"""Garde-fous partages pour les ecritures financieres des annexes."""

from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from accounts.models import BranchCashRegisterSession, BranchMonthlyClosure, Profile
from notifier.models import NotificationMessage
from notifier.services import NotificationBus


FINAL_CLOSURE_STATUSES = {
    BranchMonthlyClosure.STATUS_VALIDATED,
    BranchMonthlyClosure.STATUS_CLOSED,
}
EXECUTIVE_POSITIONS = {"executive_director", "deputy_executive_director"}


class FinancialPeriodClosedError(ValidationError):
    """Raised when an operation would alter a validated accounting period."""


def month_start(value: date) -> date:
    return value.replace(day=1)


def get_finalized_closure(branch, operation_date: date):
    return BranchMonthlyClosure.objects.filter(
        branch=branch,
        period_month=month_start(operation_date),
        status__in=FINAL_CLOSURE_STATUSES,
    ).first()


def assert_financial_period_open(branch, operation_date: date | None = None) -> None:
    operation_date = operation_date or timezone.localdate()
    closure = get_finalized_closure(branch, operation_date)
    if closure:
        raise FinancialPeriodClosedError(
            "La periode {:%m/%Y} est {} : aucune ecriture ne peut y etre ajoutee ou modifiee. "
            "Utilisez une contre-ecriture dans une periode ouverte.".format(
                closure.period_month,
                closure.get_status_display().lower(),
            )
        )


def get_today_cash_register_session(branch, session_date: date | None = None):
    return BranchCashRegisterSession.objects.filter(
        branch=branch,
        session_date=session_date or timezone.localdate(),
    ).first()


def open_cash_register_session(*, branch, actor, opening_amount: int, notes: str = ""):
    """Open one daily physical-count session, serialized per annex."""
    if opening_amount < 0:
        raise ValidationError("Le fonds d'ouverture ne peut pas etre negatif.")

    from accounts.services.manager_intelligence import get_branch_cash_balance, lock_branch_cash_balance

    with transaction.atomic():
        locked_branch, system_balance = lock_branch_cash_balance(branch)
        assert_financial_period_open(locked_branch, timezone.localdate())
        session, created = BranchCashRegisterSession.objects.get_or_create(
            branch=locked_branch,
            session_date=timezone.localdate(),
            defaults={
                "opening_amount": opening_amount,
                "system_opening_balance": system_balance,
                "expected_amount": system_balance,
                "opening_notes": notes,
                "opened_by": actor,
            },
        )
        if not created:
            if session.status == BranchCashRegisterSession.STATUS_CLOSED:
                raise ValidationError("La caisse de ce jour est deja fermee.")
            return session, False
        return session, True


def close_cash_register_session(*, branch, actor, counted_amount: int, notes: str = ""):
    """Close the day and preserve the observed physical variance."""
    if counted_amount < 0:
        raise ValidationError("Le comptage de fermeture ne peut pas etre negatif.")

    from accounts.services.manager_intelligence import lock_branch_cash_balance

    with transaction.atomic():
        locked_branch, expected_amount = lock_branch_cash_balance(branch)
        assert_financial_period_open(locked_branch, timezone.localdate())
        try:
            session = BranchCashRegisterSession.objects.select_for_update().get(
                branch=locked_branch,
                session_date=timezone.localdate(),
            )
        except BranchCashRegisterSession.DoesNotExist as exc:
            raise ValidationError("Ouvrez d'abord la caisse avant de la fermer.") from exc
        if session.status != BranchCashRegisterSession.STATUS_OPEN:
            raise ValidationError("La caisse de ce jour est deja fermee.")
        session.expected_amount = expected_amount
        session.counted_amount = counted_amount
        session.difference_amount = counted_amount - expected_amount
        session.closing_notes = notes
        session.closed_by = actor
        session.closed_at = timezone.now()
        session.status = BranchCashRegisterSession.STATUS_CLOSED
        session.save(
            update_fields=[
                "expected_amount", "counted_amount", "difference_amount", "closing_notes",
                "closed_by", "closed_at", "status", "updated_at",
            ]
        )

    if session.difference_amount:
        notify_cash_register_variance(session=session, actor=actor)
    return session


def notify_cash_register_variance(*, session, actor) -> None:
    """Notify the executive team without leaking financial data across branches."""
    recipients = Profile.objects.select_related("user").filter(
        position__in=EXECUTIVE_POSITIONS,
        user__is_active=True,
    )
    direction = "surplus" if session.difference_amount > 0 else "manquant"
    amount = abs(session.difference_amount)
    for profile in recipients:
        NotificationBus.notify(
            recipient=profile.user,
            actor=actor,
            event_type="cash_register_variance",
            title="Ecart de caisse a verifier",
            body=(
                f"Annexe {session.branch.name}, {session.session_date:%d/%m/%Y} : "
                f"{direction} de {amount:,} FCFA lors de la fermeture."
            ),
            source_app="accounts",
            priority=NotificationMessage.PRIORITY_HIGH,
            channels=(
                NotificationMessage.CHANNEL_IN_APP,
                NotificationMessage.CHANNEL_WEBSOCKET,
            ),
            metadata={
                "branch_id": session.branch_id,
                "cash_register_session_id": session.pk,
                "difference_amount": session.difference_amount,
            },
            legacy_source="cash_register_session",
            legacy_object_id=str(session.pk),
        )
