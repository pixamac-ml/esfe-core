# admissions/forms.py
from django import forms
from .models import Candidature
from formations.models import RequiredDocument


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
        widgets = {
            "birth_date": forms.DateInput(attrs={"type": "date"}),
        }
