from django import forms
from .models import Article, Category


class ArticleForm(forms.ModelForm):

    class Meta:
        model = Article
        fields = [
            'title',
            'excerpt',
            'content',
            'category',
            'status',
            'allow_comments',
        ]

        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'w-full rounded-md border-gray-300 focus:ring-blue-500 focus:border-blue-500'
            }),
            'excerpt': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full rounded-md border-gray-300 focus:ring-blue-500 focus:border-blue-500'
            }),
            'content': forms.Textarea(attrs={
                'rows': 8,
                'class': 'w-full rounded-md border-gray-300 focus:ring-blue-500 focus:border-blue-500'
            }),
            'status': forms.Select(attrs={
                'class': 'w-full rounded-md border-gray-300'
            }),
            'allow_comments': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # On limite aux catégories actives uniquement
        self.fields['category'].queryset = Category.objects.filter(is_active=True)

        self.fields['category'].widget.attrs.update({
            'class': 'w-full rounded-md border-gray-300 focus:ring-blue-500 focus:border-blue-500'
        })

        # Labels plus propres
        self.fields['title'].label = "Titre de l’article"
        self.fields['excerpt'].label = "Résumé"
        self.fields['content'].label = "Contenu"
        self.fields['category'].label = "Catégorie"
        self.fields['status'].label = "Statut"
        self.fields['allow_comments'].label = "Autoriser les commentaires"

    def clean_title(self):
        title = self.cleaned_data.get("title")
        if len(title) < 5:
            raise forms.ValidationError("Le titre est trop court.")
        return title


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description', 'is_active']

        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full rounded-md border-gray-300 focus:ring-blue-500 focus:border-blue-500'
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full rounded-md border-gray-300 focus:ring-blue-500 focus:border-blue-500'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-blue-600'
            }),
        }
