from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

from .models import Profile

User = get_user_model()


# ==========================
# CLASSE CSS DE BASE
# ==========================
INPUT_CLASS = (
    "w-full border border-gray-200 rounded-xl px-4 py-3.5 text-gray-700 "
    "placeholder-gray-400 bg-gray-50/50 "
    "focus:bg-white focus:border-primary-400 focus:ring-2 focus:ring-primary-100 "
    "transition-all duration-200 outline-none"
)

TEXTAREA_CLASS = (
    "w-full border border-gray-200 rounded-xl px-4 py-3.5 text-gray-700 "
    "placeholder-gray-400 bg-gray-50/50 min-h-[120px] resize-none "
    "focus:bg-white focus:border-primary-400 focus:ring-2 focus:ring-primary-100 "
    "transition-all duration-200 outline-none"
)


# ==========================
# INSCRIPTION
# ==========================
class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["username"].widget.attrs.update({
            "class": INPUT_CLASS,
            "placeholder": "Choisissez un identifiant unique"
        })

        self.fields["password1"].widget.attrs.update({
            "class": INPUT_CLASS,
            "placeholder": "Minimum 8 caractères"
        })

        self.fields["password2"].widget.attrs.update({
            "class": INPUT_CLASS,
            "placeholder": "Confirmez votre mot de passe"
        })


# ==========================
# PROFIL COMPLET
# ==========================
class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["avatar", "bio", "location", "main_domain", "website"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Avatar
        self.fields["avatar"].widget.attrs.update({
            "class": "hidden",
            "accept": "image/jpeg,image/png,image/webp",
            "id": "avatar-input"
        })

        # Bio
        self.fields["bio"].widget = forms.Textarea()
        self.fields["bio"].widget.attrs.update({
            "class": TEXTAREA_CLASS,
            "placeholder": "Décrivez votre parcours, spécialité ou centres d'intérêt...",
            "rows": 4
        })

        # Localisation
        self.fields["location"].widget.attrs.update({
            "class": INPUT_CLASS,
            "placeholder": "Ex: Douala, Cameroun"
        })

        # Domaine principal
        self.fields["main_domain"].widget.attrs.update({
            "class": INPUT_CLASS,
            "placeholder": "Ex: Médecine générale, Pédiatrie..."
        })

        # Site web
        self.fields["website"].widget.attrs.update({
            "class": INPUT_CLASS,
            "placeholder": "https://votre-site.com"
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
            "class": INPUT_CLASS,
            "placeholder": "exemple@domaine.com",
            "type": "email"
        })