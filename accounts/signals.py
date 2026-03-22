from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
import logging

from .models import Profile

User = get_user_model()
logger = logging.getLogger(__name__)


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
        profile, was_created = Profile.objects.get_or_create(user=instance)
        if was_created:
            logger.info(f"Profil créé pour le nouvel utilisateur: {instance.username}")


# ==========================================================
# SAUVEGARDE DU PROFIL
# ==========================================================
@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """
    Assure que le profil existe et reste synchronisé
    avec l'utilisateur.
    """
    profile, created = Profile.objects.get_or_create(user=instance)

    if created:
        logger.info(f"Profil créé pour utilisateur existant: {instance.username}")

    # Sauvegarder le profil si des changements sont nécessaires
    profile.save()


# ==========================================================
# UTILITAIRE : CRÉER LES PROFILS MANQUANTS
# ==========================================================
def create_missing_profiles():
    """
    Crée les profils pour tous les utilisateurs qui n'en ont pas.
    À exécuter une seule fois via le shell Django.

    Usage:
        python manage.py shell
        >>> from accounts.signals import create_missing_profiles
        >>> create_missing_profiles()
    """
    users_without_profile = User.objects.filter(profile__isnull=True)
    count = 0

    for user in users_without_profile:
        Profile.objects.create(user=user)
        count += 1
        print(f"✓ Profil créé pour: {user.username}")

    if count == 0:
        print("✅ Tous les utilisateurs ont déjà un profil.")
    else:
        print(f"\n🎉 {count} profil(s) créé(s) avec succès!")

    return count