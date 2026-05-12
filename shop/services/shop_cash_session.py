"""Sessions espèces boutique — même principe que payments.services.cash."""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
import secrets

from payments.models import PaymentAgent

from shop.models import ShopCashPaymentSession, ShopOrder


def verify_agent_and_create_shop_session(order: ShopOrder, agent_full_name):
    """Trouve l'agent dans l'annexe de la commande et assure une session locale active."""

    if not agent_full_name or len(agent_full_name.strip()) < 2:
        return None, "Nom de l'agent requis."

    agent_full_name = agent_full_name.strip()
    parts = agent_full_name.split()

    queryset = PaymentAgent.objects.select_related("user", "branch").filter(
        is_active=True,
        branch_id=order.branch_id,
    )
    query = Q()
    for part in parts:
        query &= (
            Q(user__first_name__icontains=part) | Q(user__last_name__icontains=part)
        )
    agent = queryset.filter(query).distinct().first()

    if not agent:
        return None, "Agent introuvable pour cette annexe."

    with transaction.atomic():
        ShopCashPaymentSession.objects.filter(
            order=order,
            agent=agent,
            expires_at__lt=timezone.now(),
            is_used=False,
        ).update(is_used=True)

        session = (
            ShopCashPaymentSession.objects.select_for_update()
            .filter(
                order=order,
                agent=agent,
                is_used=False,
                expires_at__gt=timezone.now(),
            )
            .order_by("-created_at")
            .first()
        )

        if not session:
            verification_code = str(secrets.randbelow(900000) + 100000)
            session = ShopCashPaymentSession.objects.create(
                order=order,
                agent=agent,
                verification_code=verification_code,
                expires_at=timezone.now() + timedelta(minutes=5),
                is_used=False,
            )

    return agent, None


def validate_shop_cash_session_code(order: ShopOrder, agent: PaymentAgent, code: str):
    """Valide et consomme le code communiqué par l'agent."""

    if not code:
        return None, "Code requis."

    code = code.strip()

    with transaction.atomic():
        session = (
            ShopCashPaymentSession.objects.select_for_update()
            .filter(
                order=order,
                agent=agent,
                is_used=False,
            )
            .order_by("-created_at")
            .first()
        )

        if not session:
            return None, "Aucune session active trouvee."

        if timezone.now() > session.expires_at:
            session.is_used = True
            session.save(update_fields=["is_used"])
            return None, "Code expire."

        if session.verification_code != code:
            return None, "Code invalide."

        session.is_used = True
        session.save(update_fields=["is_used"])

    return session, None


def manager_shop_sessions_for_agent(agent: PaymentAgent, *, limit: int = 10):
    """Sessions boutique actives visibles au poste de l'agent (gestionnaire)."""
    now = timezone.now()
    return list(
        ShopCashPaymentSession.objects.filter(
            agent=agent,
            is_used=False,
            expires_at__gt=now,
        )
        .select_related(
            "order",
            "order__student",
            "agent__user",
        )
        .prefetch_related("order__items", "order__items__product")
        .order_by("-created_at")[:limit]
    )
