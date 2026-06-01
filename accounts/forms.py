from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model

from .models import (
    BranchBankTransfer,
    BranchCashMovement,
    BranchExpense,
    BranchMonthlyClosure,
    Donation,
    PayrollEntry,
    Profile,
    TeacherHonorariumEntry,
    UserPreference,
)

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
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)

    class Meta:
        model = Profile
        fields = [
            "avatar",
            "bio",
            "location",
            "phone",
            "address",
            "main_domain",
            "website",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.user_id:
            self.fields["first_name"].initial = self.instance.user.first_name
            self.fields["last_name"].initial = self.instance.user.last_name

        self.fields["first_name"].widget.attrs.update({
            "class": INPUT_CLASS,
            "placeholder": "Prenom",
        })
        self.fields["last_name"].widget.attrs.update({
            "class": INPUT_CLASS,
            "placeholder": "Nom",
        })

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

        self.fields["phone"].widget.attrs.update({
            "class": INPUT_CLASS,
            "placeholder": "Ex: +237 6 00 00 00 00",
        })

        self.fields["address"].widget.attrs.update({
            "class": INPUT_CLASS,
            "placeholder": "Ex: Quartier, ville, annexe ou adresse administrative",
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

    def save(self, commit=True):
        profile = super().save(commit=False)
        user = profile.user
        user.first_name = self.cleaned_data.get("first_name", "").strip()
        user.last_name = self.cleaned_data.get("last_name", "").strip()
        if commit:
            user.save(update_fields=["first_name", "last_name"])
            profile.save()
        return profile


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


class UserPreferenceForm(forms.ModelForm):
    class Meta:
        model = UserPreference
        fields = [
            "notify_email",
            "notify_in_app",
            "notify_sms",
            "ui_sidebar_collapsed",
            "ui_compact_mode",
            "ui_autorefresh",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        checkbox_class = (
            "h-5 w-5 rounded border-gray-300 text-primary-600 "
            "focus:ring-2 focus:ring-primary-200"
        )
        labels = {
            "notify_email": "Recevoir les notifications par email",
            "notify_in_app": "Recevoir les notifications dans la plateforme",
            "notify_sms": "Recevoir les alertes critiques par SMS",
            "ui_sidebar_collapsed": "Ouvrir les espaces avec barre laterale reduite",
            "ui_compact_mode": "Activer l'affichage compact",
            "ui_autorefresh": "Autoriser l'actualisation automatique des widgets",
        }
        for field_name, field in self.fields.items():
            field.widget.attrs.update({"class": checkbox_class})
            field.label = labels[field_name]


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


class TeacherHonorariumEntryForm(forms.ModelForm):
    class Meta:
        model = TeacherHonorariumEntry
        fields = [
            "period_month",
            "hourly_rate",
            "validated_hours",
            "adjustments",
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
        for field_name in ["period_month", "hourly_rate", "validated_hours", "adjustments", "deductions", "advances"]:
            self.fields[field_name].widget.attrs.update({"class": INPUT_CLASS})
        self.fields["notes"].widget.attrs.update({
            "class": TEXTAREA_CLASS,
            "placeholder": "Observations internes sur les honoraires du mois...",
        })


class BranchMonthlyClosureForm(forms.ModelForm):
    class Meta:
        model = BranchMonthlyClosure
        fields = [
            "period_month",
            "bank_transfer_amount",
            "notes",
        ]
        widgets = {
            "period_month": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ["period_month", "bank_transfer_amount"]:
            self.fields[field_name].widget.attrs.update({"class": INPUT_CLASS})
        self.fields["bank_transfer_amount"].required = False
        self.fields["notes"].widget.attrs.update({
            "class": TEXTAREA_CLASS,
            "placeholder": "Motif de cloture ou observations de fin de periode...",
        })


class BranchBankTransferForm(forms.ModelForm):
    class Meta:
        model = BranchBankTransfer
        fields = [
            "bank_name",
            "reference",
            "transfer_date",
            "amount",
            "proof",
            "comment",
        ]
        widgets = {
            "transfer_date": forms.DateInput(attrs={"type": "date"}),
            "comment": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ["bank_name", "reference", "transfer_date", "amount"]:
            self.fields[field_name].widget.attrs.update({"class": INPUT_CLASS})
            self.fields[field_name].required = False
        self.fields["proof"].widget.attrs.update({
            "class": INPUT_CLASS,
            "accept": ".pdf,image/jpeg,image/png,image/webp",
        })
        self.fields["proof"].required = False
        self.fields["comment"].widget.attrs.update({
            "class": TEXTAREA_CLASS,
            "placeholder": "Commentaire interne sur le versement bancaire...",
        })
        self.fields["comment"].required = False


class BranchExpenseForm(forms.ModelForm):
    class Meta:
        model = BranchExpense
        fields = [
            "title",
            "category",
            "amount",
            "expense_date",
            "supplier",
            "receipt",
            "notes",
        ]
        widgets = {
            "expense_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ["title", "category", "amount", "expense_date", "supplier"]:
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
            "notes",
        ]
        widgets = {
            "movement_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ["movement_type", "source", "amount", "label", "movement_date"]:
            self.fields[field_name].widget.attrs.update({"class": INPUT_CLASS})
        self.fields["notes"].widget.attrs.update({
            "class": TEXTAREA_CLASS,
            "placeholder": "Commentaire interne sur ce mouvement...",
        })


class DonationForm(forms.ModelForm):
    class Meta:
        model = Donation
        fields = [
            "donor_name",
            "amount",
            "date",
            "motif",
            "payment_method",
            "description",
            "receipt_number",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ["donor_name", "amount", "date", "motif", "payment_method", "receipt_number"]:
            self.fields[field_name].widget.attrs.update({"class": INPUT_CLASS})
        self.fields["description"].widget.attrs.update({
            "class": TEXTAREA_CLASS,
            "placeholder": "Remerciements ou note...",
        })
