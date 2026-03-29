"""
Vues pour les dashboards du personnel.
FILTRAGE PAR ANNEXE : Chaque agent ne voit que les données de son annexe.
DG + Superadmin : Voient TOUT + stats comparatives par annexe.

VERSION ENRICHIE :
- Filtres avancés
- Recherche
- Vues détaillées
- Suppression (candidatures rejetées uniquement)
- Stats pour graphiques
- Alertes
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Sum, Q, Avg, F
from django.utils import timezone
from django.http import HttpResponse, JsonResponse
from django.db import transaction
from django.core.paginator import Paginator
from datetime import timedelta, datetime
from django.views.decorators.http import require_POST, require_GET
import secrets
import csv

from admissions.models import Candidature, CandidatureDocument
from inscriptions.models import Inscription
from payments.models import Payment, CashPaymentSession, PaymentAgent
from students.models import Student
from branches.models import Branch
from formations.models import Programme


# =====================================================
# HELPERS
# =====================================================

def user_has_group(user, group_name):
    """Vérifie si l'utilisateur appartient à un groupe."""
    if not user.is_authenticated:
        return False
    return user.groups.filter(name=group_name).exists()


def get_user_branch(user):
    """
    Détection robuste de l'annexe utilisateur.

    Priorité :
    1️⃣ Profile.branch
    2️⃣ PaymentAgent.branch
    3️⃣ Branch.manager
    """

    if user.is_superuser:
        return None

    # 1️⃣ Nouvelle architecture
    try:
        if hasattr(user, "profile") and user.profile.branch:
            return user.profile.branch
    except Exception:
        pass

    # 2️⃣ PaymentAgent
    try:
        agent = PaymentAgent.objects.select_related("branch").get(user=user)
        if agent.branch:
            return agent.branch
    except PaymentAgent.DoesNotExist:
        pass

    # 3️⃣ Manager d'annexe
    managed_branch = Branch.objects.filter(manager=user).first()
    if managed_branch:
        return managed_branch

    return None


def is_global_viewer(user):
    """Utilisateurs ayant accès global."""
    if user.is_superuser:
        return True

    if hasattr(user, "profile") and user.profile.role == "executive":
        return True

    if user_has_group(user, "executive_director"):
        return True

    return False


def check_admissions_access(user):
    return (
        user.is_superuser
        or user_has_group(user, "admissions_managers")
        or getattr(user.profile, "role", None) == "admissions"
    )


def check_finance_access(user):
    return (
        user.is_superuser
        or user_has_group(user, "finance_agents")
        or getattr(user.profile, "role", None) == "finance"
        or is_global_viewer(user)
    )


def check_executive_access(user):
    return (
        user.is_superuser
        or user_has_group(user, "executive_director")
        or getattr(user.profile, "role", None) == "executive"
    )
# =====================================================
# VUE DE REDIRECTION
# =====================================================

@login_required
def dashboard_redirect(request):

    user = request.user

    if user.is_superuser or is_global_viewer(user):
        return redirect("accounts:executive_dashboard")

    if check_admissions_access(user):
        return redirect("accounts:admissions_dashboard")

    if check_finance_access(user):
        return redirect("accounts:finance_dashboard")

    messages.warning(request, "Aucun dashboard disponible.")
    return redirect("core:home")

# =====================================================
# DASHBOARD RESPONSABLE ADMISSIONS (ENRICHI)
# =====================================================

@login_required
def admissions_dashboard(request):
    """
    Dashboard du responsable des dossiers d'admission.
    ENRICHI : Filtres, recherche, stats graphiques, alertes.
    """
    user = request.user
    if not check_admissions_access(user):
        messages.error(request, "Accès refusé.")
        return redirect('core:home')

    user_branch = get_user_branch(user)
    is_global = is_global_viewer(user)

    # === BASE QUERYSET ===
    candidatures_qs = get_base_queryset(user, 'candidature')
    docs_qs = CandidatureDocument.objects.filter(
        candidature__in=candidatures_qs
    ) if candidatures_qs.exists() else CandidatureDocument.objects.none()

    # === FILTRES DEPUIS GET ===
    filter_status = request.GET.get('status', '')
    filter_programme = request.GET.get('programme', '')
    filter_branch = request.GET.get('branch', '')
    filter_date_from = request.GET.get('date_from', '')
    filter_date_to = request.GET.get('date_to', '')
    search_query = request.GET.get('q', '')

    # Appliquer les filtres
    filtered_qs = candidatures_qs

    if filter_status:
        filtered_qs = filtered_qs.filter(status=filter_status)

    if filter_programme:
        filtered_qs = filtered_qs.filter(programme_id=filter_programme)

    if filter_branch and is_global:
        filtered_qs = filtered_qs.filter(branch_id=filter_branch)

    if filter_date_from:
        try:
            date_from = datetime.strptime(filter_date_from, '%Y-%m-%d').date()
            filtered_qs = filtered_qs.filter(submitted_at__date__gte=date_from)
        except ValueError:
            pass

    if filter_date_to:
        try:
            date_to = datetime.strptime(filter_date_to, '%Y-%m-%d').date()
            filtered_qs = filtered_qs.filter(submitted_at__date__lte=date_to)
        except ValueError:
            pass

    if search_query:
        filtered_qs = filtered_qs.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone__icontains=search_query)
        )

    # === STATISTIQUES GLOBALES ===
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    candidacy_stats = candidatures_qs.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status='submitted')),
        under_review=Count('id', filter=Q(status='under_review')),
        accepted=Count('id', filter=Q(status='accepted')),
        rejected=Count('id', filter=Q(status='rejected')),
        to_complete=Count('id', filter=Q(status='to_complete')),
    )

    # Stats pour graphiques
    weekly_candidacies = candidatures_qs.filter(submitted_at__date__gte=week_ago).count()
    monthly_candidacies = candidatures_qs.filter(submitted_at__date__gte=month_ago).count()

    # Candidatures par jour (7 derniers jours) pour graphique
    daily_stats = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        count = candidatures_qs.filter(submitted_at__date=day).count()
        daily_stats.append({
            'date': day.strftime('%d/%m'),
            'count': count
        })

    # Candidatures par programme (top 5)
    by_programme = candidatures_qs.values(
        'programme__title'
    ).annotate(count=Count('id')).order_by('-count')[:5]

    # === ALERTES ===
    alerts = []

    # Candidatures en attente depuis plus de 7 jours
    old_pending = candidatures_qs.filter(
        status__in=['submitted', 'under_review'],
        submitted_at__date__lt=week_ago
    ).count()
    if old_pending > 0:
        alerts.append({
            'type': 'warning',
            'message': f"{old_pending} candidature(s) en attente depuis plus de 7 jours"
        })

    # Documents non validés
    pending_docs_count = docs_qs.filter(is_valid=False).count()
    if pending_docs_count > 10:
        alerts.append({
            'type': 'info',
            'message': f"{pending_docs_count} documents en attente de validation"
        })

    # === LISTES PAGINÉES ===
    # Candidatures filtrées avec pagination
    filtered_qs = filtered_qs.select_related('programme', 'branch').order_by('-submitted_at')
    paginator = Paginator(filtered_qs, 20)
    page_number = request.GET.get('page', 1)
    candidatures_page = paginator.get_page(page_number)

    # Documents non validés (top 30)
    pending_docs = docs_qs.filter(
        is_valid=False
    ).select_related('candidature', 'document_type', 'candidature__branch')[:30]

    # Candidatures en attente de traitement
    pending_candidatures = candidatures_qs.filter(
        status__in=['submitted', 'under_review', 'to_complete']
    ).select_related('programme', 'branch').order_by('-submitted_at')[:20]

    # Candidatures acceptées récemment
    accepted_candidatures = candidatures_qs.filter(
        status='accepted'
    ).select_related('programme', 'branch').order_by('-reviewed_at')[:10]

    # Candidatures rejetées (peuvent être supprimées)
    rejected_candidatures = candidatures_qs.filter(
        status='rejected'
    ).select_related('programme', 'branch').order_by('-reviewed_at')[:20]

    # === Taux de conversion ===
    total_reviewed = candidacy_stats['accepted'] + candidacy_stats['rejected']
    admission_rate = 0
    if total_reviewed > 0:
        admission_rate = round((candidacy_stats['accepted'] / total_reviewed) * 100, 1)

    # === Listes pour filtres ===
    programmes_list = Programme.objects.all().order_by('title')
    branches_list = Branch.objects.filter(is_active=True) if is_global else []
    status_choices = [
        ('submitted', 'Soumise'),
        ('under_review', 'En analyse'),
        ('to_complete', 'À compléter'),
        ('accepted', 'Acceptée'),
        ('rejected', 'Rejetée'),
    ]

    context = {
        # Stats
        'stats': candidacy_stats,
        'weekly_candidacies': weekly_candidacies,
        'monthly_candidacies': monthly_candidacies,
        'admission_rate': admission_rate,
        'daily_stats': daily_stats,
        'by_programme': by_programme,

        # Alertes
        'alerts': alerts,

        # Listes
        'pending_docs': pending_docs,
        'pending_candidatures': pending_candidatures,
        'accepted_candidatures': accepted_candidatures,
        'rejected_candidatures': rejected_candidatures,
        'candidatures_page': candidatures_page,

        # Filtres
        'programmes_list': programmes_list,
        'branches_list': branches_list,
        'status_choices': status_choices,
        'current_filters': {
            'status': filter_status,
            'programme': filter_programme,
            'branch': filter_branch,
            'date_from': filter_date_from,
            'date_to': filter_date_to,
            'q': search_query,
        },

        # Meta
        'dashboard_type': 'admissions',
        'user_branch': user_branch,
        'is_global_view': is_global,
    }

    return render(request, 'accounts/dashboard/admissions.html', context)


# =====================================================
# DASHBOARD AGENT DE PAIEMENT (ENRICHI)
# =====================================================

@login_required
def finance_dashboard(request):
    """
    Dashboard de l'agent de paiement.
    ENRICHI : Filtres, historique, stats graphiques.
    """
    user = request.user
    if not check_finance_access(user):
        messages.error(request, "Accès refusé.")
        return redirect('core:home')

    is_global = is_global_viewer(user)

    # === RÉCUPÉRER L'AGENT DE PAIEMENT ===
    try:
        payment_agent = PaymentAgent.objects.select_related('branch').get(user=user)
        user_branch = payment_agent.branch
    except PaymentAgent.DoesNotExist:
        payment_agent = None
        user_branch = get_user_branch(user)

    # === DATES ===
    today = timezone.now().date()
    today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
    today_end = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.max.time()))
    week_ago = today - timedelta(days=7)
    month_start = today.replace(day=1)
    month_start_dt = timezone.make_aware(timezone.datetime.combine(month_start, timezone.datetime.min.time()))

    # === BASE QUERYSETS ===
    payments_qs = get_base_queryset(user, 'payment')
    inscriptions_qs = get_base_queryset(user, 'inscription')

    # === FILTRES ===
    filter_method = request.GET.get('method', '')
    filter_status = request.GET.get('status', '')
    filter_date_from = request.GET.get('date_from', '')
    filter_date_to = request.GET.get('date_to', '')
    search_query = request.GET.get('q', '')

    filtered_payments = payments_qs

    if filter_method:
        filtered_payments = filtered_payments.filter(method=filter_method)

    if filter_status:
        filtered_payments = filtered_payments.filter(status=filter_status)

    if filter_date_from:
        try:
            date_from = datetime.strptime(filter_date_from, '%Y-%m-%d').date()
            dt_from = timezone.make_aware(timezone.datetime.combine(date_from, timezone.datetime.min.time()))
            filtered_payments = filtered_payments.filter(created_at__gte=dt_from)
        except ValueError:
            pass

    if filter_date_to:
        try:
            date_to = datetime.strptime(filter_date_to, '%Y-%m-%d').date()
            dt_to = timezone.make_aware(timezone.datetime.combine(date_to, timezone.datetime.max.time()))
            filtered_payments = filtered_payments.filter(created_at__lte=dt_to)
        except ValueError:
            pass

    if search_query:
        filtered_payments = filtered_payments.filter(
            Q(inscription__candidature__first_name__icontains=search_query) |
            Q(inscription__candidature__last_name__icontains=search_query) |
            Q(inscription__reference__icontains=search_query)
        )

    # === STATISTIQUES ===
    # Paiements du jour
    daily_payments = payments_qs.filter(
        paid_at__gte=today_start,
        paid_at__lte=today_end,
        status='validated'
    )
    daily_stats = daily_payments.aggregate(
        count=Count('id'),
        total=Sum('amount')
    )

    # Paiements de la semaine
    weekly_payments = payments_qs.filter(
        paid_at__date__gte=week_ago,
        status='validated'
    )
    weekly_stats = weekly_payments.aggregate(
        count=Count('id'),
        total=Sum('amount')
    )

    # Paiements du mois
    monthly_payments = payments_qs.filter(
        paid_at__gte=month_start_dt,
        status='validated'
    )
    monthly_stats = monthly_payments.aggregate(
        count=Count('id'),
        total=Sum('amount')
    )

    # Stats par jour (7 derniers jours) pour graphique
    daily_chart = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_start = timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time()))
        day_end = timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.max.time()))
        day_total = payments_qs.filter(
            paid_at__gte=day_start,
            paid_at__lte=day_end,
            status='validated'
        ).aggregate(total=Sum('amount'))['total'] or 0
        daily_chart.append({
            'date': day.strftime('%d/%m'),
            'total': day_total
        })

    # Par méthode de paiement
    payments_by_method = payments_qs.filter(
        status='validated'
    ).values('method').annotate(
        count=Count('id'),
        total=Sum('amount')
    )

    # === ALERTES ===
    alerts = []

    # Paiements en attente
    pending_count = payments_qs.filter(status='pending').count()
    if pending_count > 0:
        alerts.append({
            'type': 'warning',
            'message': f"{pending_count} paiement(s) en attente de validation"
        })

    # Inscriptions sans paiement depuis plus de 7 jours
    old_unpaid = inscriptions_qs.filter(
        status='created',
        created_at__date__lt=week_ago
    ).count()
    if old_unpaid > 0:
        alerts.append({
            'type': 'info',
            'message': f"{old_unpaid} inscription(s) sans paiement depuis plus de 7 jours"
        })

    # === LISTES ===
    # Paiements en attente
    pending_payments = payments_qs.filter(
        status='pending'
    ).select_related(
        'inscription__candidature__programme',
        'inscription__candidature__branch'
    ).order_by('-created_at')[:20]

    # Paiements du jour
    today_payments = daily_payments.select_related(
        'inscription__candidature__programme',
        'inscription__candidature__branch'
    ).order_by('-paid_at')[:50]

    # Historique des paiements (filtré, paginé)
    filtered_payments = filtered_payments.select_related(
        'inscription__candidature__programme',
        'inscription__candidature__branch'
    ).order_by('-created_at')
    paginator = Paginator(filtered_payments, 20)
    page_number = request.GET.get('page', 1)
    payments_page = paginator.get_page(page_number)

    # Inscriptions en attente de paiement
    inscriptions_pending = inscriptions_qs.filter(
        status__in=['created', 'awaiting_payment', 'partial_paid']
    ).select_related(
        'candidature__programme',
        'candidature__branch'
    ).order_by('-created_at')[:30]

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

    # Inscriptions disponibles pour session
    if is_global:
        available_inscriptions = Inscription.objects.filter(
            status__in=['created', 'awaiting_payment', 'partial_paid']
        ).select_related(
            'candidature__programme',
            'candidature__branch'
        ).order_by('-created_at')[:50]
    elif user_branch:
        available_inscriptions = Inscription.objects.filter(
            status__in=['created', 'awaiting_payment', 'partial_paid'],
            candidature__branch=user_branch
        ).select_related(
            'candidature__programme',
            'candidature__branch'
        ).order_by('-created_at')[:50]
    else:
        available_inscriptions = []

    # === PERFORMANCE AGENTS (DG seulement) ===
    agent_performance = []
    if is_global:
        all_agents = PaymentAgent.objects.filter(is_active=True).select_related('user', 'branch')

        for agent in all_agents:
            session_ids = CashPaymentSession.objects.filter(
                agent=agent,
                is_used=True
            ).values_list('inscription_id', flat=True)

            agent_revenue = Payment.objects.filter(
                inscription_id__in=session_ids,
                status='validated'
            ).aggregate(total=Sum('amount'))['total'] or 0

            agent_monthly = Payment.objects.filter(
                inscription_id__in=session_ids,
                status='validated',
                paid_at__gte=month_start_dt
            ).aggregate(total=Sum('amount'))['total'] or 0

            sessions_today = CashPaymentSession.objects.filter(
                agent=agent,
                created_at__gte=today_start
            ).count()

            agent_performance.append({
                'agent': agent,
                'user': agent.user,
                'branch': agent.branch,
                'sessions_today': sessions_today,
                'total_revenue': agent_revenue,
                'monthly_revenue': agent_monthly,
            })

        agent_performance.sort(key=lambda x: x['total_revenue'], reverse=True)

    # === OPTIONS FILTRES ===
    method_choices = [
        ('cash', 'Espèces'),
        ('mobile_money', 'Mobile Money'),
        ('bank_transfer', 'Virement'),
        ('card', 'Carte bancaire'),
    ]
    payment_status_choices = [
        ('pending', 'En attente'),
        ('validated', 'Validé'),
        ('cancelled', 'Annulé'),
    ]

    context = {
        # Stats
        'daily_stats': daily_stats,
        'weekly_stats': weekly_stats,
        'monthly_stats': monthly_stats,
        'daily_chart': daily_chart,
        'payments_by_method': payments_by_method,

        # Alertes
        'alerts': alerts,

        # Listes
        'pending_payments': pending_payments,
        'today_payments': today_payments,
        'payments_page': payments_page,
        'inscriptions_pending': inscriptions_pending,
        'available_inscriptions': available_inscriptions,

        # Sessions
        'payment_agent': payment_agent,
        'active_sessions': active_sessions,
        'sessions': active_sessions,
        'today_sessions': today_sessions,
        'recent_sessions': recent_sessions,

        # Performance
        'agent_performance': agent_performance,

        # Filtres
        'method_choices': method_choices,
        'payment_status_choices': payment_status_choices,
        'current_filters': {
            'method': filter_method,
            'status': filter_status,
            'date_from': filter_date_from,
            'date_to': filter_date_to,
            'q': search_query,
        },

        # Meta
        'dashboard_type': 'finance',
        'user_branch': user_branch,
        'is_global_view': is_global,
    }

    return render(request, 'accounts/dashboard/finance.html', context)


# =====================================================
# DASHBOARD DIRECTEUR GÉNÉRAL (ENRICHI)
# =====================================================

@login_required
def executive_dashboard(request):
    """
    Dashboard du directeur général.
    ENRICHI : Comparatifs détaillés, alertes, tendances.
    """
    user = request.user
    if not check_executive_access(user):
        messages.error(request, "Accès refusé.")
        return redirect('core:home')

    # === DATES ===
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_start = today.replace(day=1)
    month_start_dt = timezone.make_aware(timezone.datetime.combine(month_start, timezone.datetime.min.time()))
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    last_month_start_dt = timezone.make_aware(timezone.datetime.combine(last_month_start, timezone.datetime.min.time()))

    # === STATISTIQUES GLOBALES ===
    total_students = Student.objects.filter(is_active=True).count()
    total_inscriptions = Inscription.objects.count()
    total_candidatures = Candidature.objects.count()

    total_revenue = Payment.objects.filter(
        status='validated'
    ).aggregate(total=Sum('amount'))['total'] or 0

    monthly_revenue = Payment.objects.filter(
        status='validated',
        paid_at__gte=month_start_dt
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Revenus mois précédent (pour comparaison)
    last_month_revenue = Payment.objects.filter(
        status='validated',
        paid_at__gte=last_month_start_dt,
        paid_at__lt=month_start_dt
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Évolution
    revenue_evolution = 0
    if last_month_revenue > 0:
        revenue_evolution = round(((monthly_revenue - last_month_revenue) / last_month_revenue) * 100, 1)

    # === TENDANCES (7 derniers jours) ===
    daily_revenue = []
    daily_candidatures = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_start = timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time()))
        day_end = timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.max.time()))

        rev = Payment.objects.filter(
            paid_at__gte=day_start,
            paid_at__lte=day_end,
            status='validated'
        ).aggregate(total=Sum('amount'))['total'] or 0

        cand = Candidature.objects.filter(submitted_at__date=day).count()

        daily_revenue.append({'date': day.strftime('%d/%m'), 'total': rev})
        daily_candidatures.append({'date': day.strftime('%d/%m'), 'count': cand})

    # === ALERTES ===
    alerts = []

    # Candidatures en attente depuis longtemps
    old_pending = Candidature.objects.filter(
        status__in=['submitted', 'under_review'],
        submitted_at__date__lt=week_ago
    ).count()
    if old_pending > 0:
        alerts.append({
            'type': 'warning',
            'icon': 'clock',
            'message': f"{old_pending} candidature(s) en attente depuis plus de 7 jours",
            'action_url': '?filter=old_pending'
        })

    # Inscriptions impayées
    unpaid_inscriptions = Inscription.objects.filter(
        status='created',
        created_at__date__lt=week_ago
    ).count()
    if unpaid_inscriptions > 0:
        alerts.append({
            'type': 'danger',
            'icon': 'exclamation-triangle',
            'message': f"{unpaid_inscriptions} inscription(s) sans paiement depuis plus de 7 jours"
        })

    # Paiements en attente
    pending_payments = Payment.objects.filter(status='pending').count()
    if pending_payments > 5:
        alerts.append({
            'type': 'info',
            'icon': 'credit-card',
            'message': f"{pending_payments} paiement(s) en attente de validation"
        })

    # === STATISTIQUES PAR ANNEXE ===
    branches = Branch.objects.filter(is_active=True)
    branch_stats = []

    for branch in branches:
        branch_candidatures = Candidature.objects.filter(branch=branch)
        candidatures_count = branch_candidatures.count()
        candidatures_accepted = branch_candidatures.filter(status='accepted').count()
        candidatures_pending = branch_candidatures.filter(
            status__in=['submitted', 'under_review']
        ).count()

        branch_inscriptions = Inscription.objects.filter(candidature__branch=branch)
        inscriptions_count = branch_inscriptions.count()

        branch_revenue = Payment.objects.filter(
            status='validated',
            inscription__candidature__branch=branch
        ).aggregate(total=Sum('amount'))['total'] or 0

        branch_monthly_revenue = Payment.objects.filter(
            status='validated',
            inscription__candidature__branch=branch,
            paid_at__gte=month_start_dt
        ).aggregate(total=Sum('amount'))['total'] or 0

        agents_count = PaymentAgent.objects.filter(
            branch=branch, is_active=True
        ).count()

        # Taux de conversion
        conversion = 0
        if candidatures_count > 0:
            conversion = round((inscriptions_count / candidatures_count) * 100, 1)

        branch_stats.append({
            'branch': branch,
            'candidatures_total': candidatures_count,
            'candidatures_accepted': candidatures_accepted,
            'candidatures_pending': candidatures_pending,
            'inscriptions_count': inscriptions_count,
            'total_revenue': branch_revenue,
            'monthly_revenue': branch_monthly_revenue,
            'agents_count': agents_count,
            'conversion_rate': conversion,
        })

    branch_stats.sort(key=lambda x: x['total_revenue'], reverse=True)

    # === CLASSEMENT DES AGENTS ===
    agent_ranking = []
    all_agents = PaymentAgent.objects.filter(is_active=True).select_related('user', 'branch')

    for agent in all_agents:
        session_inscription_ids = CashPaymentSession.objects.filter(
            agent=agent,
            is_used=True
        ).values_list('inscription_id', flat=True)

        agent_revenue = Payment.objects.filter(
            inscription_id__in=session_inscription_ids,
            status='validated'
        ).aggregate(total=Sum('amount'))['total'] or 0

        agent_monthly = Payment.objects.filter(
            inscription_id__in=session_inscription_ids,
            status='validated',
            paid_at__gte=month_start_dt
        ).aggregate(total=Sum('amount'))['total'] or 0

        sessions_total = CashPaymentSession.objects.filter(
            agent=agent,
            is_used=True
        ).count()

        agent_ranking.append({
            'agent': agent,
            'branch': agent.branch,
            'total_revenue': agent_revenue,
            'monthly_revenue': agent_monthly,
            'sessions_total': sessions_total,
        })

    agent_ranking.sort(key=lambda x: x['monthly_revenue'], reverse=True)

    # === POPULARITÉ DES PROGRAMMES ===
    programmes_popularity = Inscription.objects.values(
        'candidature__programme__title',
        'candidature__programme__id'
    ).annotate(
        count=Count('id'),
        revenue=Sum('amount_paid')
    ).order_by('-count')[:10]

    # === STATUTS D'ADMISSION ===
    admission_stats = Candidature.objects.values('status').annotate(count=Count('id'))

    # === TAUX DE CONVERSION GLOBAL ===
    conversion_rate = 0
    if total_candidatures > 0:
        conversion_rate = round((total_inscriptions / total_candidatures) * 100, 1)

    # === RÉCENTES ACTIVITÉS ===
    recent_inscriptions = Inscription.objects.select_related(
        'candidature__programme',
        'candidature__branch',
        'candidature'
    ).order_by('-created_at')[:10]

    recent_payments = Payment.objects.filter(
        status='validated'
    ).select_related(
        'inscription__candidature__programme',
        'inscription__candidature__branch',
        'agent__branch'
    ).order_by('-paid_at')[:10]

    programmes_list = Programme.objects.all().order_by('title')

    context = {
        # Stats globales
        'total_students': total_students,
        'total_inscriptions': total_inscriptions,
        'total_candidatures': total_candidatures,
        'total_revenue': total_revenue,
        'monthly_revenue': monthly_revenue,
        'last_month_revenue': last_month_revenue,
        'revenue_evolution': revenue_evolution,
        'conversion_rate': conversion_rate,

        # Tendances
        'daily_revenue': daily_revenue,
        'daily_candidatures': daily_candidatures,

        # Alertes
        'alerts': alerts,

        # Par annexe
        'branches': branches,
        'branch_stats': branch_stats,

        # Agents
        'agent_ranking': agent_ranking[:10],

        # Programmes
        'programmes_popularity': programmes_popularity,
        'admission_stats': admission_stats,
        'programmes_list': programmes_list,

        # Activités récentes
        'recent_inscriptions': recent_inscriptions,
        'recent_payments': recent_payments,

        # Meta
        'dashboard_type': 'executive',
    }

    return render(request, 'accounts/dashboard/executive.html', context)


# =====================================================
# HTMX ENDPOINTS - FINANCE
# =====================================================

@login_required
def validate_payment_htmx(request, payment_id):
    """Valider un paiement."""
    user = request.user
    if not check_finance_access(user):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    user_branch = get_user_branch(user)

    try:
        payment = Payment.objects.select_related(
            'inscription__candidature__programme',
            'inscription__candidature__branch'
        ).get(pk=payment_id, status='pending')

        if not is_global_viewer(user) and user_branch:
            if payment.inscription.candidature.branch != user_branch:
                return render(request, 'accounts/dashboard/partials/error.html', {
                    'message': 'Ce paiement ne fait pas partie de votre annexe.'
                })

    except Payment.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Paiement non trouvé ou déjà traité.'
        })

    with transaction.atomic():
        payment.status = "validated"
        payment.paid_at = timezone.now()
        payment.save(update_fields=["status", "paid_at"])

    return render(request, 'accounts/dashboard/partials/payment_validated.html', {
        'payment': payment
    })


@login_required
def reject_payment_htmx(request, payment_id):
    """Rejeter un paiement."""
    user = request.user
    if not check_finance_access(user):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    user_branch = get_user_branch(user)

    try:
        payment = Payment.objects.select_related(
            'inscription__candidature__branch'
        ).get(pk=payment_id, status='pending')

        if not is_global_viewer(user) and user_branch:
            if payment.inscription.candidature.branch != user_branch:
                return render(request, 'accounts/dashboard/partials/error.html', {
                    'message': 'Ce paiement ne fait pas partie de votre annexe.'
                })

    except Payment.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Paiement non trouvé ou déjà traité.'
        })

    payment.status = 'cancelled'
    payment.save(update_fields=['status'])

    return HttpResponse('')


# =====================================================
# HTMX ENDPOINTS - ADMISSIONS
# =====================================================

@login_required
def approve_candidature_htmx(request, candidature_id):
    """Approuver une candidature ET créer l'inscription."""
    from inscriptions.services import create_inscription_from_candidature

    user = request.user
    if not check_admissions_access(user):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    user_branch = get_user_branch(user)

    try:
        candidature = Candidature.objects.select_related('programme', 'branch').get(
            pk=candidature_id,
            status__in=['submitted', 'under_review', 'to_complete']
        )

        if not is_global_viewer(user) and user_branch:
            if candidature.branch != user_branch:
                return render(request, 'accounts/dashboard/partials/error.html', {
                    'message': 'Cette candidature ne fait pas partie de votre annexe.'
                })

    except Candidature.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Candidature non trouvée ou déjà traitée.'
        })

    if hasattr(candidature, 'inscription'):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Une inscription existe déjà pour cette candidature.'
        })

    programme = candidature.programme
    amount_due = programme.get_inscription_amount_for_year(candidature.entry_year)

    if not amount_due or amount_due <= 0:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': f'Aucun frais configuré pour {programme}.'
        })

    try:
        with transaction.atomic():
            # 1️⃣ ACCEPTER LA CANDIDATURE D'ABORD
            candidature.status = 'accepted'
            candidature.reviewed_at = timezone.now()
            candidature.save(update_fields=['status', 'reviewed_at'])

            # 2️⃣ PUIS créer l'inscription
            inscription = create_inscription_from_candidature(
                candidature=candidature,
                amount_due=amount_due
            )

        # Email notification
        try:
            from admissions.emails import send_candidature_accepted_email
            send_candidature_accepted_email(candidature)
        except Exception:
            pass

        return render(request, 'accounts/dashboard/partials/candidature_approved.html', {
            'candidature': candidature,
            'inscription': inscription
        })

    except Exception as e:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': f'Erreur: {str(e)}'
        })


@login_required
def reject_candidature_htmx(request, candidature_id):
    """Rejeter une candidature."""
    user = request.user
    if not check_admissions_access(user):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    user_branch = get_user_branch(user)

    try:
        candidature = Candidature.objects.select_related('branch').get(
            pk=candidature_id,
            status__in=['submitted', 'under_review', 'to_complete']
        )

        if not is_global_viewer(user) and user_branch:
            if candidature.branch != user_branch:
                return render(request, 'accounts/dashboard/partials/error.html', {
                    'message': 'Cette candidature ne fait pas partie de votre annexe.'
                })

    except Candidature.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Candidature non trouvée ou déjà traitée.'
        })

    candidature.status = 'rejected'
    candidature.reviewed_at = timezone.now()
    candidature.save(update_fields=['status', 'reviewed_at'])

    try:
        from admissions.emails import send_candidature_rejected_email
        send_candidature_rejected_email(candidature)
    except Exception:
        pass

    return HttpResponse('')


@login_required
def set_candidature_under_review_htmx(request, candidature_id):
    """Passer une candidature en cours d'analyse."""
    user = request.user
    if not check_admissions_access(user):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    user_branch = get_user_branch(user)

    try:
        candidature = Candidature.objects.select_related('branch').get(
            pk=candidature_id, status='submitted'
        )

        if not is_global_viewer(user) and user_branch:
            if candidature.branch != user_branch:
                return render(request, 'accounts/dashboard/partials/error.html', {
                    'message': 'Cette candidature ne fait pas partie de votre annexe.'
                })

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
    """Demander de compléter le dossier."""
    user = request.user
    if not check_admissions_access(user):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    user_branch = get_user_branch(user)

    try:
        candidature = Candidature.objects.select_related('branch').get(
            pk=candidature_id,
            status__in=['submitted', 'under_review']
        )

        if not is_global_viewer(user) and user_branch:
            if candidature.branch != user_branch:
                return render(request, 'accounts/dashboard/partials/error.html', {
                    'message': 'Cette candidature ne fait pas partie de votre annexe.'
                })

        candidature.status = 'to_complete'
        candidature.reviewed_at = timezone.now()
        candidature.save(update_fields=['status', 'reviewed_at'])

        # Email notification
        try:
            from admissions.emails import send_candidature_to_complete_email
            send_candidature_to_complete_email(candidature)
        except Exception:
            pass

        return HttpResponse('')

    except Candidature.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Candidature non trouvée ou statut invalide.'
        })


@login_required
def create_inscription_htmx(request, candidature_id):
    """Créer une inscription pour une candidature déjà acceptée."""
    from inscriptions.services import create_inscription_from_candidature

    user = request.user
    if not check_admissions_access(user):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    user_branch = get_user_branch(user)

    try:
        candidature = Candidature.objects.select_related('programme', 'branch').get(
            pk=candidature_id,
            status='accepted'
        )

        if not is_global_viewer(user) and user_branch:
            if candidature.branch != user_branch:
                return render(request, 'accounts/dashboard/partials/error.html', {
                    'message': 'Cette candidature ne fait pas partie de votre annexe.'
                })

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


@login_required
def validate_document_htmx(request, document_id):
    """Valider un document."""
    user = request.user
    if not check_admissions_access(user):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    user_branch = get_user_branch(user)

    try:
        document = CandidatureDocument.objects.select_related(
            'candidature__branch', 'document_type'
        ).get(pk=document_id, is_valid=False)

        if not is_global_viewer(user) and user_branch:
            if document.candidature.branch != user_branch:
                return render(request, 'accounts/dashboard/partials/error.html', {
                    'message': 'Ce document ne fait pas partie de votre annexe.'
                })

    except CandidatureDocument.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Document non trouvé ou déjà validé.'
        })

    document.is_valid = True
    document.save(update_fields=['is_valid'])

    return HttpResponse('')


# =====================================================
# HTMX ENDPOINTS - DÉTAILS & SUPPRESSION (NOUVEAU)
# =====================================================

@login_required
def get_candidature_detail_htmx(request, candidature_id):
    """Obtenir les détails complets d'une candidature."""
    user = request.user
    if not check_admissions_access(user):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    user_branch = get_user_branch(user)

    try:
        candidature = Candidature.objects.select_related(
            'programme', 'branch'
        ).prefetch_related('documents__document_type').get(pk=candidature_id)

        if not is_global_viewer(user) and user_branch:
            if candidature.branch != user_branch:
                return render(request, 'accounts/dashboard/partials/error.html', {
                    'message': 'Cette candidature ne fait pas partie de votre annexe.'
                })

    except Candidature.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Candidature non trouvée.'
        })

    # Vérifier si une inscription existe
    has_inscription = hasattr(candidature, 'inscription')
    inscription = candidature.inscription if has_inscription else None

    return render(request, 'accounts/dashboard/partials/candidature_detail.html', {
        'candidature': candidature,
        'documents': candidature.documents.all(),
        'has_inscription': has_inscription,
        'inscription': inscription,
    })


@login_required
@require_POST
def delete_candidature_htmx(request, candidature_id):
    """
    Supprimer une candidature REJETÉE uniquement.
    Sécurité : seules les candidatures rejetées peuvent être supprimées.
    """
    user = request.user
    if not check_admissions_access(user):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    user_branch = get_user_branch(user)

    try:
        candidature = Candidature.objects.select_related('branch').get(
            pk=candidature_id,
            status='rejected'  # IMPORTANT: Seulement les rejetées
        )

        if not is_global_viewer(user) and user_branch:
            if candidature.branch != user_branch:
                return render(request, 'accounts/dashboard/partials/error.html', {
                    'message': 'Cette candidature ne fait pas partie de votre annexe.'
                })

    except Candidature.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Candidature non trouvée ou non supprimable (seules les rejetées peuvent être supprimées).'
        })

    # Vérifier qu'il n'y a pas d'inscription liée
    if hasattr(candidature, 'inscription'):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Impossible de supprimer: une inscription est liée à cette candidature.'
        })

    # Supprimer les documents d'abord
    candidature.documents.all().delete()

    # Supprimer la candidature
    candidature_name = candidature.full_name
    candidature.delete()

    return render(request, 'accounts/dashboard/partials/candidature_deleted.html', {
        'message': f'Candidature de {candidature_name} supprimée avec succès.'
    })


@login_required
def get_inscription_detail_htmx(request, inscription_id):
    """Obtenir les détails complets d'une inscription."""
    user = request.user
    if not check_finance_access(user):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    user_branch = get_user_branch(user)

    try:
        inscription = Inscription.objects.select_related(
            'candidature__programme',
            'candidature__branch'
        ).prefetch_related('payments').get(pk=inscription_id)

        if not is_global_viewer(user) and user_branch:
            if inscription.candidature.branch != user_branch:
                return render(request, 'accounts/dashboard/partials/error.html', {
                    'message': 'Cette inscription ne fait pas partie de votre annexe.'
                })

    except Inscription.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Inscription non trouvée.'
        })

    payments = inscription.payments.all().order_by('-created_at')

    return render(request, 'accounts/dashboard/partials/inscription_detail.html', {
        'inscription': inscription,
        'candidature': inscription.candidature,
        'payments': payments,
        'balance': inscription.balance,
    })


# =====================================================
# HTMX ENDPOINTS - CASH PAYMENT SESSIONS
# =====================================================

@login_required
def create_cash_session_htmx(request):
    """Créer une session de paiement espèces."""
    user = request.user
    if not check_finance_access(user):
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

    user_branch = get_user_branch(user)

    try:
        payment_agent, created = PaymentAgent.objects.get_or_create(
            user=user,
            defaults={
                'agent_code': secrets.token_hex(3).upper(),
                'branch': user_branch
            }
        )

        inscription = Inscription.objects.select_related(
            'candidature__programme',
            'candidature__branch'
        ).get(pk=inscription_id)

        if not is_global_viewer(user) and user_branch:
            if inscription.candidature.branch != user_branch:
                return render(request, 'accounts/dashboard/partials/error.html', {
                    'message': 'Cette inscription ne fait pas partie de votre annexe.'
                })

        session = CashPaymentSession.objects.create(
            inscription=inscription,
            agent=payment_agent,
            verification_code='000000'
        )
        session.generate_code()

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
    """Régénérer un code de validation."""
    user = request.user
    if not check_finance_access(user):
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

        session.generate_code()

        return render(request, 'accounts/dashboard/partials/cash_session_code.html', {
            'session': session
        })

    except CashPaymentSession.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Session non trouvée ou déjà utilisée.'
        })


@login_required
def mark_session_used_htmx(request, session_id):
    """Marquer une session comme utilisée."""
    user = request.user
    if not check_finance_access(user):
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

        session.is_used = True
        session.save(update_fields=['is_used'])

        return HttpResponse('')

    except CashPaymentSession.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Session non trouvée.'
        })


# =====================================================
# EXPORT CSV (NOUVEAU)
# =====================================================

@login_required
def export_candidatures_csv(request):
    """Exporter les candidatures en CSV."""
    user = request.user
    if not check_admissions_access(user):
        messages.error(request, "Accès refusé.")
        return redirect('accounts:admissions_dashboard')

    candidatures_qs = get_base_queryset(user, 'candidature')

    # Appliquer les mêmes filtres que le dashboard
    filter_status = request.GET.get('status', '')
    filter_programme = request.GET.get('programme', '')

    if filter_status:
        candidatures_qs = candidatures_qs.filter(status=filter_status)
    if filter_programme:
        candidatures_qs = candidatures_qs.filter(programme_id=filter_programme)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="candidatures_{timezone.now().strftime("%Y%m%d")}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Nom', 'Prénom', 'Email', 'Téléphone', 'Programme',
        'Annexe', 'Statut', 'Date soumission', 'Date révision'
    ])

    for c in candidatures_qs.select_related(
            "programme", "branch"
    ).iterator():
        writer.writerow([
            c.last_name,
            c.first_name,
            c.email,
            c.phone,
            c.programme.title if c.programme else '',
            c.branch.name if c.branch else '',
            c.get_status_display(),
            c.submitted_at.strftime('%Y-%m-%d %H:%M') if c.submitted_at else '',
            c.reviewed_at.strftime('%Y-%m-%d %H:%M') if c.reviewed_at else '',
        ])

    return response


@login_required
def export_payments_csv(request):
    """Exporter les paiements en CSV."""
    user = request.user
    if not check_finance_access(user):
        messages.error(request, "Accès refusé.")
        return redirect('accounts:finance_dashboard')

    payments_qs = get_base_queryset(user, 'payment')

    # Filtres
    filter_status = request.GET.get('status', '')
    if filter_status:
        payments_qs = payments_qs.filter(status=filter_status)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="paiements_{timezone.now().strftime("%Y%m%d")}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Référence inscription', 'Candidat', 'Programme', 'Annexe',
        'Montant', 'Méthode', 'Statut', 'Date création', 'Date paiement'
    ])

    for p in payments_qs.select_related(
        'inscription__candidature__programme',
        'inscription__candidature__branch'
    ):
        c = p.inscription.candidature
        writer.writerow([
            p.inscription.reference,
            f"{c.last_name} {c.first_name}",
            c.programme.title if c.programme else '',
            c.branch.name if c.branch else '',
            p.amount,
            p.get_method_display() if hasattr(p, 'get_method_display') else p.method,
            p.get_status_display() if hasattr(p, 'get_status_display') else p.status,
            p.created_at.strftime('%Y-%m-%d %H:%M') if p.created_at else '',
            p.paid_at.strftime('%Y-%m-%d %H:%M') if p.paid_at else '',
        ])

    return response