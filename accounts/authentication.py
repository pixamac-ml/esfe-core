"""Primitives communes aux parcours d'authentification ESFE."""

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.utils.http import url_has_allowed_host_and_scheme

from portal.services.it_support_service import get_account_support_state


@dataclass(frozen=True)
class AuthenticationDecision:
    allowed: bool
    reason_code: str = "allowed"
    message: str = ""


class AuthenticationGate:
    """Applique les mêmes états de compte à tous les modes de connexion."""

    @staticmethod
    def evaluate(user) -> AuthenticationDecision:
        if user is None or not getattr(user, "is_active", False):
            return AuthenticationDecision(
                False,
                "account_inactive",
                "Ce compte est inactif. Contactez l'administration.",
            )

        state = get_account_support_state(user)
        if state.is_suspended:
            return AuthenticationDecision(
                False,
                "account_suspended",
                "Ce compte est suspendu. Contactez l'informaticien de votre annexe.",
            )
        if state.is_blocked:
            return AuthenticationDecision(
                False,
                "account_blocked",
                "Ce compte est bloque. Contactez l'informaticien de votre annexe.",
            )
        return AuthenticationDecision(True)

    @classmethod
    def enforce(cls, user) -> None:
        decision = cls.evaluate(user)
        if not decision.allowed:
            raise ValidationError(decision.message, code=decision.reason_code)


def safe_local_redirect_url(request, candidate):
    """Retourne une cible locale sûre ou ``None``."""
    if not candidate:
        return None
    if url_has_allowed_host_and_scheme(
        url=candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return None
