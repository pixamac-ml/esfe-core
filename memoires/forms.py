from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

from .models import Memoire

PDF_MAGIC_BYTES = b"%PDF-"

_INPUT_CLASS = "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"


class MemoireForm(forms.ModelForm):
    """Formulaire de dépôt/édition, utilisé par le Super Admin et par django.contrib.admin (filet de secours)."""

    class Meta:
        model = Memoire
        exclude = ["nb_pages", "nombre_vues", "date_publication", "cree_par", "date_depot"]
        widgets = {
            "titre": forms.TextInput(attrs={"class": _INPUT_CLASS}),
            "slug": forms.TextInput(attrs={"class": _INPUT_CLASS, "placeholder": "Auto depuis le titre"}),
            "auteurs": forms.TextInput(attrs={"class": _INPUT_CLASS}),
            "encadreur": forms.TextInput(attrs={"class": _INPUT_CLASS}),
            "filiere": forms.Select(attrs={"class": _INPUT_CLASS}),
            "niveau": forms.Select(attrs={"class": _INPUT_CLASS}),
            "annee": forms.NumberInput(attrs={"class": _INPUT_CLASS}),
            "mots_cles": forms.TextInput(attrs={"class": _INPUT_CLASS, "placeholder": "Séparés par des virgules"}),
            "fichier_source": forms.ClearableFileInput(attrs={"class": _INPUT_CLASS, "accept": "application/pdf"}),
            "statut": forms.Select(attrs={"class": _INPUT_CLASS}),
            "est_mis_en_avant": forms.CheckboxInput(attrs={"class": "h-4 w-4 text-primary-600"}),
        }

    def clean_fichier_source(self):
        fichier = self.cleaned_data.get("fichier_source")
        if not fichier or not hasattr(fichier, "size"):
            # Pas de nouveau fichier envoyé (édition sans changement) -> rien à valider.
            return fichier

        if not fichier.name.lower().endswith(".pdf"):
            raise ValidationError("Le fichier doit avoir l'extension .pdf.")

        max_bytes = settings.MEMOIRE_UPLOAD_MAX_MB * 1024 * 1024
        if fichier.size > max_bytes:
            raise ValidationError(
                f"Le fichier dépasse la taille maximale autorisée ({settings.MEMOIRE_UPLOAD_MAX_MB} Mo)."
            )

        en_tete = fichier.read(len(PDF_MAGIC_BYTES))
        fichier.seek(0)
        if en_tete != PDF_MAGIC_BYTES:
            raise ValidationError("Le contenu du fichier n'est pas un PDF valide.")

        return fichier
