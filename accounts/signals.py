from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from .models import Profile

User = get_user_model()


# ==========================================================
# CRÉATION AUTOMATIQUE DU PROFIL UTILISATEUR
# ==========================================================
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Crée automatiquement un profil lors de la création
    d'un nouvel utilisateur.
    """

    if created:
        Profile.objects.get_or_create(user=instance)


# ==========================================================
# SAUVEGARDE DU PROFIL
# ==========================================================
@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """
    Assure que le profil existe et reste synchronisé
    avec l'utilisateur.
    """

    Profile.objects.get_or_create(user=instance)

    try:
        instance.profile.save()
    except Profile.DoesNotExist:
        Profile.objects.create(user=instance)