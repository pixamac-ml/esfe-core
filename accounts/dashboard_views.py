"""
Vues pour les dashboards du personnel.

Ce fichier contient:
- La vue de redirection automatique (/accounts/dashboard/)
- Le dashboard du responsable admissions
- Le dashboard des agents de paiement
- Le dashboard du directeur général
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import UserPassesTestMixin
from django.views.generic import TemplateView
from django.contrib import messages

from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta
import secrets

from admissions.models import Candidature, CandidatureDocument, RequiredDocument
from inscriptions.models import Inscription
from payments.models import Payment, CashPaymentSession, PaymentAgent
from students.models import Student


# =====================================================
# HELPERS
# =====================================================

def user_has_group(user, group_name):
    """Vérifie si l'utilisateur appartient à un groupe"""
    if not user.is_authenticated:
        return False
    return user.groups.filter(name=group_name).exists()


def get_user_primary_group(user):
    """Retourne le premier groupe de l'utilisateur"""
    if not user.is_authenticated:
        return None
    return user.groups.first()


# =====================================================
# VUE DE REDIRECTION
# =====================================================

@login_required
def dashboard_redirect(request):
    """
    Redirige automatiquement vers le dashboard approprié
    selon le groupe de l'utilisateur.
    """
    user = request.user

    # Superuser -> dashboard exécutif par défaut
    if user.is_superuser:
        return redirect('accounts:executive_dashboard')

    # Vérifier les groupes par ordre de priorité
    if user_has_group(user, 'admissions_managers'):
        return redirect('accounts:admissions_dashboard')

    if user_has_group(user, 'finance_agents'):
        return redirect('accounts:finance_dashboard')

    if user_has_group(user, 'executive_director'):
        return redirect('accounts:executive_dashboard')

    # Si pas de groupe, afficher message
    messages.warning(
        request,
        "Vous n'avez pas accès à un dashboard. "
        "Contactez l'administrateur pour obtenir un accès."
    )
    return redirect('core:home')


# =====================================================
# DASHBOARD RESPONSABLE ADMISSIONS
# =====================================================

@login_required
def admissions_dashboard(request):
    """
    Dashboard du responsable des dossiers d'admission.
    Affiche:
    - Statistiques des candidatures
    - Liste des candidatures en attente
    - Documents à valider
    """
    # Vérification de permission
    user = request.user
    if not (user.is_superuser or user_has_group(user, 'admissions_managers')):
        messages.error(request, "Accès refusé. Vous n'avez pas la permission.")
        return redirect('core:home')

    # === STATISTIQUES ===
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)

    # Candidatures par statut
    candidacy_stats = Candidature.objects.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status='submitted')),
        under_review=Count('id', filter=Q(status='under_review')),
        accepted=Count('id', filter=Q(status='accepted')),
        rejected=Count('id', filter=Q(status='rejected')),
        to_complete=Count('id', filter=Q(status='to_complete')),
    )

    # Candidatures cette semaine
    weekly_candidacies = Candidature.objects.filter(
        submitted_at__date__gte=week_ago
    ).count()

    # Documents non validés
    pending_docs = CandidatureDocument.objects.filter(
        is_valid=False
    ).select_related('candidature', 'document_type')

    # === LISTES ===
    # Candidatures en attente de décision
    pending_candidatures = Candidature.objects.filter(
        status__in=['submitted', 'under_review', 'to_complete']
    ).select_related('programme').order_by('-submitted_at')[:20]

    # Candidatures acceptées récentes (prêtes pour inscription)
    accepted_candidatures = Candidature.objects.filter(
        status='accepted'
    ).select_related('programme').order_by('-reviewed_at')[:10]

    # === Taux de conversion ===
    total_reviewed = candidacy_stats['accepted'] + candidacy_stats['rejected']
    admission_rate = 0
    if total_reviewed > 0:
        admission_rate = round((candidacy_stats['accepted'] / total_reviewed) * 100, 1)

    # === LISTE DES PROGRAMMES POUR FILTRES ===
    from formations.models import Programme
    programmes_list = Programme.objects.all().order_by('title')

    context = {
        'stats': candidacy_stats,
        'weekly_candidacies': weekly_candidacies,
        'pending_docs': pending_docs,
        'pending_candidatures': pending_candidatures,
        'accepted_candidatures': accepted_candidatures,
        'admission_rate': admission_rate,
        'dashboard_type': 'admissions',
        'programmes_list': programmes_list,
    }

    return render(request, 'accounts/dashboard/admissions.html', context)


# =====================================================
# DASHBOARD AGENT DE PAIEMENT
# =====================================================

@login_required
def finance_dashboard(request):
    """
    Dashboard de l'agent de paiement.
    Affiche:
    - Statistiques des paiements du jour
    - Transactions en attente de validation
    - Sessions de paiement espèces
    - Historique des paiements
    """
    # Vérification de permission
    user = request.user
    if not (user.is_superuser or user_has_group(user, 'finance_agents')):
        messages.error(request, "Accès refusé. Vous n'avez pas la permission.")
        return redirect('core:home')

    # === STATISTIQUES ===
    today = timezone.now().date()
    today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
    today_end = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.max.time()))

    # Paiements du jour
    daily_payments = Payment.objects.filter(
        paid_at__gte=today_start,
        paid_at__lte=today_end,
        status='validated'
    )

    daily_stats = daily_payments.aggregate(
        count=Count('id'),
        total=Sum('amount')
    )

    # Paiements en attente (non validés)
    pending_payments = Payment.objects.filter(
        status='pending'
    ).select_related(
        'inscription__candidature__programme'
    ).order_by('-created_at')[:20]

    # Tous les paiements du jour
    today_payments = daily_payments.select_related(
        'inscription__candidature__programme'
    ).order_by('-paid_at')[:50]

    # === INSCRIPTIONS EN ATTENTE DE PAIEMENT ===
    inscriptions_pending = Inscription.objects.filter(
        status='created'
    ).select_related(
        'candidature__programme'
    ).order_by('-created_at')[:20]

    # === PAR MÉTHODE DE PAIEMENT ===
    payments_by_method = Payment.objects.filter(
        status='validated'
    ).values('method').annotate(
        count=Count('id'),
        total=Sum('amount')
    )

    # === SESSIONS DE PAIEMENT ESPÈCES ===
    # Récupérer ou créer le profile PaymentAgent pour l'utilisateur
    try:
        payment_agent = PaymentAgent.objects.get(user=user)
        # Sessions actives de l'agent (non utilisées)
        active_sessions = CashPaymentSession.objects.filter(
            agent=payment_agent,
            is_used=False,
            expires_at__gte=timezone.now()
        ).select_related('inscription__candidature').order_by('-created_at')

        # Sessions utilisées aujourd'hui
        today_sessions = CashPaymentSession.objects.filter(
            agent=payment_agent,
            created_at__gte=today_start,
            is_used=True
        ).select_related('inscription__candidature')

        # Toutes les sessions récentes
        recent_sessions = CashPaymentSession.objects.filter(
            agent=payment_agent
        ).select_related('inscription__candidature').order_by('-created_at')[:10]
    except PaymentAgent.DoesNotExist:
        payment_agent = None
        active_sessions = []
        today_sessions = []
        recent_sessions = []

    # Inscriptions disponibles pour création de session
    available_inscriptions = Inscription.objects.filter(
        status='created'
    ).select_related(
        'candidature__programme'
    ).order_by('-created_at')[:50]

    context = {
        'daily_stats': daily_stats,
        'pending_payments': pending_payments,
        'today_payments': today_payments,
        'inscriptions_pending': inscriptions_pending,
        'payments_by_method': payments_by_method,
        'dashboard_type': 'finance',
        # Cash Payment Sessions
        'payment_agent': payment_agent,
        'active_sessions': active_sessions,
        'today_sessions': today_sessions,
        'recent_sessions': recent_sessions,
        'available_inscriptions': available_inscriptions,
    }

    return render(request, 'accounts/dashboard/finance.html', context)


# =====================================================
# DASHBOARD DIRECTEUR GÉNÉRAL
# =====================================================

@login_required
def executive_dashboard(request):
    """
    Dashboard du directeur général.
    Affiche:
    - Statistiques globales
    - Revenus totaux
    - Graphiques et KPIs
    """
    # Vérification de permission
    user = request.user
    if not (user.is_superuser or user_has_group(user, 'executive_director')):
        messages.error(request, "Accès refusé. Vous n'avez pas la permission.")
        return redirect('core:home')

    # === STATISTIQUES GLOBALES ===
    # Total étudiants actifs
    total_students = Student.objects.filter(is_active=True).count()

    # Total inscriptions
    total_inscriptions = Inscription.objects.count()

    # Total candidatures
    total_candidatures = Candidature.objects.count()

    # Revenus totaux
    total_revenue = Payment.objects.filter(
        status='validated'
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Revenus du mois
    today = timezone.now().date()
    month_start = today.replace(day=1)
    month_start_dt = timezone.make_aware(timezone.datetime.combine(month_start, timezone.datetime.min.time()))

    monthly_revenue = Payment.objects.filter(
        status='validated',
        paid_at__gte=month_start_dt
    ).aggregate(total=Sum('amount'))['total'] or 0

    # === POPULARITÉ DES PROGRAMMES ===
    programmes_popularity = Inscription.objects.values(
        'candidature__programme__title'
    ).annotate(
        count=Count('id')
    ).order_by('-count')[:5]

    # === PAR STATUT D'ADMISSION ===
    admission_stats = Candidature.objects.values('status').annotate(
        count=Count('id')
    )

    # === TAUX DE CONVERSION (candidatures -> inscriptions) ===
    conversion_rate = 0
    if total_candidatures > 0:
        conversion_rate = round((total_inscriptions / total_candidatures) * 100, 1)

    # === RÉCENTS ACTIVITÉS ===
    # Dernières inscriptions
    recent_inscriptions = Inscription.objects.select_related(
        'candidature__programme',
        'candidature'
    ).order_by('-created_at')[:10]

    # Derniers paiements validés
    recent_payments = Payment.objects.filter(
        status='validated'
    ).select_related(
        'inscription__candidature__programme'
    ).order_by('-paid_at')[:10]

    # === LISTE DES PROGRAMMES POUR FILTRES ===
    from formations.models import Programme
    programmes_list = Programme.objects.all().order_by('title')

    context = {
        'total_students': total_students,
        'total_inscriptions': total_inscriptions,
        'total_candidatures': total_candidatures,
        'total_revenue': total_revenue,
        'monthly_revenue': monthly_revenue,
        'conversion_rate': conversion_rate,
        'programmes_popularity': programmes_popularity,
        'admission_stats': admission_stats,
        'recent_inscriptions': recent_inscriptions,
        'recent_payments': recent_payments,
        'dashboard_type': 'executive',
        'programmes_list': programmes_list,
    }

    return render(request, 'accounts/dashboard/executive.html', context)


# =====================================================
# HTMX ENDPOINTS - FINANCE
# =====================================================

@login_required
def validate_payment_htmx(request, payment_id):
    """
    Endpoint HTMX pour valider un paiement.
    Accessible uniquement aux agents finance.
    """
    # Vérification de permission
    user = request.user
    if not (user.is_superuser or user_has_group(user, 'finance_agents')):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    try:
        payment = Payment.objects.select_related(
            'inscription__candidature__programme'
        ).get(pk=payment_id, status='pending')
    except Payment.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Paiement non trouvé ou déjà traité.'
        })

    # Validation du paiement
    payment.status = 'validated'
    payment.save()

    # Retourner une réponse HTML pour remplacer l'élément
    return render(request, 'accounts/dashboard/partials/payment_validated.html', {
        'payment': payment
    })


@login_required
def reject_payment_htmx(request, payment_id):
    """
    Endpoint HTMX pour rejeter un paiement.
    Accessible uniquement aux agents finance.
    """
    # Vérification de permission
    user = request.user
    if not (user.is_superuser or user_has_group(user, 'finance_agents')):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    try:
        payment = Payment.objects.select_related(
            'inscription__candidature__programme'
        ).get(pk=payment_id, status='pending')
    except Payment.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Paiement non trouvé ou déjà traité.'
        })

    # Rejet du paiement
    payment.status = 'cancelled'
    payment.save()

    # Retourner une réponse vide (l'élément sera supprimé)
    from django.http import HttpResponse
    return HttpResponse('')


# =====================================================
# HTMX ENDPOINTS - ADMISSIONS
# =====================================================

@login_required
def approve_candidature_htmx(request, candidature_id):
    """
    Endpoint HTMX pour approuver une candidature ET créer l'inscription automatiquement.
    Accessible uniquement aux responsables admissions.
    """
    from django.db import transaction

    # Vérification de permission
    user = request.user
    if not (user.is_superuser or user_has_group(user, 'admissions_managers')):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    try:
        candidature = Candidature.objects.select_related('programme').get(
            pk=candidature_id,
            status__in=['submitted', 'under_review', 'to_complete']
        )
    except Candidature.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Candidature non trouvée ou déjà traitée.'
        })

    # Vérifier si inscription existe déjà
    if hasattr(candidature, 'inscription'):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Une inscription existe déjà pour cette candidature.'
        })

    programme = candidature.programme

    # Calculer le montant des frais
    amount_due = programme.get_inscription_amount_for_year(candidature.entry_year)

    if not amount_due or amount_due <= 0:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': f'Aucun frais configuré pour {programme}. Veuillez configurer les frais dans admin.'
        })

    try:
        with transaction.atomic():
            # Créer l'inscription
            from inscriptions.services import create_inscription_from_candidature
            inscription = create_inscription_from_candidature(
                candidature=candidature,
                amount_due=amount_due
            )

            # Mettre à jour le statut de la candidature
            candidature.status = 'accepted'
            candidature.reviewed_at = timezone.now()
            candidature.save(update_fields=['status', 'reviewed_at'])

        # Retourner le template de succès avec les détails de l'inscription
        return render(request, 'accounts/dashboard/partials/candidature_approved.html', {
            'candidature': candidature,
            'inscription': inscription
        })

    except Exception as e:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': f'Erreur lors de la création de l\'inscription: {str(e)}'
        })


@login_required
def set_candidature_under_review_htmx(request, candidature_id):
    """Passer une candidature en cours d'analyse."""
    from django.http import HttpResponse

    user = request.user
    if not (user.is_superuser or user_has_group(user, 'admissions_managers')):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    try:
        candidature = Candidature.objects.get(pk=candidature_id, status='submitted')
        candidature.status = 'under_review'
        candidature.reviewed_at = timezone.now()
        candidature.save(update_fields=['status', 'reviewed_at'])
        return HttpResponse('')
    except Candidature.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Candidature non trouvée ou statut invalide.'
        })


@login_required
def set_candidature_to_complete_htmx(request, candidature_id):
    """Demander à la candidate de compléter son dossier."""
    from django.http import HttpResponse

    user = request.user
    if not (user.is_superuser or user_has_group(user, 'admissions_managers')):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    try:
        candidature = Candidature.objects.get(
            pk=candidature_id,
            status__in=['submitted', 'under_review']
        )
        candidature.status = 'to_complete'
        candidature.reviewed_at = timezone.now()
        candidature.save(update_fields=['status', 'reviewed_at'])
        return HttpResponse('')
    except Candidature.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Candidature non trouvée ou statut invalide.'
        })


@login_required
def create_inscription_htmx(request, candidature_id):
    """Créer une inscription pour une candidature déjà acceptée."""
    from django.db import transaction

    user = request.user
    if not (user.is_superuser or user_has_group(user, 'admissions_managers')):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    try:
        candidature = Candidature.objects.select_related('programme').get(
            pk=candidature_id,
            status='accepted'
        )
    except Candidature.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Candidature non trouvée ou non acceptée.'
        })

    if hasattr(candidature, 'inscription'):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Une inscription existe déjà.'
        })

    programme = candidature.programme
    amount_due = programme.get_inscription_amount_for_year(candidature.entry_year)

    if not amount_due or amount_due <= 0:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Frais non configurés pour ce programme.'
        })

    try:
        with transaction.atomic():
            from inscriptions.services import create_inscription_from_candidature
            inscription = create_inscription_from_candidature(
                candidature=candidature,
                amount_due=amount_due
            )

        return render(request, 'accounts/dashboard/partials/candidature_approved.html', {
            'candidature': candidature,
            'inscription': inscription
        })
    except Exception as e:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': f'Erreur: {str(e)}'
        })


# =====================================================
# HTMX ENDPOINTS - CASH PAYMENT SESSIONS
# =====================================================

@login_required
def create_cash_session_htmx(request):
    """
    Endpoint HTMX pour créer une session de paiement espèces.
    Accessible uniquement aux agents finance.
    """
    from django.http import HttpResponse

    # Vérification de permission
    user = request.user
    if not (user.is_superuser or user_has_group(user, 'finance_agents')):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    if request.method != 'POST':
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Méthode non autorisée.'
        })

    inscription_id = request.POST.get('inscription_id')
    if not inscription_id:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Veuillez sélectionner une inscription.'
        })

    try:
        # Récupérer ou créer le PaymentAgent
        payment_agent, created = PaymentAgent.objects.get_or_create(
            user=user,
            defaults={'agent_code': secrets.token_hex(3).upper()}
        )

        # Récupérer l'inscription
        inscription = Inscription.objects.select_related(
            'candidature__programme'
        ).get(pk=inscription_id)

        # Créer la session
        session = CashPaymentSession.objects.create(
            inscription=inscription,
            agent=payment_agent,
            verification_code='000000'  # Sera généré lors de la première demande
        )
        session.generate_code()

        # Retourner le code de validation
        response = render(request, 'accounts/dashboard/partials/cash_session_created.html', {
            'session': session
        })
        response['HX-Trigger'] = 'cash-session-created'
        return response

    except Inscription.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Inscription non trouvée.'
        })
    except Exception as e:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': f'Erreur: {str(e)}'
        })


@login_required
def regenerate_code_htmx(request, session_id):
    """
    Endpoint HTMX pour régénérer un code de validation.
    Accessible uniquement aux agents finance.
    """
    from django.http import HttpResponse

    # Vérification de permission
    user = request.user
    if not (user.is_superuser or user_has_group(user, 'finance_agents')):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    try:
        payment_agent = PaymentAgent.objects.get(user=user)
        session = CashPaymentSession.objects.get(
            pk=session_id,
            agent=payment_agent,
            is_used=False
        )

        # Régénérer le code
        session.generate_code()

        # Retourner le nouveau code
        return render(request, 'accounts/dashboard/partials/cash_session_code.html', {
            'session': session
        })

    except CashPaymentSession.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Session non trouvée ou déjà utilisée.'
        })


@login_required
def mark_session_used_htmx(request, session_id):
    """
    Endpoint HTMX pour marquer une session comme utilisée.
    Accessible uniquement aux agents finance.
    """
    from django.http import HttpResponse

    # Vérification de permission
    user = request.user
    if not (user.is_superuser or user_has_group(user, 'finance_agents')):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    try:
        payment_agent = PaymentAgent.objects.get(user=user)
        session = CashPaymentSession.objects.get(
            pk=session_id,
            agent=payment_agent,
            is_used=False
        )

        # Marquer comme utilisée
        session.is_used = True
        session.save()

        # Retourner une réponse vide (l'élément sera supprimé)
        return HttpResponse('')

    except CashPaymentSession.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Session non trouvée.'
        })


@login_required
def reject_candidature_htmx(request, candidature_id):
    """
    Endpoint HTMX pour rejeter une candidature.
    Accessible uniquement aux responsables admissions.
    """
    # Vérification de permission
    user = request.user
    if not (user.is_superuser or user_has_group(user, 'admissions_managers')):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    try:
        candidature = Candidature.objects.select_related('programme').get(
            pk=candidature_id,
            status__in=['submitted', 'under_review', 'to_complete']
        )
    except Candidature.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Candidature non trouvée ou déjà traitée.'
        })

    # Rejet de la candidature
    candidature.status = 'rejected'
    candidature.save()
    candidature.mark_reviewed()

    # Retourner une réponse vide (l'élément sera supprimé)
    from django.http import HttpResponse
    return HttpResponse('')


@login_required
def validate_document_htmx(request, document_id):
    """
    Endpoint HTMX pour valider un document.
    Accessible uniquement aux responsables admissions.
    """
    # Vérification de permission
    user = request.user
    if not (user.is_superuser or user_has_group(user, 'admissions_managers')):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    try:
        document = CandidatureDocument.objects.select_related(
            'candidature', 'document_type'
        ).get(pk=document_id, is_valid=False)
    except CandidatureDocument.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Document non trouvé ou déjà validé.'
        })

    # Validation du document
    document.is_valid = True
    document.save()

    # Retourner une réponse vide (l'élément sera supprimé)
    from django.http import HttpResponse
    return HttpResponse('')









@login_required
def finance_dashboard(request):
    """
    Dashboard de l'agent de paiement.
    Affiche:
    - Statistiques des paiements du jour (agent-specific)
    - Transactions en attente de validation (agent-specific)
    - Sessions de paiement espèces
    - Historique des paiements (agent-specific)
    - Comparaison avec les autres agents (pour directeurs)
    """
    # Vérification de permission
    user = request.user
    is_executive = user.is_superuser or user_has_group(user, 'executive_director')
    is_finance_agent = user.is_superuser or user_has_group(user, 'finance_agents')

    if not (is_executive or is_finance_agent):
        messages.error(request, "Accès refusé. Vous n'avez pas la permission.")
        return redirect('core:home')

    # === RÉCUPÉRER L'AGENT DE PAIEMENT ===
    try:
        payment_agent = PaymentAgent.objects.get(user=user)
    except PaymentAgent.DoesNotExist:
        payment_agent = None

    # === STATISTIQUES ===
    today = timezone.now().date()
    today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
    today_end = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.max.time()))

    # === DONNÉES FILTRÉES PAR AGENT ===
    if payment_agent and not is_executive:
        # Agent de paiement - voir seulement son travail

        # Paiements validés aujourd'hui par CET agent (via session)
        today_session_ids = CashPaymentSession.objects.filter(
            agent=payment_agent,
            created_at__gte=today_start,
            is_used=True
        ).values_list('inscription_id', flat=True)

        daily_payments = Payment.objects.filter(
            paid_at__gte=today_start,
            paid_at__lte=today_end,
            status='validated',
            inscription_id__in=today_session_ids
        )

        # Paiements en attente - voir seulement les inscriptions assignées
        assigned_inscription_ids = CashPaymentSession.objects.filter(
            agent=payment_agent,
            is_used=False,
            expires_at__gte=timezone.now()
        ).values_list('inscription_id', flat=True)

        pending_payments = Payment.objects.filter(
            status='pending',
            inscription_id__in=assigned_inscription_ids
        ).select_related(
            'inscription__candidature__programme'
        ).order_by('-created_at')[:20]

        # Inscriptions en attente de paiement - seulement celles assignées
        inscriptions_pending = Inscription.objects.filter(
            status='created',
            id__in=assigned_inscription_ids
        ).select_related(
            'candidature__programme'
        ).order_by('-created_at')[:20]

        # Tous les paiements du jour pour cet agent
        today_payments = daily_payments.select_related(
            'inscription__candidature__programme'
        ).order_by('-paid_at')[:50]

    else:
        # Directeur ou superuser - voir TOUT
        daily_payments = Payment.objects.filter(
            paid_at__gte=today_start,
            paid_at__lte=today_end,
            status='validated'
        )

        pending_payments = Payment.objects.filter(
            status='pending'
        ).select_related(
            'inscription__candidature__programme'
        ).order_by('-created_at')[:20]

        inscriptions_pending = Inscription.objects.filter(
            status='created'
        ).select_related(
            'candidature__programme'
        ).order_by('-created_at')[:20]

        today_payments = daily_payments.select_related(
            'inscription__candidature__programme'
        ).order_by('-paid_at')[:50]

    # === STATISTIQUES DU JOUR ===
    daily_stats = daily_payments.aggregate(
        count=Count('id'),
        total=Sum('amount')
    )

    # === PAR MÉTHODE DE PAIEMENT ===
    payments_by_method = Payment.objects.filter(
        status='validated'
    ).values('method').annotate(
        count=Count('id'),
        total=Sum('amount')
    )

    # === SESSIONS DE PAIEMENT ESPÈCES ===
    if payment_agent:
        active_sessions = CashPaymentSession.objects.filter(
            agent=payment_agent,
            is_used=False,
            expires_at__gte=timezone.now()
        ).select_related('inscription__candidature').order_by('-created_at')

        today_sessions = CashPaymentSession.objects.filter(
            agent=payment_agent,
            created_at__gte=today_start,
            is_used=True
        ).select_related('inscription__candidature')

        recent_sessions = CashPaymentSession.objects.filter(
            agent=payment_agent
        ).select_related('inscription__candidature').order_by('-created_at')[:10]
    else:
        active_sessions = []
        today_sessions = []
        recent_sessions = []

    # === INSCRIPTIONS DISPONIBLES POUR CRÉATION DE SESSION ===
    if payment_agent and not is_executive:
        assigned_ids = CashPaymentSession.objects.filter(
            agent=payment_agent
        ).values_list('inscription_id', flat=True)

        available_inscriptions = Inscription.objects.filter(
            status='created'
        ).exclude(
            id__in=assigned_ids
        ).select_related(
            'candidature__programme'
        ).order_by('-created_at')[:50]
    else:
        available_inscriptions = Inscription.objects.filter(
            status='created'
        ).select_related(
            'candidature__programme'
        ).order_by('-created_at')[:50]

    # === COMPARAISON DES AGENTS (pour directeurs) ===
    agent_performance = []
    if is_executive:
        all_agents = PaymentAgent.objects.select_related('user').all()

        for agent in all_agents:
            sessions_today = CashPaymentSession.objects.filter(
                agent=agent,
                created_at__gte=today_start
            ).count()

            session_ids = CashPaymentSession.objects.filter(
                agent=agent,
                created_at__gte=today_start,
                is_used=True
            ).values_list('inscription_id', flat=True)

            amount_today = Payment.objects.filter(
                inscription_id__in=session_ids,
                status='validated'
            ).aggregate(total=Sum('amount'))['total'] or 0

            agent_performance.append({
                'agent': agent,
                'user': agent.user,
                'sessions_today': sessions_today,
                'amount_today': amount_today,
            })

        agent_performance.sort(key=lambda x: x['amount_today'], reverse=True)

    context = {
        'daily_stats': daily_stats,
        'pending_payments': pending_payments,
        'today_payments': today_payments,
        'inscriptions_pending': inscriptions_pending,
        'payments_by_method': payments_by_method,
        'dashboard_type': 'finance',
        'payment_agent': payment_agent,
        'active_sessions': active_sessions,
        'today_sessions': today_sessions,
        'recent_sessions': recent_sessions,
        'available_inscriptions': available_inscriptions,
        'agent_performance': agent_performance,
        'is_executive_view': is_executive,
    }

    return render(request, 'accounts/dashboard/finance.html', context)