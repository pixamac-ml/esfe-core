# filters.py
from django.db.models import Q

def filter_news(queryset, params):
    categorie = params.get('category')
    search = params.get('q')

    if categorie:
        queryset = queryset.filter(categorie__slug=categorie)

    if search:
        queryset = queryset.filter(
            Q(titre__icontains=search) |
            Q(resume__icontains=search) |
            Q(contenu__icontains=search)
        )

    return queryset
