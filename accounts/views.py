# accounts/views.py

"""
Vues principales du module accounts.

- Authentification (register)
- Profil utilisateur
- Redirection dashboard
"""

import csv

from django.shortcuts import render, redirect
from django.contrib.auth import login, get_user_model
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.utils import timezone
from django.db.models import Sum, Count

from branches.models import Branch
from inscriptions.models import Inscription
from admissions.models import Candidature
from payments.models import Payment, PaymentAgent, CashPaymentSession
from .dashboards.helpers import is_manager

from .models import Profile
from .forms import CustomUserCreationForm, ProfileForm, EmailUpdateForm

from .dashboards.permissions import (
    check_admissions_access,
    check_finance_access,
    check_executive_access,
)


User = get_user_model()


# ==========================================================
# INSCRIPTION UTILISATEUR
# ==========================================================

def register(request):
    """
    Inscription d'un nouvel utilisateur.
    """

    next_url = request.GET.get("next")

    if request.method == "POST":

        form = CustomUserCreationForm(request.POST)

        if form.is_valid():

            user = form.save()

            # Création automatique du profil si signal absent
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


# ==========================================================
# REDIRECTION DASHBOARD
# ==========================================================

@login_required
def dashboard_redirect(request):
    """
    Redirige l'utilisateur vers le dashboard approprié
    selon ses permissions.
    """

    user = request.user

    # Ordre de priorité
    if check_executive_access(user):
        return redirect("accounts:executive_dashboard")

    if check_finance_access(user):
        return redirect("accounts:finance_dashboard")

    if is_manager(user):
        return redirect("accounts:manager_dashboard")

    if check_admissions_access(user):
        return redirect("accounts:admissions_dashboard")

    # Aucun dashboard
    messages.warning(
        request,
        "Vous n'avez accès à aucun dashboard."
    )

    return redirect("accounts:profile")

# ==========================================================
# PROFIL UTILISATEUR
# ==========================================================

@login_required
def profile_detail(request):
    """
    Affiche le profil de l'utilisateur connecté.
    """

    user_obj = request.user

    # Garantie que le profil existe
    profile, created = Profile.objects.get_or_create(user=user_obj)

    # Statistiques rapides
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

    # Derniers sujets créés par l'utilisateur
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

    # Dernières réponses de l'utilisateur
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

    # Mise à jour de l'activité utilisateur
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


# ==========================================================
# MODIFIER PROFIL
# ==========================================================

@login_required
def edit_profile(request):
    """
    Modification du profil utilisateur.
    """

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


# ==========================================================
# MODIFIER EMAIL
# ==========================================================

@login_required
def update_email(request):
    """
    Modification de l'email utilisateur.
    """

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


# ==========================================================
# PROFIL - ONGLETS HTMX
# ==========================================================

@login_required
def profile_activity(request):
    """
    Onglet Activité - Affiche l'activité récente.
    """

    from community.models import Answer, Topic

    # Derniers sujets
    recent_topics = (
        Topic.objects
        .filter(author=request.user, is_deleted=False)
        .select_related("category")
        .annotate(answer_count=Count("answers"))
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
    """
    Onglet Sujets - Liste des sujets créés.
    """

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
    """
    Onglet Réponses - Liste des réponses données.
    """

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
    """
    Onglet Badges - Affiche les badges et leur progression.
    """

    from community.models import Answer

    # Stats pour les badges
    answers_count = (
        Answer.objects
        .filter(author=request.user, is_deleted=False)
        .count()
    )

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
        {
            "badges": badges,
            "stats": {
                "answers": answers_count,
                "accepted": accepted_answers,
                "upvotes": upvotes_received
            }
        }
    )


@login_required
def profile_settings(request):
    """
    Onglet Paramètres - Actions rapides.
    """

    return render(
        request,
        "accounts/partials/profile_settings.html",
        {}
    )
