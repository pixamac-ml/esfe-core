from django import forms
from django_ckeditor_5.widgets import CKEditor5Widget
from django.utils.html import strip_tags

from .models import Topic, Category


class TopicForm(forms.ModelForm):

    subscribe = forms.BooleanField(
        required=False,
        initial=True,
        label="Suivre automatiquement ce domaine"
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        base_input = (
            "w-full border border-gray-300 rounded-lg "
            "px-4 py-2.5 text-sm "
            "focus:ring-2 focus:ring-primary-500 focus:border-primary-500 "
            "transition"
        )

        select_input = (
            "w-full border border-gray-300 rounded-lg "
            "px-4 py-2.5 text-sm bg-white "
            "focus:ring-2 focus:ring-primary-500 focus:border-primary-500 "
            "transition"
        )

        # limiter aux catégories actives
        self.fields["category"].queryset = Category.objects.filter(is_active=True)

        # TITLE
        self.fields["title"].widget.attrs.update({
            "class": base_input,
            "placeholder": "Ex : Difficulté en dosage médicamenteux en pédiatrie",
        })

        # CATEGORY
        self.fields["category"].widget.attrs.update({
            "class": select_input,
        })

        # TAGS
        self.fields["tags"].widget.attrs.update({
            "class": select_input,
        })

        self.fields["tags"].help_text = "Maximum 5 tags."

    # ======================
    # VALIDATIONS MÉTIER
    # ======================

    def clean_title(self):

        title = self.cleaned_data.get("title")

        if not title:
            raise forms.ValidationError("Le titre est obligatoire.")

        title = title.strip()

        if len(title) < 10:
            raise forms.ValidationError(
                "Le titre doit contenir au moins 10 caractères."
            )

        return title

    def clean_content(self):

        content = self.cleaned_data.get("content")

        if not content:
            raise forms.ValidationError(
                "Le contenu ne peut pas être vide."
            )

        text_only = strip_tags(content).strip()

        if len(text_only) < 30:
            raise forms.ValidationError(
                "Le contenu doit contenir au moins 30 caractères."
            )

        return content

    def clean_tags(self):

        tags = self.cleaned_data.get("tags")

        if tags and len(tags) > 5:
            raise forms.ValidationError(
                "Vous ne pouvez pas ajouter plus de 5 tags."
            )

        return tags