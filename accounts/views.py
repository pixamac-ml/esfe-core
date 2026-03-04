from django.shortcuts import render, redirect
from django.contrib.auth import login, get_user_model
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from django.db.models.functions import Coalesce

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