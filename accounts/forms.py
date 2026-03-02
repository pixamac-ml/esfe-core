from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

from .models import Profile

User = get_user_model()


# ==========================
# INSCRIPTION
# ==========================
class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        base_class = "w-full border border-primary-200 rounded-xl p-4 focus:ring-2 focus:ring-secondary transition"

        self.fields["username"].widget.attrs.update({
            "class": base_class,
            "placeholder": "Choisissez un identifiant"
        })

        self.fields["password1"].widget.attrs.update({
            "class": base_class,
            "placeholder": "Minimum 8 caractères"
        })

        self.fields["password2"].widget.attrs.update({
            "class": base_class,
            "placeholder": "Confirmez votre mot de passe"
        })


# ==========================
# PROFIL
# ==========================
class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["avatar", "bio"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["bio"].widget.attrs.update({
            "class": "w-full border border-primary-200 rounded-xl p-4 focus:ring-2 focus:ring-secondary transition",
            "placeholder": "Décrivez brièvement votre parcours..."
        })


# ==========================
# EMAIL
# ==========================
class EmailUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["email"].widget.attrs.update({
            "class": "w-full border border-primary-200 rounded-xl p-4 focus:ring-2 focus:ring-secondary transition",
            "placeholder": "exemple@domaine.com"
        })