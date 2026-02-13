# managers.py
from django.db import models
from django.utils import timezone


class PublishedNewsManager(models.Manager):
    """
    Manager utilisé exclusivement pour le site public.
    Ne retourne que les actualités publiées et valides.
    """

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(
                status="published",
                published_at__isnull=False,
                published_at__lte=timezone.now(),
            )
        )

    def by_category(self, category_slug):
        return self.get_queryset().filter(
            categorie__slug=category_slug,
            categorie__is_active=True
        )

    def search(self, query):
        return self.get_queryset().filter(
            models.Q(titre__icontains=query)
            | models.Q(resume__icontains=query)
            | models.Q(contenu__icontains=query)
        )
