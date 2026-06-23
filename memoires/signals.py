import logging

from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

from .models import Memoire, PageMemoire

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Memoire)
def _marquer_passage_en_publie(sender, instance, **kwargs):
    """Renseigne date_publication au premier passage en statut Publié.

    Le rendu des pages n'est pas déclenché ici : il dépend du fichier déjà
    enregistré, donc il est lancé après la sauvegarde (admin.py / management),
    avec un message clair en cas d'échec — pas de tâche asynchrone disponible
    dans ce projet (pas de Celery/RQ).
    """
    if not instance.pk:
        if instance.statut == Memoire.Statut.PUBLIE and not instance.date_publication:
            from django.utils import timezone

            instance.date_publication = timezone.now()
        return

    try:
        ancien_statut = Memoire.objects.values_list("statut", flat=True).get(pk=instance.pk)
    except Memoire.DoesNotExist:
        ancien_statut = None

    devient_publie = instance.statut == Memoire.Statut.PUBLIE and ancien_statut != Memoire.Statut.PUBLIE
    if devient_publie and not instance.date_publication:
        from django.utils import timezone

        instance.date_publication = timezone.now()


@receiver(post_delete, sender=PageMemoire)
def _supprimer_image_page(sender, instance, **kwargs):
    """Django ne supprime pas les fichiers d'un ImageField -> nettoyage explicite."""
    if instance.image:
        instance.image.delete(save=False)


@receiver(post_delete, sender=Memoire)
def _supprimer_fichier_source(sender, instance, **kwargs):
    """Idem pour le PDF source. Les PageMemoire liées sont nettoyées par cascade
    (chacune déclenche _supprimer_image_page ci-dessus). Le cache des pages
    filigranées expire de lui-même (CACHE_TIMEOUT) ; pas de purge ciblée possible
    sans backend de cache à motif (LocMemCache ne le permet pas).
    """
    if instance.fichier_source:
        instance.fichier_source.delete(save=False)
