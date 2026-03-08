
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

from admissions.models import Candidature, CandidatureDocument
from inscriptions.models import Inscription
from payments.models import Payment, CashPaymentSession
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

    # === Taux d'admission ===
    total_reviewed = candidacy_stats['accepted'] + candidacy_stats['rejected']
    admission_rate = 0
    if total_reviewed > 0:
        admission_rate = round((candidacy_stats['accepted'] / total_reviewed) * 100, 1)

    context = {
        'stats': candidacy_stats,
        'weekly_candidacies': weekly_candidacies,
        'pending_docs': pending_docs,
        'pending_candidatures': pending_candidatures,
        'accepted_candidatures': accepted_candidatures,
        'admission_rate': admission_rate,
        'dashboard_type': 'admissions',
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

    context = {
        'daily_stats': daily_stats,
        'pending_payments': pending_payments,
        'today_payments': today_payments,
        'inscriptions_pending': inscriptions_pending,
        'payments_by_method': payments_by_method,
        'dashboard_type': 'finance',
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

    # Total inscriptions actives
    total_inscriptions = Inscription.objects.filter(status='active').count()

    # Total candidatures
    total_candidatures = Candidature.objects.count()

    # === REVENUS ===
    # Revenus validés total
    total_revenue = Payment.objects.filter(
        status='validated'
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Revenus ce mois-ci
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_revenue = Payment.objects.filter(
        status='validated',
        paid_at__gte=month_start
    ).aggregate(total=Sum('amount'))['total'] or 0

    # === PAR FORMATION (Top programmes) ===
    programmes_popularity = Inscription.objects.filter(
        status__in=['created', 'active']
    ).values(
        'candidature__programme__title'
    ).annotate(
        count=Count('id')
    ).order_by('-count')[:10]

    # === PAR STATUT D'ADMISSION ===
    admission_stats = Candidature.objects.values('status').annotate(
        count=Count('id')
    )

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

    context = {
        'total_students': total_students,
        'total_inscriptions': total_inscriptions,
        'total_candidatures': total_candidatures,
        'total_revenue': total_revenue,
        'monthly_revenue': monthly_revenue,
        'programmes_popularity': programmes_popularity,
        'admission_stats': admission_stats,
        'recent_inscriptions': recent_inscriptions,
        'recent_payments': recent_payments,
        'dashboard_type': 'executive',
    }

    return render(request, 'accounts/dashboard/executive.html', context)
