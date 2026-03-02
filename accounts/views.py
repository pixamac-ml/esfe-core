from django.shortcuts import render, redirect
from django.contrib.auth import login, get_user_model
from django.contrib import messages
from django.urls import reverse
from django.contrib.auth.decorators import login_required

from .models import Profile
from .forms import CustomUserCreationForm, ProfileForm, EmailUpdateForm

User = get_user_model()


# ==========================
# INSCRIPTION
# ==========================
def register(request):
    next_url = request.GET.get("next")

    if request.method == "POST":
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Bienvenue, votre compte a été créé.")
            return redirect(next_url or reverse("community:topic_list"))
    else:
        form = CustomUserCreationForm()

    return render(request, "accounts/register.html", {"form": form})


# ==========================
# MODIFIER PROFIL
# ==========================
@login_required
def edit_profile(request):
    profile = request.user.profile

    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profil mis à jour.")
            return redirect("accounts:profile")
    else:
        form = ProfileForm(instance=profile)

    return render(request, "accounts/edit_profile.html", {"form": form})


# ==========================
# MODIFIER EMAIL
# ==========================
@login_required
def update_email(request):
    if request.method == "POST":
        form = EmailUpdateForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Email mis à jour.")
            return redirect("accounts:profile")
    else:
        form = EmailUpdateForm(instance=request.user)

    return render(request, "accounts/update_email.html", {"form": form})


# ==========================
# PROFIL UTILISATEUR
# ==========================
@login_required
def profile_detail(request):
    user_obj = request.user

    topics_count = user_obj.community_topics.count()
    answers_count = user_obj.community_answers.count()

    score = sum(answer.score for answer in user_obj.community_answers.all())

    return render(request, "accounts/profile_detail.html", {
        "user_obj": user_obj,
        "topics_count": topics_count,
        "answers_count": answers_count,
        "score": score,
    })


