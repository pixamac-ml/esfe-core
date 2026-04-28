from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

from .models import BranchCashMovement, BranchExpense, PayrollEntry, Profile

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


class PayrollEntryForm(forms.ModelForm):
    class Meta:
        model = PayrollEntry
        fields = [
            "period_month",
            "base_salary",
            "allowances",
            "deductions",
            "advances",
            "notes",
        ]
        widgets = {
            "period_month": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ["period_month", "base_salary", "allowances", "deductions", "advances"]:
            self.fields[field_name].widget.attrs.update({"class": INPUT_CLASS})
        self.fields["notes"].widget.attrs.update({
            "class": TEXTAREA_CLASS,
            "placeholder": "Observations internes sur la paie du mois...",
        })


class BranchExpenseForm(forms.ModelForm):
    class Meta:
        model = BranchExpense
        fields = [
            "title",
            "category",
            "amount",
            "expense_date",
            "supplier",
            "reference",
            "receipt",
            "notes",
        ]
        widgets = {
            "expense_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ["title", "category", "amount", "expense_date", "supplier", "reference"]:
            self.fields[field_name].widget.attrs.update({"class": INPUT_CLASS})
        self.fields["receipt"].widget.attrs.update({
            "class": INPUT_CLASS,
            "accept": ".pdf,image/jpeg,image/png,image/webp",
        })
        self.fields["notes"].widget.attrs.update({
            "class": TEXTAREA_CLASS,
            "placeholder": "Motif, details ou justification interne...",
        })


class BranchCashMovementForm(forms.ModelForm):
    class Meta:
        model = BranchCashMovement
        fields = [
            "movement_type",
            "source",
            "amount",
            "label",
            "movement_date",
            "reference",
            "notes",
        ]
        widgets = {
            "movement_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ["movement_type", "source", "amount", "label", "movement_date", "reference"]:
            self.fields[field_name].widget.attrs.update({"class": INPUT_CLASS})
        self.fields["notes"].widget.attrs.update({
            "class": TEXTAREA_CLASS,
            "placeholder": "Commentaire interne sur ce mouvement...",
        })
