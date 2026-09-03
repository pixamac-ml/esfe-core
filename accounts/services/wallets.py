"""Wallets internes : affectations traçables sans double comptage de caisse."""

from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, F, IntegerField, Sum, When
from django.utils import timezone

from accounts.models import BranchWallet, BranchWalletEntry
from accounts.services.financial_integrity import assert_financial_period_open
from accounts.services.manager_intelligence import get_branch_cash_balance, lock_branch_cash_balance


def wallet_balance(wallet: BranchWallet) -> int:
    totals = wallet.entries.aggregate(
        total=Sum(Case(When(direction=BranchWalletEntry.DIRECTION_IN, then=F("amount")), When(direction=BranchWalletEntry.DIRECTION_OUT, then=-F("amount")), output_field=IntegerField()))
    )
    return totals["total"] or 0


def branch_wallet_total(branch) -> int:
    total = 0
    for wallet in BranchWallet.objects.filter(branch=branch).only("pk"):
        total += wallet_balance(wallet)
    return total


def branch_unallocated_cash(branch) -> int:
    return get_branch_cash_balance(branch) - branch_wallet_total(branch)


def configured_wallet_for_category(branch, category: str, wallet_type=BranchWallet.TYPE_DISBURSEMENT):
    """Return a wallet only when configuration is unambiguous; otherwise fallback to main cash."""
    wallets = list(BranchWallet.objects.filter(branch=branch, category=category, wallet_type=wallet_type, status=BranchWallet.STATUS_ACTIVE).order_by("-is_favorite", "pk")[:2])
    return wallets[0] if len(wallets) == 1 else None


def _require_active(wallet):
    if wallet.status != BranchWallet.STATUS_ACTIVE:
        raise ValidationError("Cette mini-caisse n'est plus active.")


def allocate_from_principal(*, wallet, amount: int, actor, label="Affectation depuis la caisse principale", notes=""):
    if amount <= 0:
        raise ValidationError("Le montant a affecter doit etre positif.")
    with transaction.atomic():
        branch, _balance = lock_branch_cash_balance(wallet.branch)
        assert_financial_period_open(branch, timezone.localdate())
        wallet = BranchWallet.objects.select_for_update().get(pk=wallet.pk, branch=branch)
        _require_active(wallet)
        if amount > branch_unallocated_cash(branch):
            raise ValidationError("Le disponible non affecte de la caisse principale est insuffisant.")
        return BranchWalletEntry.objects.create(wallet=wallet, direction=BranchWalletEntry.DIRECTION_IN, kind=BranchWalletEntry.KIND_ALLOCATION, amount=amount, label=label, notes=notes, created_by=actor)


def return_to_principal(*, wallet, amount: int, actor, notes=""):
    if amount <= 0 or amount > wallet_balance(wallet):
        raise ValidationError("Le montant a restituer depasse le solde de cette mini-caisse.")
    with transaction.atomic():
        branch, _balance = lock_branch_cash_balance(wallet.branch)
        assert_financial_period_open(branch, timezone.localdate())
        wallet = BranchWallet.objects.select_for_update().get(pk=wallet.pk, branch=branch)
        return BranchWalletEntry.objects.create(wallet=wallet, direction=BranchWalletEntry.DIRECTION_OUT, kind=BranchWalletEntry.KIND_RETURN, amount=amount, label="Restitution vers la caisse principale", notes=notes, created_by=actor)


def transfer_between_wallets(*, source, target, amount: int, actor, notes=""):
    if source.branch_id != target.branch_id or source.pk == target.pk:
        raise ValidationError("Le transfert doit concerner deux mini-caisses distinctes de la meme annexe.")
    if amount <= 0 or amount > wallet_balance(source):
        raise ValidationError("Le montant a transferer depasse le solde disponible.")
    reference = uuid4()
    with transaction.atomic():
        branch, _balance = lock_branch_cash_balance(source.branch)
        assert_financial_period_open(branch, timezone.localdate())
        wallets = {item.pk: item for item in BranchWallet.objects.select_for_update().filter(pk__in=[source.pk, target.pk], branch=branch)}
        source, target = wallets[source.pk], wallets[target.pk]
        _require_active(source); _require_active(target)
        if amount > wallet_balance(source):
            raise ValidationError("Le solde source a change ; reessayez.")
        outgoing = BranchWalletEntry.objects.create(wallet=source, counterpart_wallet=target, direction=BranchWalletEntry.DIRECTION_OUT, kind=BranchWalletEntry.KIND_TRANSFER, amount=amount, operation_reference=reference, label=f"Transfert vers {target.name}", notes=notes, created_by=actor)
        BranchWalletEntry.objects.create(wallet=target, counterpart_wallet=source, direction=BranchWalletEntry.DIRECTION_IN, kind=BranchWalletEntry.KIND_TRANSFER, amount=amount, operation_reference=reference, label=f"Transfert depuis {source.name}", notes=notes, created_by=actor)
        return outgoing


def consume_wallet_for_cash_movement(*, wallet, cash_movement, actor, label="", notes=""):
    """Link a real debit to its reservation without creating a second cash debit."""
    if cash_movement.branch_id != wallet.branch_id or cash_movement.movement_type != "out":
        raise ValidationError("La sortie de caisse ne correspond pas a cette mini-caisse.")
    with transaction.atomic():
        wallet = BranchWallet.objects.select_for_update().get(pk=wallet.pk)
        _require_active(wallet)
        if cash_movement.amount > wallet_balance(wallet):
            raise ValidationError("La mini-caisse ne couvre pas ce decaissement.")
        entry, _created = BranchWalletEntry.objects.get_or_create(
            wallet=wallet,
            idempotency_key=f"cash:{cash_movement.pk}",
            defaults={"direction": BranchWalletEntry.DIRECTION_OUT, "kind": BranchWalletEntry.KIND_CONSUMPTION, "amount": cash_movement.amount, "cash_movement": cash_movement, "label": label or cash_movement.label, "notes": notes, "created_by": actor},
        )
        return entry


def close_wallet(*, wallet, actor):
    assert_financial_period_open(wallet.branch, timezone.localdate())
    if wallet_balance(wallet) != 0:
        raise ValidationError("Restituez ou transferez le solde avant de cloturer cette mini-caisse.")
    wallet.status = BranchWallet.STATUS_CLOSED
    wallet.closed_by = actor
    wallet.closed_at = timezone.now()
    wallet.save(update_fields=["status", "closed_by", "closed_at", "updated_at"])
    return wallet
