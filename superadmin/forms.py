from django import forms
from django_ckeditor_5.widgets import CKEditor5Widget

from formations.models import Programme

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024


class ProgrammeForm(forms.ModelForm):

    class Meta:
        model = Programme
        fields = [
            'title',
            'short_description',
            'description',
            'cycle',
            'filiere',
            'diploma_awarded',
            'duration_years',
            'learning_outcomes',
            'career_opportunities',
            'program_structure',
            'illustration',
            'meta_title',
            'meta_description',
            'og_image',
            'is_active',
            'is_featured',
        ]

        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Ex: Licence en Sciences Informatiques',
            }),
            'short_description': forms.TextInput(attrs={
                'class': 'form-input',
                'maxlength': 300,
                'placeholder': 'Ex: Formation complète en développement logiciel et algorithmes',
            }),
            'description': CKEditor5Widget(
                attrs={'class': 'django_ckeditor_5'},
                config_name='default',
            ),
            'cycle': forms.Select(attrs={'class': 'form-select'}),
            'filiere': forms.Select(attrs={'class': 'form-select'}),
            'diploma_awarded': forms.Select(attrs={'class': 'form-select'}),
            'duration_years': forms.NumberInput(attrs={
                'class': 'form-input', 'min': 1, 'max': 10,
            }),
            'learning_outcomes': forms.Textarea(attrs={
                'class': 'form-textarea', 'rows': 4,
                'placeholder': '- Maitrise des algorithmes et structures de donnees\n- Programmation orientee objet\n- Gestion de bases de donnees',
            }),
            'career_opportunities': forms.Textarea(attrs={
                'class': 'form-textarea', 'rows': 4,
                'placeholder': '- Developpeur logiciel\n- Ingenieur systeme\n- Analyste de donnees',
            }),
            'program_structure': forms.Textarea(attrs={
                'class': 'form-textarea', 'rows': 4,
                'placeholder': 'Cours theoriques: 60%\nTravaux pratiques: 30%\nStages: 10%',
            }),
            'illustration': forms.FileInput(attrs={
                'class': 'form-input', 'accept': 'image/*',
            }),
            'meta_title': forms.TextInput(attrs={
                'class': 'form-input',
                'maxlength': 70,
                'placeholder': "Ex: Licence en Sciences Informatiques - ESFE",
            }),
            'meta_description': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 3,
                'maxlength': 160,
                'placeholder': "Resume accrocheur affiche dans les partages Facebook et les resultats de recherche.",
            }),
            'og_image': forms.FileInput(attrs={
                'class': 'form-input', 'accept': 'image/*',
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'sr-only'}),
            'is_featured': forms.CheckboxInput(attrs={'class': 'sr-only'}),
        }

        labels = {
            'title': 'Titre du programme',
            'short_description': 'Description courte',
            'description': 'Description',
            'cycle': 'Cycle',
            'filiere': 'Filière',
            'diploma_awarded': 'Diplôme délivré',
            'duration_years': 'Durée (années)',
            'learning_outcomes': 'Compétences acquises',
            'career_opportunities': 'Débouchés professionnels',
            'program_structure': 'Structure pédagogique',
            'illustration': 'Image du programme',
            'meta_title': 'Titre SEO / réseaux sociaux',
            'meta_description': 'Description SEO / réseaux sociaux',
            'og_image': 'Image de partage social',
            'is_active': 'Programme actif',
            'is_featured': 'Programme en vedette',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['duration_years'].initial = 3

    def _clean_image_size(self, field_name):
        uploaded = self.cleaned_data.get(field_name)
        if uploaded and hasattr(uploaded, 'size') and uploaded.size > MAX_IMAGE_SIZE_BYTES:
            raise forms.ValidationError("L'image ne doit pas dépasser 5 Mo.")
        return uploaded

    def clean_illustration(self):
        return self._clean_image_size('illustration')

    def clean_og_image(self):
        return self._clean_image_size('og_image')
