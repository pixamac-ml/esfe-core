# payments/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Payment


@receiver(post_save, sender=Payment)
def payment_post_save(sender, instance, created, **kwargs):
    """
    Signal volontairement MINIMAL.
    Aucune génération de reçu ici.
    Prévu pour :
    - notifications futures
    - audit
    """

    # Exemple futur (désactivé volontairement)
    # if instance.status == "validated":
    #     notify_accounting(instance)
    pass
