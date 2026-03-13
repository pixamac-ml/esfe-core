"""
Vues pour les dashboards du personnel.
FILTRAGE PAR ANNEXE : Chaque agent ne voit que les données de son annexe.
DG + Superadmin : Voient TOUT + stats comparatives par annexe.
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Sum, Q
from django.utils import timezone
from django.http import HttpResponse
from django.db import transaction
from datetime import timedelta
import secrets

from admissions.models import Candidature, CandidatureDocument
from inscriptions.models import Inscription
from payments.models import Payment, CashPaymentSession, PaymentAgent
from students.models import Student
from branches.models import Branch


# =====================================================
# HELPERS
# =====================================================

def user_has_group(user, group_name):
    """Vérifie si l'utilisateur appartient à un groupe"""
    if not user.is_authenticated:
        return False
    return user.groups.filter(name=group_name).exists()


def get_user_branch(user):
    """
    Récupère l'annexe assignée à l'utilisateur.
    Cherche dans PaymentAgent ou Branch.manager.
    Retourne None si pas d'annexe (= accès global).
    """
    if user.is_superuser:
        return None  # Superuser voit tout

    # Vérifier si l'user est manager d'une branche
    managed_branch = Branch.objects.filter(manager=user).first()
    if managed_branch:
        return managed_branch

    # Vérifier si l'user est un PaymentAgent avec branch
    try:
        payment_agent = PaymentAgent.objects.select_related('branch').get(user=user)
        if payment_agent.branch:
            return payment_agent.branch
    except PaymentAgent.DoesNotExist:
        pass

    return None  # Pas d'annexe = accès restreint


def is_global_viewer(user):
    """
    Retourne True si l'utilisateur peut voir TOUTES les annexes.
    (Superuser, DG, ou pas d'annexe assignée mais admin)
    """
    if user.is_superuser:
        return True
    if user_has_group(user, 'executive_director'):
        return True
    return False


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

    if user.is_superuser:
        return redirect('accounts:executive_dashboard')

    if user_has_group(user, 'admissions_managers'):
        return redirect('accounts:admissions_dashboard')

    if user_has_group(user, 'finance_agents'):
        return redirect('accounts:finance_dashboard')

    if user_has_group(user, 'executive_director'):
        return redirect('accounts:executive_dashboard')

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
    FILTRÉ PAR ANNEXE : L'agent ne voit que les candidatures de son annexe.
    """
    user = request.user
    if not (user.is_superuser or user_has_group(user, 'admissions_managers')):
        messages.error(request, "Accès refusé. Vous n'avez pas la permission.")
        return redirect('core:home')

    # === DÉTERMINER L'ANNEXE DE L'UTILISATEUR ===
    user_branch = get_user_branch(user)
    is_global = is_global_viewer(user)

    # === BASE QUERYSET (filtré par annexe si nécessaire) ===
    if is_global:
        candidatures_qs = Candidature.objects.all()
        docs_qs = CandidatureDocument.objects.all()
    else:
        if user_branch:
            candidatures_qs = Candidature.objects.filter(branch=user_branch)
            docs_qs = CandidatureDocument.objects.filter(candidature__branch=user_branch)
        else:
            # Pas d'annexe assignée = ne voit rien
            candidatures_qs = Candidature.objects.none()
            docs_qs = CandidatureDocument.objects.none()
            messages.warning(request, "Aucune annexe ne vous est assignée. Contactez l'administrateur.")

    # === STATISTIQUES ===
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)

    candidacy_stats = candidatures_qs.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status='submitted')),
        under_review=Count('id', filter=Q(status='under_review')),
        accepted=Count('id', filter=Q(status='accepted')),
        rejected=Count('id', filter=Q(status='rejected')),
        to_complete=Count('id', filter=Q(status='to_complete')),
    )

    weekly_candidacies = candidatures_qs.filter(
        submitted_at__date__gte=week_ago
    ).count()

    # Documents non validés
    pending_docs = docs_qs.filter(
        is_valid=False
    ).select_related('candidature', 'document_type', 'candidature__branch')[:30]

    # === LISTES ===
    pending_candidatures = candidatures_qs.filter(
        status__in=['submitted', 'under_review', 'to_complete']
    ).select_related('programme', 'branch').order_by('-submitted_at')[:20]

    accepted_candidatures = candidatures_qs.filter(
        status='accepted'
    ).select_related('programme', 'branch').order_by('-reviewed_at')[:10]

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
        # Info annexe
        'user_branch': user_branch,
        'is_global_view': is_global,
    }

    return render(request, 'accounts/dashboard/admissions.html', context)


# =====================================================
# DASHBOARD AGENT DE PAIEMENT
# =====================================================

@login_required
def finance_dashboard(request):
    """
    Dashboard de l'agent de paiement.
    FILTRÉ PAR ANNEXE : L'agent ne voit que les inscriptions/paiements de son annexe.
    """
    user = request.user
    is_global = is_global_viewer(user)
    is_finance_agent = user.is_superuser or user_has_group(user, 'finance_agents')

    if not (is_global or is_finance_agent):
        messages.error(request, "Accès refusé. Vous n'avez pas la permission.")
        return redirect('core:home')

    # === RÉCUPÉRER L'AGENT DE PAIEMENT ET SON ANNEXE ===
    try:
        payment_agent = PaymentAgent.objects.select_related('branch').get(user=user)
        user_branch = payment_agent.branch
    except PaymentAgent.DoesNotExist:
        payment_agent = None
        user_branch = get_user_branch(user)

    # === STATISTIQUES ===
    today = timezone.now().date()
    today_start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
    today_end = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.max.time()))

    # === BASE QUERYSET (filtré par annexe) ===
    if is_global:
        # DG/Superuser : voir TOUT
        payments_qs = Payment.objects.all()
        inscriptions_qs = Inscription.objects.all()
    elif user_branch:
        # Agent avec annexe : filtrer par annexe
        payments_qs = Payment.objects.filter(inscription__candidature__branch=user_branch)
        inscriptions_qs = Inscription.objects.filter(candidature__branch=user_branch)
    else:
        # Pas d'annexe = ne voit rien
        payments_qs = Payment.objects.none()
        inscriptions_qs = Inscription.objects.none()
        messages.warning(request, "Aucune annexe ne vous est assignée.")

    # === PAIEMENTS DU JOUR ===
    daily_payments = payments_qs.filter(
        paid_at__gte=today_start,
        paid_at__lte=today_end,
        status='validated'
    )

    daily_stats = daily_payments.aggregate(
        count=Count('id'),
        total=Sum('amount')
    )

    # === PAIEMENTS EN ATTENTE ===
    pending_payments = payments_qs.filter(
        status='pending'
    ).select_related(
        'inscription__candidature__programme',
        'inscription__candidature__branch'
    ).order_by('-created_at')[:20]

    # === PAIEMENTS DU JOUR ===
    today_payments = daily_payments.select_related(
        'inscription__candidature__programme',
        'inscription__candidature__branch'
    ).order_by('-paid_at')[:50]

    # === INSCRIPTIONS EN ATTENTE DE PAIEMENT ===
    inscriptions_pending = inscriptions_qs.filter(
        status='created'
    ).select_related(
        'candidature__programme',
        'candidature__branch'
    ).order_by('-created_at')[:20]

    # === PAR MÉTHODE DE PAIEMENT ===
    payments_by_method = payments_qs.filter(
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
    if is_global:
        available_inscriptions = Inscription.objects.filter(
            status='created'
        ).select_related(
            'candidature__programme',
            'candidature__branch'
        ).order_by('-created_at')[:50]
    elif user_branch:
        available_inscriptions = Inscription.objects.filter(
            status='created',
            candidature__branch=user_branch
        ).select_related(
            'candidature__programme',
            'candidature__branch'
        ).order_by('-created_at')[:50]
    else:
        available_inscriptions = []

    # === COMPARAISON DES AGENTS (pour DG seulement) ===
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
            })

        agent_performance.sort(key=lambda x: x['total_revenue'], reverse=True)

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
        # Info annexe
        'user_branch': user_branch,
        'is_global_view': is_global,
    }

    return render(request, 'accounts/dashboard/finance.html', context)


# =====================================================
# DASHBOARD DIRECTEUR GÉNÉRAL
# =====================================================

@login_required
def executive_dashboard(request):
    """
    Dashboard du directeur général.
    VUE GLOBALE : Statistiques de TOUTES les annexes + comparatif.
    """
    user = request.user
    if not (user.is_superuser or user_has_group(user, 'executive_director')):
        messages.error(request, "Accès refusé. Vous n'avez pas la permission.")
        return redirect('core:home')

    # === STATISTIQUES GLOBALES ===
    total_students = Student.objects.filter(is_active=True).count()
    total_inscriptions = Inscription.objects.count()
    total_candidatures = Candidature.objects.count()

    total_revenue = Payment.objects.filter(
        status='validated'
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Revenus du mois
    today = timezone.now().date()
    month_start = today.replace(day=1)
    month_start_dt = timezone.make_aware(
        timezone.datetime.combine(month_start, timezone.datetime.min.time())
    )

    monthly_revenue = Payment.objects.filter(
        status='validated',
        paid_at__gte=month_start_dt
    ).aggregate(total=Sum('amount'))['total'] or 0

    # =====================================================
    # 🏫 STATISTIQUES PAR ANNEXE
    # =====================================================
    branches = Branch.objects.filter(is_active=True)

    branch_stats = []
    for branch in branches:
        # Candidatures
        branch_candidatures = Candidature.objects.filter(branch=branch)
        candidatures_count = branch_candidatures.count()
        candidatures_accepted = branch_candidatures.filter(status='accepted').count()
        candidatures_pending = branch_candidatures.filter(
            status__in=['submitted', 'under_review']
        ).count()

        # Inscriptions
        branch_inscriptions = Inscription.objects.filter(candidature__branch=branch)
        inscriptions_count = branch_inscriptions.count()

        # Revenus totaux
        branch_revenue = Payment.objects.filter(
            status='validated',
            inscription__candidature__branch=branch
        ).aggregate(total=Sum('amount'))['total'] or 0

        # Revenus du mois
        branch_monthly_revenue = Payment.objects.filter(
            status='validated',
            inscription__candidature__branch=branch,
            paid_at__gte=month_start_dt
        ).aggregate(total=Sum('amount'))['total'] or 0

        # Agents actifs
        agents_count = PaymentAgent.objects.filter(
            branch=branch, is_active=True
        ).count()

        branch_stats.append({
            'branch': branch,
            'candidatures_total': candidatures_count,
            'candidatures_accepted': candidatures_accepted,
            'candidatures_pending': candidatures_pending,
            'inscriptions_count': inscriptions_count,
            'total_revenue': branch_revenue,
            'monthly_revenue': branch_monthly_revenue,
            'agents_count': agents_count,
        })

    # Trier par chiffre d'affaires
    branch_stats.sort(key=lambda x: x['total_revenue'], reverse=True)

    # =====================================================
    # CLASSEMENT DES AGENTS PAR PERFORMANCE
    # =====================================================
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

        agent_ranking.append({
            'agent': agent,
            'branch': agent.branch,
            'total_revenue': agent_revenue,
            'monthly_revenue': agent_monthly,
        })

    agent_ranking.sort(key=lambda x: x['total_revenue'], reverse=True)

    # === POPULARITÉ DES PROGRAMMES ===
    programmes_popularity = Inscription.objects.values(
        'candidature__programme__title'
    ).annotate(count=Count('id')).order_by('-count')[:5]

    # === PAR STATUT D'ADMISSION ===
    admission_stats = Candidature.objects.values('status').annotate(count=Count('id'))

    # === TAUX DE CONVERSION ===
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
        # Stats par annexe
        'branches': branches,
        'branch_stats': branch_stats,
        'agent_ranking': agent_ranking[:10],
    }

    return render(request, 'accounts/dashboard/executive.html', context)


# =====================================================
# HTMX ENDPOINTS - FINANCE
# =====================================================

@login_required
def validate_payment_htmx(request, payment_id):
    """Endpoint HTMX pour valider un paiement."""
    user = request.user
    if not (user.is_superuser or user_has_group(user, 'finance_agents')):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    # Vérifier que l'agent a accès à ce paiement (même annexe)
    user_branch = get_user_branch(user)

    try:
        payment = Payment.objects.select_related(
            'inscription__candidature__programme',
            'inscription__candidature__branch'
        ).get(pk=payment_id, status='pending')

        # Vérifier l'annexe si l'user n'est pas global
        if not is_global_viewer(user) and user_branch:
            if payment.inscription.candidature.branch != user_branch:
                return render(request, 'accounts/dashboard/partials/error.html', {
                    'message': 'Ce paiement ne fait pas partie de votre annexe.'
                })

    except Payment.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Paiement non trouvé ou déjà traité.'
        })

    payment.status = 'validated'
    payment.save()

    return render(request, 'accounts/dashboard/partials/payment_validated.html', {
        'payment': payment
    })


@login_required
def reject_payment_htmx(request, payment_id):
    """Endpoint HTMX pour rejeter un paiement."""
    user = request.user
    if not (user.is_superuser or user_has_group(user, 'finance_agents')):
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
    payment.save()

    return HttpResponse('')


# =====================================================
# HTMX ENDPOINTS - ADMISSIONS
# =====================================================

@login_required
def approve_candidature_htmx(request, candidature_id):
    """
    Endpoint HTMX pour approuver une candidature ET créer l'inscription.
    ✅ CORRIGÉ : Accepte la candidature D'ABORD, puis crée l'inscription.
    """
    from inscriptions.services import create_inscription_from_candidature

    user = request.user
    if not (user.is_superuser or user_has_group(user, 'admissions_managers')):
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Accès refusé.'
        })

    user_branch = get_user_branch(user)

    try:
        candidature = Candidature.objects.select_related('programme', 'branch').get(
            pk=candidature_id,
            status__in=['submitted', 'under_review', 'to_complete']
        )

        # Vérifier l'annexe
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
            # ✅ 1️⃣ ACCEPTER LA CANDIDATURE D'ABORD
            candidature.status = 'accepted'
            candidature.reviewed_at = timezone.now()
            candidature.save(update_fields=['status', 'reviewed_at'])

            # ✅ 2️⃣ PUIS créer l'inscription (maintenant la validation passe)
            inscription = create_inscription_from_candidature(
                candidature=candidature,
                amount_due=amount_due
            )

        # ✅ Envoyer l'email de notification (après la transaction)
        try:
            from admissions.emails import send_candidature_accepted_email
            send_candidature_accepted_email(candidature)
        except Exception:
            pass  # Ne pas bloquer si l'email échoue

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
    """
    Endpoint HTMX pour rejeter une candidature.
    ✅ CORRIGÉ : Un seul save avec les deux champs.
    """
    user = request.user
    if not (user.is_superuser or user_has_group(user, 'admissions_managers')):
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

    # ✅ CORRIGÉ : Un seul save avec les deux champs
    candidature.status = 'rejected'
    candidature.reviewed_at = timezone.now()
    candidature.save(update_fields=['status', 'reviewed_at'])

    # ✅ Envoyer l'email de notification
    try:
        from admissions.emails import send_candidature_rejected_email
        send_candidature_rejected_email(candidature)
    except Exception:
        pass  # Ne pas bloquer si l'email échoue

    return HttpResponse('')


@login_required
def set_candidature_under_review_htmx(request, candidature_id):
    """Passer une candidature en cours d'analyse."""
    user = request.user
    if not (user.is_superuser or user_has_group(user, 'admissions_managers')):
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
    """Demander au candidat de compléter son dossier."""
    user = request.user
    if not (user.is_superuser or user_has_group(user, 'admissions_managers')):
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
    if not (user.is_superuser or user_has_group(user, 'admissions_managers')):
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
    """Endpoint HTMX pour valider un document."""
    user = request.user
    if not (user.is_superuser or user_has_group(user, 'admissions_managers')):
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
    document.save()

    return HttpResponse('')


# =====================================================
# HTMX ENDPOINTS - CASH PAYMENT SESSIONS
# =====================================================

@login_required
def create_cash_session_htmx(request):
    """Endpoint HTMX pour créer une session de paiement espèces."""
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

    user_branch = get_user_branch(user)

    try:
        # Récupérer ou créer le PaymentAgent
        payment_agent, created = PaymentAgent.objects.get_or_create(
            user=user,
            defaults={
                'agent_code': secrets.token_hex(3).upper(),
                'branch': user_branch
            }
        )

        # Récupérer l'inscription
        inscription = Inscription.objects.select_related(
            'candidature__programme',
            'candidature__branch'
        ).get(pk=inscription_id)

        # Vérifier l'annexe
        if not is_global_viewer(user) and user_branch:
            if inscription.candidature.branch != user_branch:
                return render(request, 'accounts/dashboard/partials/error.html', {
                    'message': 'Cette inscription ne fait pas partie de votre annexe.'
                })

        # Créer la session
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
    """Endpoint HTMX pour régénérer un code de validation."""
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
    """Endpoint HTMX pour marquer une session comme utilisée."""
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

        session.is_used = True
        session.save()

        return HttpResponse('')

    except CashPaymentSession.DoesNotExist:
        return render(request, 'accounts/dashboard/partials/error.html', {
            'message': 'Session non trouvée.'
        })