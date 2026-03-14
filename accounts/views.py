from django.shortcuts import render, redirect
from django.contrib.auth import login, get_user_model
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from django.db.models.functions import Coalesce
from django.db.models import Sum, Count  # ← Assure-toi que c'est présent
from .models import Profile
from .forms import CustomUserCreationForm, ProfileForm, EmailUpdateForm

User = get_user_model()


# ==========================================
# INSCRIPTION UTILISATEUR
# ==========================================
def register(request):

    next_url = request.GET.get("next")

    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)

        if form.is_valid():
            user = form.save()

            # création automatique du profil si signal absent
            Profile.objects.get_or_create(user=user)

            login(request, user)

            messages.success(
                request,
                "Bienvenue ! Votre compte a été créé avec succès."
            )

            return redirect(next_url or reverse("community:topic_list"))

    else:
        form = CustomUserCreationForm()

    return render(
        request,
        "accounts/register.html",
        {"form": form}
    )


# ==========================================
# MODIFIER PROFIL
# ==========================================
@login_required
def edit_profile(request):

    profile = request.user.profile

    if request.method == "POST":

        form = ProfileForm(
            request.POST,
            request.FILES,
            instance=profile
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Votre profil a été mis à jour."
            )

            return redirect("accounts:profile")

    else:
        form = ProfileForm(instance=profile)

    return render(
        request,
        "accounts/edit_profile.html",
        {"form": form}
    )


# ==========================================
# MODIFIER EMAIL
# ==========================================
@login_required
def update_email(request):

    if request.method == "POST":

        form = EmailUpdateForm(
            request.POST,
            instance=request.user
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Votre email a été mis à jour."
            )

            return redirect("accounts:profile")

    else:
        form = EmailUpdateForm(instance=request.user)

    return render(
        request,
        "accounts/update_email.html",
        {"form": form}
    )

from django.utils import timezone
# ==========================================
# PROFIL UTILISATEUR (DASHBOARD)
# ==========================================
@login_required
def profile_detail(request):

    user_obj = request.user

    # garantie que le profil existe
    profile, created = Profile.objects.get_or_create(user=user_obj)

    # statistiques rapides (stockées dans Profile)
    stats = {
        "reputation": profile.reputation,
        "topics": profile.total_topics,
        "answers": profile.total_answers,
        "accepted": profile.total_accepted_answers,
        "upvotes": profile.total_upvotes_received,
        "views": profile.total_views_generated,
        "badges": {
            "gold": profile.badge_gold,
            "silver": profile.badge_silver,
            "bronze": profile.badge_bronze,
        }
    }

    # derniers sujets créés par l'utilisateur
    recent_topics = (
        user_obj.community_topics
        .filter(is_deleted=False)
        .select_related("category")
        .only(
            "id",
            "title",
            "slug",
            "created_at",
            "views",
            "category__name"
        )
        .order_by("-created_at")[:5]
    )

    # dernières réponses de l'utilisateur
    recent_answers = (
        user_obj.community_answers
        .filter(is_deleted=False)
        .select_related("topic")
        .only(
            "id",
            "topic",
            "created_at",
            "is_accepted"
        )
        .order_by("-created_at")[:5]
    )

    # mise à jour activité utilisateur
    Profile.objects.filter(pk=profile.pk).update(last_seen=timezone.now())

    context = {
        "user_obj": user_obj,
        "profile": profile,
        "stats": stats,
        "recent_topics": recent_topics,
        "recent_answers": recent_answers,
    }

    return render(
        request,
        "accounts/profile_detail.html",
        context
    )


# =====================================================
# PROFIL - ONGLETS HTMX
# =====================================================

@login_required
def profile_activity(request):
    """Onglet Activité - Affiche l'activité récente"""
    from community.models import Answer, Topic

    # Derniers sujets
    recent_topics = (
        Topic.objects
        .filter(author=request.user, is_deleted=False)
        .select_related("category")
        .order_by("-created_at")[:5]
    )

    # Dernières réponses
    recent_answers = (
        Answer.objects
        .filter(author=request.user, is_deleted=False)
        .select_related("topic")
        .order_by("-created_at")[:5]
    )

    return render(
        request,
        "accounts/partials/profile_activity.html",
        {
            "recent_topics": recent_topics,
            "recent_answers": recent_answers
        }
    )

@login_required
def profile_topics(request):
    """Onglet Sujets - Liste des sujets créés"""
    from community.models import Topic

    topics = (
        Topic.objects
        .filter(author=request.user, is_deleted=False)
        .select_related("category")
        .annotate(answer_count=Count("answers"))
        .order_by("-created_at")
    )

    return render(
        request,
        "accounts/partials/profile_topics.html",
        {"topics": topics}
    )


@login_required
def profile_answers(request):
    """Onglet Réponses - Liste des réponses données"""
    from community.models import Answer

    answers = (
        Answer.objects
        .filter(author=request.user, is_deleted=False)
        .select_related("topic", "topic__author")
        .order_by("-created_at")
    )

    return render(
        request,
        "accounts/partials/profile_answers.html",
        {"answers": answers}
    )


@login_required
def profile_badges(request):
    """Onglet Badges - Affiche les badges et leur progression"""
    from community.models import Answer

    # Calculer les stats pour les badges
    answers_count = Answer.objects.filter(author=request.user, is_deleted=False).count()

    accepted_answers = (
        Answer.objects
        .filter(author=request.user, is_deleted=False)
        .filter(accepted_for_topics__isnull=False)
        .count()
    )

    upvotes_received = (
            Answer.objects
            .filter(author=request.user, is_deleted=False)
            .aggregate(total=Sum("upvotes"))["total"] or 0
    )

    badges = {
        "beginner": {
            "title": "Débutant",
            "description": "Première réponse publiée",
            "icon": "fa-star",
            "color": "text-gray-600",
            "bg": "bg-gray-100",
            "earned": answers_count >= 1,
            "progress": min(answers_count, 1),
            "target": 1,
        },
        "contributor": {
            "title": "Contributeur",
            "description": "10 réponses utiles",
            "icon": "fa-star",
            "color": "text-blue-600",
            "bg": "bg-blue-100",
            "earned": answers_count >= 10,
            "progress": min(answers_count, 10),
            "target": 10,
        },
        "expert": {
            "title": "Expert",
            "description": "50 réponses utiles",
            "icon": "fa-star",
            "color": "text-purple-600",
            "bg": "bg-purple-100",
            "earned": answers_count >= 50,
            "progress": min(answers_count, 50),
            "target": 50,
        },
        "helper": {
            "title": "Aidant",
            "description": "Premiers upvotes reçus",
            "icon": "fa-thumbs-up",
            "color": "text-green-600",
            "bg": "bg-green-100",
            "earned": upvotes_received >= 10,
            "progress": min(upvotes_received, 10),
            "target": 10,
        },
        "specialist": {
            "title": "Spécialiste",
            "description": "5 réponses acceptées",
            "icon": "fa-check-circle",
            "color": "text-emerald-600",
            "bg": "bg-emerald-100",
            "earned": accepted_answers >= 5,
            "progress": min(accepted_answers, 5),
            "target": 5,
        },
    }

    return render(
        request,
        "accounts/partials/profile_badges.html",
        {"badges": badges, "stats": {
            "answers": answers_count,
            "accepted": accepted_answers,
            "upvotes": upvotes_received
        }}
    )


@login_required
def profile_settings(request):
    """Onglet Paramètres - Actions rapides"""
    return render(
        request,
        "accounts/partials/profile_settings.html",
        {}
    )


@login_required
def export_executive_csv(request):
    """Exporter le rapport exécutif complet en CSV."""
    user = request.user
    if not check_executive_access(user):
        messages.error(request, "Accès refusé.")
        return redirect('accounts:executive_dashboard')

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response[
        'Content-Disposition'] = f'attachment; filename="rapport_executif_{timezone.now().strftime("%Y%m%d_%H%M")}.csv"'
    response.write('\ufeff')  # BOM pour Excel

    writer = csv.writer(response, delimiter=';')

    # === DATES ===
    today = timezone.now().date()
    month_start = today.replace(day=1)
    month_start_dt = timezone.make_aware(timezone.datetime.combine(month_start, timezone.datetime.min.time()))

    # === SECTION 1: RÉSUMÉ GLOBAL ===
    writer.writerow(['=== RÉSUMÉ GLOBAL ==='])
    writer.writerow(['Métrique', 'Valeur'])

    total_candidatures = Candidature.objects.count()
    total_inscriptions = Inscription.objects.count()
    total_revenue = Payment.objects.filter(status='validated').aggregate(total=Sum('amount'))['total'] or 0
    monthly_revenue = Payment.objects.filter(
        status='validated', paid_at__gte=month_start_dt
    ).aggregate(total=Sum('amount'))['total'] or 0

    writer.writerow(['Total Candidatures', total_candidatures])
    writer.writerow(['Total Inscriptions', total_inscriptions])
    writer.writerow(['Revenus Totaux (F)', total_revenue])
    writer.writerow(['Revenus du Mois (F)', monthly_revenue])
    writer.writerow(['Taux de Conversion (%)',
                     round((total_inscriptions / total_candidatures * 100), 1) if total_candidatures > 0 else 0])
    writer.writerow([])

    # === SECTION 2: PERFORMANCE PAR ANNEXE ===
    writer.writerow(['=== PERFORMANCE PAR ANNEXE ==='])
    writer.writerow(['Annexe', 'Code', 'Candidatures', 'Acceptées', 'Inscriptions', 'Agents', 'Revenus Total (F)',
                     'Revenus Mois (F)'])

    branches = Branch.objects.filter(is_active=True)
    for branch in branches:
        branch_candidatures = Candidature.objects.filter(branch=branch)
        candidatures_count = branch_candidatures.count()
        candidatures_accepted = branch_candidatures.filter(status='accepted').count()
        inscriptions_count = Inscription.objects.filter(candidature__branch=branch).count()
        agents_count = PaymentAgent.objects.filter(branch=branch, is_active=True).count()

        branch_revenue = Payment.objects.filter(
            status='validated',
            inscription__candidature__branch=branch
        ).aggregate(total=Sum('amount'))['total'] or 0

        branch_monthly = Payment.objects.filter(
            status='validated',
            inscription__candidature__branch=branch,
            paid_at__gte=month_start_dt
        ).aggregate(total=Sum('amount'))['total'] or 0

        writer.writerow([
            branch.name,
            branch.code,
            candidatures_count,
            candidatures_accepted,
            inscriptions_count,
            agents_count,
            branch_revenue,
            branch_monthly
        ])

    writer.writerow([])

    # === SECTION 3: TOP AGENTS ===
    writer.writerow(['=== TOP 10 AGENTS ==='])
    writer.writerow(['Rang', 'Agent', 'Code', 'Annexe', 'Sessions Total', 'Revenus Total (F)', 'Revenus Mois (F)'])

    all_agents = PaymentAgent.objects.filter(is_active=True).select_related('user', 'branch')
    agent_ranking = []

    for agent in all_agents:
        session_ids = CashPaymentSession.objects.filter(
            agent=agent, is_used=True
        ).values_list('inscription_id', flat=True)

        agent_revenue = Payment.objects.filter(
            inscription_id__in=session_ids, status='validated'
        ).aggregate(total=Sum('amount'))['total'] or 0

        agent_monthly = Payment.objects.filter(
            inscription_id__in=session_ids, status='validated', paid_at__gte=month_start_dt
        ).aggregate(total=Sum('amount'))['total'] or 0

        sessions_total = CashPaymentSession.objects.filter(agent=agent, is_used=True).count()

        agent_ranking.append({
            'agent': agent,
            'revenue': agent_revenue,
            'monthly': agent_monthly,
            'sessions': sessions_total
        })

    agent_ranking.sort(key=lambda x: x['revenue'], reverse=True)

    for i, item in enumerate(agent_ranking[:10], 1):
        agent = item['agent']
        writer.writerow([
            i,
            agent.user.get_full_name() or agent.user.username,
            agent.agent_code,
            agent.branch.name if agent.branch else 'Non assigné',
            item['sessions'],
            item['revenue'],
            item['monthly']
        ])

    writer.writerow([])

    # === SECTION 4: TOP PROGRAMMES ===
    writer.writerow(['=== TOP PROGRAMMES ==='])
    writer.writerow(['Rang', 'Programme', 'Inscriptions', 'Revenus (F)'])

    programmes_stats = Inscription.objects.values(
        'candidature__programme__title'
    ).annotate(
        count=Count('id'),
        revenue=Sum('amount_paid')
    ).order_by('-count')[:10]

    for i, prog in enumerate(programmes_stats, 1):
        writer.writerow([
            i,
            prog['candidature__programme__title'],
            prog['count'],
            prog['revenue'] or 0
        ])

    return response
