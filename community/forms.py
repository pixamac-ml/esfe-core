from django import forms
from django.utils.text import slugify
from django_ckeditor_5.widgets import CKEditor5Widget
from .models import Topic


class TopicForm(forms.ModelForm):

    class Meta:
        model = Topic
        fields = [
            "title",
            "category",
            "tags",
            "content",
            "cover_image",
        ]
        widgets = {
            "content": CKEditor5Widget(config_name="default"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        base_input = (
            "w-full border border-primary-200 rounded-xl "
            "p-4 focus:ring-2 focus:ring-secondary "
            "focus:outline-none transition"
        )

        select_input = (
            "w-full border border-primary-200 rounded-xl "
            "p-4 bg-white focus:ring-2 focus:ring-secondary "
            "focus:outline-none transition"
        )

        file_input = (
            "block w-full text-sm text-gray-600 "
            "file:mr-4 file:py-2 file:px-4 "
            "file:rounded-lg file:border-0 "
            "file:bg-primary-500 file:text-white "
            "hover:file:bg-primary-600 transition"
        )

        # ----------------------
        # TITLE
        # ----------------------
        self.fields["title"].widget.attrs.update({
            "class": base_input,
            "placeholder": "Ex: Difficulté en dosage médicamenteux en pédiatrie",
        })

        # ----------------------
        # CATEGORY
        # ----------------------
        self.fields["category"].widget.attrs.update({
            "class": select_input,
        })

        # ----------------------
        # TAGS
        # ----------------------
        self.fields["tags"].widget.attrs.update({
            "class": select_input,
        })
        self.fields["tags"].help_text = "Maintenez Ctrl (ou Cmd) pour sélectionner plusieurs tags."

        # ----------------------
        # CONTENT (CKEditor)
        # ----------------------
        self.fields["content"].widget.attrs.update({
            "class": "rounded-xl border border-primary-200",
        })

        # ----------------------
        # IMAGE
        # ----------------------
        self.fields["cover_image"].widget.attrs.update({
            "class": file_input,
        })

    # ======================
    # VALIDATIONS MÉTIER
    # ======================

    def clean_title(self):
        title = self.cleaned_data.get("title")

        if not title:
            raise forms.ValidationError("Le titre est obligatoire.")

        if len(title.strip()) < 10:
            raise forms.ValidationError(
                "Le titre doit contenir au moins 10 caractères."
            )

        return title.strip()

    def clean_content(self):
        content = self.cleaned_data.get("content")

        if not content:
            raise forms.ValidationError(
                "Le contenu ne peut pas être vide."
            )

        # Nettoyage basique HTML (évite validation faussée par balises vides)
        text_only = content.strip().replace("&nbsp;", "")

        if len(text_only) < 30:
            raise forms.ValidationError(
                "Le contenu doit être suffisamment détaillé (minimum 30 caractères)."
            )

        return content