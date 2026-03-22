from django import forms
from django_ckeditor_5.widgets import CKEditor5Widget
from django.utils.html import strip_tags

from .models import Topic, Category


class TopicForm(forms.ModelForm):
    """
    Formulaire de création/édition de sujet communautaire.
    Inclut validation métier et styles TailwindCSS intégrés.
    """

    subscribe = forms.BooleanField(
        required=False,
        initial=True,
        label="Suivre automatiquement ce domaine",
        help_text="Recevez des notifications pour les nouvelles réponses."
    )

    class Meta:
        model = Topic
        fields = [
            "title",
            "category",
            "tags",
            "content",
        ]

        widgets = {
            "content": CKEditor5Widget(
                attrs={"class": "django_ckeditor_5"},
                config_name="default",
            ),
        }

        labels = {
            "title": "Titre du sujet",
            "category": "Domaine",
            "tags": "Tags",
            "content": "Contenu",
        }

        help_texts = {
            "title": "Un titre clair et descriptif aide les autres à trouver votre sujet.",
            "category": "Choisissez le domaine le plus pertinent pour votre question.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Classes TailwindCSS réutilisables
        base_input = (
            "w-full border border-gray-300 rounded-xl "
            "px-4 py-3 text-sm text-gray-800 "
            "placeholder-gray-400 "
            "focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 "
            "hover:border-gray-400 "
            "transition-all duration-200"
        )

        select_input = (
            "w-full border border-gray-300 rounded-xl "
            "px-4 py-3 text-sm text-gray-800 bg-white "
            "focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 "
            "hover:border-gray-400 "
            "transition-all duration-200 "
            "cursor-pointer"
        )

        checkbox_input = (
            "w-5 h-5 text-primary-600 border-gray-300 rounded "
            "focus:ring-primary-500 focus:ring-2 "
            "transition-all duration-200 cursor-pointer"
        )

        # Limiter aux catégories actives
        self.fields["category"].queryset = Category.objects.filter(is_active=True)
        self.fields["category"].empty_label = "— Sélectionnez un domaine —"

        # TITLE
        self.fields["title"].widget.attrs.update({
            "class": base_input,
            "placeholder": "Ex : Difficulté en dosage médicamenteux en pédiatrie",
            "autocomplete": "off",
            "maxlength": "200",
        })

        # CATEGORY
        self.fields["category"].widget.attrs.update({
            "class": select_input,
        })

        # TAGS
        self.fields["tags"].widget.attrs.update({
            "class": select_input,
            "data-placeholder": "Sélectionnez jusqu'à 5 tags...",
        })
        self.fields["tags"].help_text = "Maximum 5 tags pour une meilleure organisation."

        # SUBSCRIBE
        self.fields["subscribe"].widget.attrs.update({
            "class": checkbox_input,
        })

    # ======================
    # VALIDATIONS MÉTIER
    # ======================

    def clean_title(self):
        """Validation du titre: minimum 10 caractères, sans espaces superflus."""
        title = self.cleaned_data.get("title")

        if not title:
            raise forms.ValidationError(
                "Le titre est obligatoire."
            )

        title = " ".join(title.split())  # Normalise les espaces

        if len(title) < 10:
            raise forms.ValidationError(
                "Le titre doit contenir au moins 10 caractères pour être suffisamment descriptif."
            )

        if len(title) > 200:
            raise forms.ValidationError(
                "Le titre ne peut pas dépasser 200 caractères."
            )

        # Vérification basique anti-spam
        if title.isupper():
            raise forms.ValidationError(
                "Évitez d'écrire le titre entièrement en majuscules."
            )

        return title

    def clean_content(self):
        """Validation du contenu: minimum 30 caractères de texte brut."""
        content = self.cleaned_data.get("content")

        if not content:
            raise forms.ValidationError(
                "Le contenu ne peut pas être vide."
            )

        # Extraire le texte pur sans balises HTML
        text_only = strip_tags(content).strip()

        if len(text_only) < 30:
            raise forms.ValidationError(
                "Le contenu doit contenir au moins 30 caractères pour être compréhensible."
            )

        return content

    def clean_tags(self):
        """Validation des tags: maximum 5."""
        tags = self.cleaned_data.get("tags")

        if tags and len(tags) > 5:
            raise forms.ValidationError(
                "Vous ne pouvez pas ajouter plus de 5 tags. "
                "Choisissez les plus pertinents."
            )

        return tags

    def clean(self):
        """Validation globale du formulaire."""
        cleaned_data = super().clean()

        # Vérifications croisées si nécessaire
        title = cleaned_data.get("title", "")
        content = cleaned_data.get("content", "")

        # Éviter le contenu dupliqué titre/contenu
        if title and content:
            content_text = strip_tags(content).strip()
            if content_text.lower() == title.lower():
                raise forms.ValidationError(
                    "Le contenu ne peut pas être identique au titre. "
                    "Veuillez développer votre question."
                )

        return cleaned_data


from .models import Report

class ReportForm(forms.ModelForm):
    """Formulaire de signalement de contenu"""

    class Meta:
        model = Report
        fields = ["reason", "details"]

        labels = {
            "reason": "Motif du signalement",
            "details": "Détails supplémentaires",
        }

        widgets = {
            "reason": forms.Select(attrs={
                "class": "w-full border border-gray-300 rounded-xl px-4 py-3 text-sm "
                         "focus:ring-2 focus:ring-red-500/20 focus:border-red-500 "
                         "transition-all duration-200"
            }),
            "details": forms.Textarea(attrs={
                "class": "w-full border border-gray-300 rounded-xl px-4 py-3 text-sm "
                         "placeholder=\"Décrivez le problème en détail (optionnel)...\" "
                         "focus:ring-2 focus:ring-red-500/20 focus:border-red-500 "
                         "transition-all duration-200",
                "rows": 3,
            }),
        }