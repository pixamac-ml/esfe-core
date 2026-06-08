from datetime import date
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.utils import timezone
import logging

from .models import Profile, PayrollEntry, TeacherHonorariumEntry

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
            logger.info(f"Profil créé — user_id={instance.pk}")


# ==========================================================
# SAUVEGARDE DU PROFIL
# ==========================================================
@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """
    Assure que le profil existe.
    """
    profile, created = Profile.objects.get_or_create(user=instance)

    if created:
        logger.info(f"Profil créé pour utilisateur existant — user_id={instance.pk}")


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


# ==========================================================
# PRÉPARATION AUTOMATIQUE FICHE DE PAIE
# ==========================================================
@receiver(post_save, sender=Profile)
def auto_prepare_payroll_on_salary_change(sender, instance, **kwargs):
    """
    Quand salary_base est défini > 0 sur un profil staff (non-enseignant,
    non-étudiant, non-public), le système crée automatiquement la fiche
    de paie du mois en cours si elle n'existe pas.
    """
    if instance.salary_base <= 0:
        return
    if not instance.branch_id:
        return
    if instance.user_type == "public":
        return
    if instance.position in ("student", "teacher"):
        return

    period_month = timezone.now().date().replace(day=1)

    entry, created = PayrollEntry.objects.get_or_create(
        branch_id=instance.branch_id,
        employee=instance.user,
        period_month=period_month,
        defaults={
            "base_salary": instance.salary_base,
            "allowances": 0,
            "deductions": 0,
            "advances": 0,
            "paid_amount": 0,
            "status": PayrollEntry.STATUS_DRAFT,
            "created_by": instance.user,
            "updated_by": instance.user,
            "notes": "Fiche préparée automatiquement (signal post_save Profile).",
        },
    )
    if created:
        logger.info(
            "PayrollEntry auto-créée — user_id=%s branch=%s period=%s amount=%s FCFA",
            instance.user_id,
            instance.branch_id,
            period_month,
            instance.salary_base,
        )
    elif entry.status == PayrollEntry.STATUS_DRAFT and entry.base_salary != instance.salary_base:
        entry.base_salary = instance.salary_base
        entry.updated_by = instance.user
        entry.notes += " [salaire mis à jour automatiquement]"
        entry.save(update_fields=["base_salary", "updated_by", "notes"])


# ==========================================================
# PRÉPARATION AUTOMATIQUE HONORAIRES ENSEIGNANTS
# ==========================================================
@receiver(post_save, sender=Profile)
def auto_prepare_honorarium_on_rate_change(sender, instance, **kwargs):
    """
    Quand teacher_hourly_rate est défini > 0 sur un profil enseignant,
    le système crée automatiquement la fiche d'honoraire du mois en cours.
    """
    if instance.teacher_hourly_rate <= 0:
        return
    if not instance.branch_id:
        return
    if instance.position != "teacher":
        return
    if instance.user_type == "public":
        return

    period_month = timezone.now().date().replace(day=1)

    entry, created = TeacherHonorariumEntry.objects.get_or_create(
        branch_id=instance.branch_id,
        teacher=instance.user,
        period_month=period_month,
        defaults={
            "hourly_rate": instance.teacher_hourly_rate,
            "validated_hours": 0,
            "adjustments": 0,
            "deductions": 0,
            "advances": 0,
            "paid_amount": 0,
            "status": TeacherHonorariumEntry.STATUS_DRAFT,
            "created_by": instance.user,
            "updated_by": instance.user,
            "notes": "Honoraire préparé automatiquement (signal post_save Profile).",
        },
    )
    if created:
        logger.info(
            "TeacherHonorariumEntry auto-créée — user_id=%s branch=%s period=%s rate=%s FCFA/h",
            instance.user_id,
            instance.branch_id,
            period_month,
            instance.teacher_hourly_rate,
        )
    elif entry.status == TeacherHonorariumEntry.STATUS_DRAFT and entry.hourly_rate != instance.teacher_hourly_rate:
        entry.hourly_rate = instance.teacher_hourly_rate
        entry.updated_by = instance.user
        entry.notes += " [tarif mis à jour automatiquement]"
        entry.save(update_fields=["hourly_rate", "updated_by", "notes"])