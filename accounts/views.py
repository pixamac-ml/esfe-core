from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib import messages
from django.contrib.auth.forms import UserCreationForm
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from .models import Profile
from .signals import User


def register(request):
    next_url = request.GET.get("next")

    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Bienvenue, votre compte a été créé.")
            return redirect(next_url or reverse("community:topic_list"))
    else:
        form = UserCreationForm()

    return render(request, "accounts/register.html", {"form": form})



from django.contrib.auth.forms import UserChangeForm
from django import forms


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["avatar", "bio"]


@login_required
def edit_profile(request):
    profile = request.user.profile

    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profil mis à jour.")
            return redirect("accounts:edit_profile")
    else:
        form = ProfileForm(instance=profile)

    return render(request, "accounts/edit_profile.html", {"form": form})


from django import forms

class EmailUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["email"]

@login_required
def update_email(request):
    if request.method == "POST":
        form = EmailUpdateForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Email mis à jour.")
            return redirect("accounts:update_email")
    else:
        form = EmailUpdateForm(instance=request.user)

    return render(request, "accounts/update_email.html", {"form": form})


from django.contrib.auth.decorators import login_required

@login_required
def profile_detail(request):
    return render(request, "accounts/profile_detail.html", {
        "user_obj": request.user
    })