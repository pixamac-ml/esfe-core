# admissions/forms.py

from django import forms
from .models import Candidature


class CandidatureForm(forms.ModelForm):

    class Meta:
        model = Candidature
        fields = (
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

            # Gestion spécifique des Select
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.update({
                    "class": select_classes
                })
            else:
                field.widget.attrs.update({
                    "class": base_input_classes
                })

        # Placeholders professionnels
        self.fields["first_name"].widget.attrs.update({
            "placeholder": "Votre prénom"
        })

        self.fields["last_name"].widget.attrs.update({
            "placeholder": "Votre nom"
        })

        self.fields["birth_place"].widget.attrs.update({
            "placeholder": "Ville ou commune de naissance"
        })

        self.fields["phone"].widget.attrs.update({
            "placeholder": "+223 XX XX XX XX"
        })

        self.fields["email"].widget.attrs.update({
            "placeholder": "exemple@email.com"
        })

        self.fields["address"].widget.attrs.update({
            "placeholder": "Adresse complète"
        })

        self.fields["city"].widget.attrs.update({
            "placeholder": "Votre ville"
        })
