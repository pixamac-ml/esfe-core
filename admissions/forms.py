# admissions/forms.py

from django import forms
from .models import Candidature
from branches.models import Branch


class CandidatureForm(forms.ModelForm):
    # ==============================
    # CHAMP ANNEXE - EXPLICITE
    # ==============================
    branch = forms.ModelChoiceField(
        queryset=Branch.objects.filter(
            is_active=True,
            accepts_online_registration=True
        ),
        label="Annexe d'inscription",
        empty_label="-- Choisissez votre annexe --",
        help_text="Votre dossier sera traité par cette annexe"
    )

    class Meta:
        model = Candidature
        fields = (
            "branch",  # 👈 AJOUTÉ EN PREMIER
            "first_name",
            "last_name",
            "gender",
            "birth_date",
            "birth_place",
            "phone",
            "email",
            "address",
            "city",
            "country",
        )

        labels = {
            "first_name": "Prénom",
            "last_name": "Nom",
            "gender": "Genre",
            "birth_date": "Date de naissance",
            "birth_place": "Lieu de naissance",
            "phone": "Téléphone",
            "email": "Adresse e-mail",
            "address": "Adresse",
            "city": "Ville",
            "country": "Pays",
        }

        widgets = {
            "birth_date": forms.DateInput(
                attrs={
                    "type": "date",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        base_input_classes = (
            "w-full rounded-lg border border-gray-300 "
            "px-4 py-2 text-gray-900 bg-white "
            "placeholder-gray-400 text-sm "
            "focus:outline-none focus:ring-2 focus:ring-primary-500 "
            "focus:border-primary-500 transition duration-200"
        )

        select_classes = (
            "w-full rounded-lg border border-gray-300 "
            "px-4 py-2 text-gray-900 bg-white text-sm "
            "focus:outline-none focus:ring-2 focus:ring-primary-500 "
            "focus:border-primary-500 transition duration-200"
        )

        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.update({"class": select_classes})
            else:
                field.widget.attrs.update({"class": base_input_classes})

        # Placeholders
        self.fields["first_name"].widget.attrs["placeholder"] = "Votre prénom"
        self.fields["last_name"].widget.attrs["placeholder"] = "Votre nom"
        self.fields["birth_place"].widget.attrs["placeholder"] = "Ville de naissance"
        self.fields["phone"].widget.attrs["placeholder"] = "+223 XX XX XX XX"
        self.fields["email"].widget.attrs["placeholder"] = "exemple@email.com"
        self.fields["address"].widget.attrs["placeholder"] = "Adresse complète"
        self.fields["city"].widget.attrs["placeholder"] = "Votre ville"