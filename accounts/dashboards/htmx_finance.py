# accounts/dashboards/htmx_finance.py

"""
Vues HTMX pour le dashboard finance.

Gestion dynamique des paiements et sessions cash
sans rechargement de page.
"""

import json
from datetime import timedelta

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST, require_GET
from django.template.loader import render_to_string
from django.utils import timezone
from django.db import transaction, models
from django.db.models import Sum, Count, Q

from payments.models import Payment, CashPaymentSession, PaymentAgent
from inscriptions.models import Inscription

from .permissions import check_finance_access
from .querysets import get_base_queryset
from .helpers import get_user_branch


# ==========================================================
# DÉCORATEUR HTMX FINANCE
# ==========================================================

def htmx_finance_required(view_func):
    """
    Décorateur combiné : login + accès finance + requête HTMX.
    """

    def wrapper(request, *args, **kwargs):

        if not request.user.is_authenticated:
            return HttpResponse(
                "<div class='text-red-500 p-4'>Non authentifié</div>",
                status=401
            )

        if not check_finance_access(request.user):
            return HttpResponse(
                "<div class='text-red-500 p-4'>Accès refusé</div>",
                status=403
            )

        if not request.headers.get("HX-Request"):
            return HttpResponse(
                "<div class='text-red-500 p-4'>Requête HTMX requise</div>",
                status=400
            )

        return view_func(request, *args, **kwargs)

    return wrapper


# ==========================================================
# HELPER - OBTENIR L'AGENT COURANT
# ==========================================================

def get_current_agent(user):
    """
    Récupère le PaymentAgent lié à l'utilisateur courant.
    Retourne None si l'utilisateur n'est pas un agent.
    """
    try:
        return PaymentAgent.objects.select_related("branch").get(
            user=user,
            is_active=True
        )
    except PaymentAgent.DoesNotExist:
        return None


# ==========================================================
# VALIDATION PAIEMENT
# ==========================================================

@require_POST
@htmx_finance_required
def validate_payment_htmx(request, payment_id):
    """
    Valide un paiement en attente.

    - Change le statut en 'validated'
    - Met à jour l'état financier de l'inscription
    - Retourne le fragment HTML mis à jour
    """

    payment = get_object_or_404(
        get_base_queryset(request.user, "payment")
        .select_related(
            "inscription",
            "inscription__candidature",
            "inscription__candidature__programme",
            "agent",
        ),
        id=payment_id,
        status=Payment.STATUS_PENDING
    )

    try:
        with transaction.atomic():

            # Validation du paiement
            payment.status = Payment.STATUS_VALIDATED
            payment.paid_at = timezone.now()
            payment.save(update_fields=["status", "paid_at"])

            # Mise à jour de l'inscription
            if payment.inscription:
                payment.inscription.update_financial_state()

        # Rendu du fragment validé
        html = render_to_string(
            "accounts/dashboard/partials/payment_validated.html",
            {"payment": payment},
            request=request
        )

        response = HttpResponse(html)
        response["HX-Trigger"] = json.dumps({
            "paymentValidated": {
                "id": payment.id,
                "amount": str(payment.amount)
            },
            "showToast": {
                "message": f"Paiement {payment.reference} validé",
                "type": "success"
            }
        })

        return response

    except Exception as e:

        return HttpResponse(
            f"<div class='text-red-500 p-4'>Erreur : {str(e)}</div>",
            status=500
        )


# ==========================================================
# REJET PAIEMENT
# ==========================================================

@require_POST
@htmx_finance_required
def reject_payment_htmx(request, payment_id):
    """
    Rejette/annule un paiement en attente.

    - Change le statut en 'cancelled'
    - Retourne le fragment HTML mis à jour
    """

    payment = get_object_or_404(
        get_base_queryset(request.user, "payment")
        .select_related(
            "inscription",
            "inscription__candidature",
        ),
        id=payment_id,
        status=Payment.STATUS_PENDING
    )

    reason = request.POST.get("reason", "").strip()

    try:
        with transaction.atomic():

            payment.status = Payment.STATUS_CANCELLED
            payment.save(update_fields=["status"])

        # Rendu du fragment rejeté
        html = render_to_string(
            "accounts/dashboard/partials/payment_rejected.html",
            {"payment": payment, "reason": reason},
            request=request
        )

        response = HttpResponse(html)
        response["HX-Trigger"] = json.dumps({
            "paymentRejected": {
                "id": payment.id
            },
            "showToast": {
                "message": f"Paiement {payment.reference} rejeté",
                "type": "warning"
            }
        })

        return response

    except Exception as e:

        return HttpResponse(
            f"<div class='text-red-500 p-4'>Erreur : {str(e)}</div>",
            status=500
        )


# ==========================================================
# CRÉATION SESSION CASH
# ==========================================================

@require_POST
@htmx_finance_required
def create_cash_session_htmx(request):
    """
    Crée une nouvelle session de paiement cash.

    - Génère un code de vérification à 6 chiffres
    - Définit une expiration (5 minutes)
    - Lie la session à l'agent connecté
    """

    # Récupération de l'agent
    agent = get_current_agent(request.user)

    if not agent:
        return HttpResponse(
            "<div class='text-red-500 p-4'>Vous n'êtes pas un agent de paiement actif</div>",
            status=403
        )

    # Données du formulaire
    inscription_id = request.POST.get("inscription_id")

    if not inscription_id:
        return HttpResponse(
            "<div class='text-red-500 p-4'>Inscription requise</div>",
            status=400
        )

    # Récupération de l'inscription
    inscription = get_object_or_404(
        get_base_queryset(request.user, "inscription")
        .select_related(
            "candidature",
            "candidature__programme",
        ),
        id=inscription_id
    )

    if inscription.status not in {
        Inscription.STATUS_CREATED,
        Inscription.STATUS_AWAITING_PAYMENT,
        Inscription.STATUS_PARTIAL,
    }:
        return HttpResponse(
            "<div class='text-red-500 p-4'>Cette inscription n'est pas dans un etat payable.</div>",
            status=400
        )

    # Vérifier qu'il n'y a pas déjà une session active pour cette inscription
    existing_session = CashPaymentSession.objects.filter(
        inscription=inscription,
        is_used=False,
        expires_at__gt=timezone.now()
    ).first()

    if existing_session:
        return HttpResponse(
            f"<div class='text-amber-600 p-4'>Une session active existe déjà (Code: {existing_session.verification_code})</div>",
            status=400
        )

    try:
        with transaction.atomic():

            # Création de la session
            session = CashPaymentSession.objects.create(
                agent=agent,
                inscription=inscription,
                verification_code="000000",  # Temporaire
                expires_at=timezone.now() + timedelta(minutes=5)
            )

            # Génération du code
            session.generate_code()

        # Rendu du fragment
        html = render_to_string(
            "accounts/dashboard/partials/cash_session_created.html",
            {
                "session": session,
                "inscription": inscription
            },
            request=request
        )

        response = HttpResponse(html)
        response["HX-Trigger"] = json.dumps({
            "sessionCreated": {
                "id": session.id,
                "code": session.verification_code
            },
            "showToast": {
                "message": f"Session créée - Code : {session.verification_code}",
                "type": "success"
            }
        })

        return response

    except Exception as e:

        return HttpResponse(
            f"<div class='text-red-500 p-4'>Erreur : {str(e)}</div>",
            status=500
        )


# ==========================================================
# RÉGÉNÉRATION CODE
# ==========================================================

@require_POST
@htmx_finance_required
def regenerate_code_htmx(request, session_id):
    """
    Régénère le code de vérification d'une session cash.

    - Génère un nouveau code à 6 chiffres
    - Réinitialise le délai d'expiration
    """

    agent = get_current_agent(request.user)

    if not agent:
        return HttpResponse(
            "<div class='text-red-500 p-4'>Vous n'êtes pas un agent de paiement</div>",
            status=403
        )

    # Récupération de la session
    session = get_object_or_404(
        CashPaymentSession.objects.select_related(
            "inscription",
            "inscription__candidature",
        ),
        id=session_id,
        agent=agent,
        is_used=False
    )

    try:
        # Régénération du code
        session.generate_code()

        # Retourne juste le nouveau code
        response = HttpResponse(session.verification_code)
        response["HX-Trigger"] = json.dumps({
            "codeRegenerated": {
                "id": session.id,
                "code": session.verification_code
            },
            "showToast": {
                "message": f"Nouveau code : {session.verification_code}",
                "type": "info"
            }
        })

        return response

    except Exception as e:

        return HttpResponse(
            f"<div class='text-red-500 p-4'>Erreur : {str(e)}</div>",
            status=500
        )


# ==========================================================
# MARQUER SESSION UTILISÉE (ENREGISTRER PAIEMENT)
# ==========================================================

@require_POST
@htmx_finance_required
def mark_session_used_htmx(request, session_id):
    """
    Marque une session cash comme utilisée et crée le paiement.

    - Valide le code de vérification (optionnel)
    - Crée un paiement validé avec le montant spécifié
    - Met à jour l'état financier de l'inscription
    """

    agent = get_current_agent(request.user)

    if not agent:
        return HttpResponse(
            "<div class='text-red-500 p-4'>Vous n'êtes pas un agent de paiement</div>",
            status=403
        )

    # Montant fourni
    amount = request.POST.get("amount", "").strip()

    if not amount:
        return HttpResponse(
            "<div class='text-red-500 p-4'>Montant requis</div>",
            status=400
        )

    try:
        amount = int(amount)
        if amount <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        return HttpResponse(
            "<div class='text-red-500 p-4'>Montant invalide</div>",
            status=400
        )

    # Récupération de la session
    session = get_object_or_404(
        CashPaymentSession.objects.select_related(
            "inscription",
            "inscription__candidature",
            "inscription__candidature__programme",
        ),
        id=session_id,
        agent=agent,
        is_used=False
    )

    # Vérification de l'expiration
    if timezone.now() > session.expires_at:
        return HttpResponse(
            "<div class='text-red-500 p-4'>Session expirée, veuillez régénérer le code</div>",
            status=400
        )

    inscription = session.inscription

    # Vérification du solde
    if amount > inscription.balance:
        return HttpResponse(
            f"<div class='text-red-500 p-4'>Montant supérieur au solde ({inscription.balance} FCFA)</div>",
            status=400
        )

    try:
        with transaction.atomic():

            # Création du paiement
            payment = Payment.objects.create(
                inscription=inscription,
                amount=amount,
                method=Payment.METHOD_CASH,
                status=Payment.STATUS_VALIDATED,
                paid_at=timezone.now(),
                agent=agent,
            )

            # Marquage de la session
            session.is_used = True
            session.save(update_fields=["is_used"])

        # Rendu du fragment
        html = render_to_string(
            "accounts/dashboard/partials/cash_session_completed.html",
            {
                "session": session,
                "payment": payment
            },
            request=request
        )

        response = HttpResponse(html)
        response["HX-Trigger"] = json.dumps({
            "sessionCompleted": {
                "id": session.id,
                "payment_id": payment.id
            },
            "showToast": {
                "message": f"Paiement de {amount:,} FCFA enregistré".replace(",", " "),
                "type": "success"
            }
        })

        return response

    except Exception as e:

        return HttpResponse(
            f"<div class='text-red-500 p-4'>Erreur : {str(e)}</div>",
            status=500
        )


# ==========================================================
# ANNULER SESSION
# ==========================================================

@require_POST
@htmx_finance_required
def cancel_session_htmx(request, session_id):
    """
    Annule une session cash non utilisée.
    """

    agent = get_current_agent(request.user)

    if not agent:
        return HttpResponse(
            "<div class='text-red-500 p-4'>Vous n'êtes pas un agent de paiement</div>",
            status=403
        )

    session = get_object_or_404(
        CashPaymentSession,
        id=session_id,
        agent=agent,
        is_used=False
    )

    try:
        # On marque comme utilisée pour "l'archiver"
        session.is_used = True
        session.save(update_fields=["is_used"])

        # Retourne une div vide pour supprimer l'élément
        response = HttpResponse("")
        response["HX-Trigger"] = json.dumps({
            "sessionCancelled": {
                "id": session.id
            },
            "showToast": {
                "message": "Session annulée",
                "type": "warning"
            }
        })

        return response

    except Exception as e:

        return HttpResponse(
            f"<div class='text-red-500 p-4'>Erreur : {str(e)}</div>",
            status=500
        )


# ==========================================================
# RECHERCHE INSCRIPTIONS (AUTOCOMPLETE)
# ==========================================================

@require_GET
@htmx_finance_required
def search_inscriptions_htmx(request):
    """
    Recherche d'inscriptions pour paiement cash.

    Utilisé pour l'autocomplete lors de la création
    d'une session de paiement.
    """

    query = request.GET.get("q", "").strip()

    if len(query) < 2:
        return HttpResponse("")

    inscriptions = (
        get_base_queryset(request.user, "inscription")
        .filter(
            status__in=["created", "awaiting_payment", "partial_paid"]
        )
        .filter(
            Q(public_token__icontains=query) |
            Q(candidature__last_name__icontains=query) |
            Q(candidature__first_name__icontains=query) |
            Q(candidature__email__icontains=query)
        )
        .select_related(
            "candidature",
            "candidature__programme"
        )
        [:10]
    )

    html = render_to_string(
        "accounts/dashboard/partials/inscription_search_results.html",
        {"inscriptions": inscriptions},
        request=request
    )

    return HttpResponse(html)


# ==========================================================
# DÉTAIL PAIEMENT
# ==========================================================

@require_GET
@htmx_finance_required
def payment_detail_htmx(request, payment_id):
    """
    Affiche le détail complet d'un paiement dans un modal.
    """

    payment = get_object_or_404(
        get_base_queryset(request.user, "payment")
        .select_related(
            "inscription",
            "inscription__candidature",
            "inscription__candidature__programme",
            "inscription__candidature__branch",
            "agent",
            "agent__user",
            "agent__branch",
        ),
        id=payment_id
    )

    html = render_to_string(
        "accounts/dashboard/partials/payment_detail_modal.html",
        {"payment": payment},
        request=request
    )

    return HttpResponse(html)


# ==========================================================
# DÉTAIL INSCRIPTION (FINANCE)
# ==========================================================

@require_GET
@htmx_finance_required
def inscription_finance_detail_htmx(request, inscription_id):
    """
    Affiche le détail financier d'une inscription.

    Inclut l'historique des paiements et le solde restant.
    """

    inscription = get_object_or_404(
        get_base_queryset(request.user, "inscription")
        .select_related(
            "candidature",
            "candidature__programme",
            "candidature__branch"
        )
        .prefetch_related("payments"),
        id=inscription_id
    )

    # Statistiques paiements
    payments_stats = inscription.payments.aggregate(
        total_validated=Sum(
            "amount",
            filter=Q(status="validated")
        ),
        total_pending=Sum(
            "amount",
            filter=Q(status="pending")
        ),
        count_validated=Count(
            "id",
            filter=Q(status="validated")
        ),
        count_pending=Count(
            "id",
            filter=Q(status="pending")
        )
    )

    html = render_to_string(
        "accounts/dashboard/partials/inscription_finance_detail.html",
        {
            "inscription": inscription,
            "payments_stats": payments_stats,
            "payments": inscription.payments.order_by("-created_at")[:20]
        },
        request=request
    )

    return HttpResponse(html)


# ==========================================================
# STATS TEMPS RÉEL
# ==========================================================

@require_GET
@htmx_finance_required
def refresh_stats_htmx(request):
    """
    Rafraîchit les statistiques du dashboard finance.

    Utilisé pour la mise à jour automatique des compteurs.
    """

    payments = get_base_queryset(request.user, "payment")

    today = timezone.now().date()
    week = today - timedelta(days=7)

    stats_today = payments.filter(
        paid_at__date=today,
        status="validated"
    ).aggregate(
        total=Sum("amount"),
        count=Count("id")
    )

    stats_week = payments.filter(
        paid_at__date__gte=week,
        status="validated"
    ).aggregate(
        total=Sum("amount"),
        count=Count("id")
    )

    stats_global = payments.filter(
        status="validated"
    ).aggregate(
        total=Sum("amount"),
        count=Count("id")
    )

    pending_count = payments.filter(
        status="pending"
    ).count()

    html = render_to_string(
        "accounts/dashboard/partials/finance_stats.html",
        {
            "stats_today": stats_today,
            "stats_week": stats_week,
            "stats_global": stats_global,
            "pending_count": pending_count
        },
        request=request
    )

    return HttpResponse(html)


# ==========================================================
# LISTE PAIEMENTS PAGINÉE
# ==========================================================

@require_GET
@htmx_finance_required
def payments_list_htmx(request):
    """
    Liste paginée des paiements avec filtres.

    Utilisé pour le chargement dynamique et la recherche.
    """

    from django.core.paginator import Paginator

    payments = (
        get_base_queryset(request.user, "payment")
        .select_related(
            "inscription",
            "inscription__candidature",
            "inscription__candidature__programme",
            "agent",
        )
    )

    # Filtres
    method = request.GET.get("method")
    status = request.GET.get("status")
    search = (request.GET.get("q") or request.GET.get("search") or "").strip()

    if method:
        payments = payments.filter(method=method)

    if status:
        payments = payments.filter(status=status)

    if search:
        search_filter = (
            Q(reference__icontains=search) |
            Q(inscription__public_token__icontains=search) |
            Q(inscription__candidature__last_name__icontains=search) |
            Q(inscription__candidature__first_name__icontains=search) |
            Q(inscription__candidature__email__icontains=search)
        )

        # Exact id support for references like PAY-AB12CD34.
        if search.upper().startswith("PAY-"):
            search_filter = search_filter | Q(reference__iexact=search)

        payments = payments.filter(search_filter)

    # Tri
    order = request.GET.get("order", "recent")

    if order == "amount":
        payments = payments.order_by("-amount")
    elif order == "oldest":
        payments = payments.order_by("paid_at")
    else:
        payments = payments.order_by("-paid_at")

    # Pagination
    paginator = Paginator(payments, 25)
    page = request.GET.get("page", 1)
    payments_page = paginator.get_page(page)

    query_data = request.GET.copy()
    query_data.pop("page", None)
    pagination_query = query_data.urlencode()

    html = render_to_string(
        "accounts/dashboard/partials/payments_table.html",
        {
            "payments": payments_page,
            "paginator": paginator,
            "pagination_query": pagination_query,
        },
        request=request
    )

    return HttpResponse(html)