from datetime import date
from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.utils import timezone
import logging

from .models import (
    InstitutionalProfile,
    PayrollEntry,
    Profile,
    PublicCommunityProfile,
    TeacherHonorariumEntry,
)

User = get_user_model()
logger = logging.getLogger(__name__)


@receiver(pre_save, sender=User)
def remember_user_security_state(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_is_active = None
        return
    instance._previous_is_active = (
        sender.objects.filter(pk=instance.pk)
        .values_list("is_active", flat=True)
        .first()
    )


@receiver(post_save, sender=User)
def revoke_sessions_when_user_is_deactivated(sender, instance, created, **kwargs):
    if created or instance.is_active or instance._previous_is_active is not True:
        return
    from portal.models import AccountSupportState

    if AccountSupportState.objects.filter(user=instance).filter(
        is_suspended=True
    ).exists() or AccountSupportState.objects.filter(user=instance, is_blocked=True).exists():
        return
    from .models import AccountSecurityEvent, AccountSessionRecord
    from .session_policy import log_security_event
    from .session_security import revoke_user_sessions

    log_security_event(user=instance, event_type=AccountSecurityEvent.ACCOUNT_DEACTIVATED)
    revoke_user_sessions(instance, reason=AccountSessionRecord.END_ACCOUNT_RESTRICTED, global_scope=True)


@receiver(pre_save, sender=Profile)
def remember_profile_access_assignment(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_access_assignment = None
        return
    instance._previous_access_assignment = (
        sender.objects.filter(pk=instance.pk)
        .values_list("position", "branch_id")
        .first()
    )


@receiver(post_save, sender=Profile)
def revoke_sessions_when_access_assignment_changes(sender, instance, created, **kwargs):
    previous = getattr(instance, "_previous_access_assignment", None)
    current = (instance.position, instance.branch_id)
    if created or previous is None or previous == current:
        return
    from .models import AccountSecurityEvent, AccountSessionRecord
    from .session_policy import log_security_event
    from .session_security import revoke_user_sessions

    if previous[0] != current[0]:
        log_security_event(
            user=instance.user,
            event_type=AccountSecurityEvent.POSITION_CHANGED,
            metadata={"previous": previous[0] or "", "current": current[0] or ""},
        )
    if previous[1] != current[1]:
        log_security_event(
            user=instance.user,
            event_type=AccountSecurityEvent.BRANCH_CHANGED,
            metadata={"previous_id": previous[1], "current_id": current[1]},
        )
    revoke_user_sessions(instance.user, reason=AccountSessionRecord.END_ADMIN_REVOKED, global_scope=True)


@receiver(pre_save, sender=InstitutionalProfile)
def remember_institutional_access_assignment(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_access_assignment = None
        return
    instance._previous_access_assignment = (
        sender.objects.filter(pk=instance.pk)
        .values_list("position", "branch_id")
        .first()
    )


@receiver(post_save, sender=InstitutionalProfile)
def audit_direct_institutional_assignment_change(sender, instance, created, **kwargs):
    if getattr(instance, "_security_mirror_from_legacy", False):
        return
    previous = getattr(instance, "_previous_access_assignment", None)
    current = (instance.position, instance.branch_id)
    if created or previous is None or previous == current:
        return
    from .models import AccountSecurityEvent, AccountSessionRecord
    from .session_policy import log_security_event
    from .session_security import revoke_user_sessions

    if previous[0] != current[0]:
        log_security_event(
            user=instance.user,
            event_type=AccountSecurityEvent.POSITION_CHANGED,
            metadata={"previous": previous[0] or "", "current": current[0] or ""},
        )
    if previous[1] != current[1]:
        log_security_event(
            user=instance.user,
            event_type=AccountSecurityEvent.BRANCH_CHANGED,
            metadata={"previous_id": previous[1], "current_id": current[1]},
        )
    revoke_user_sessions(instance.user, reason=AccountSessionRecord.END_ADMIN_REVOKED, global_scope=True)


@receiver(pre_delete, sender=InstitutionalProfile)
def audit_direct_institutional_assignment_delete(sender, instance, **kwargs):
    # Quand Profile.position vient d'etre vide, le signal Profile a deja audite
    # la transition et cette suppression n'est que le miroir de compatibilite.
    if Profile.objects.filter(user=instance.user, position="").exists():
        return
    from .models import AccountSecurityEvent, AccountSessionRecord
    from .session_policy import log_security_event
    from .session_security import revoke_user_sessions

    log_security_event(
        user=instance.user,
        event_type=AccountSecurityEvent.POSITION_CHANGED,
        metadata={"previous": instance.position, "current": ""},
    )
    revoke_user_sessions(instance.user, reason=AccountSessionRecord.END_ADMIN_REVOKED, global_scope=True)


@receiver(user_logged_in)
def initialize_logged_in_system_session(sender, request, user, **kwargs):
    from .session_policy import initialize_system_session

    initialize_system_session(
        request,
        user=user,
        log_login=True,
        authentication_method=getattr(request, "_esfe_authentication_method", "password"),
    )


@receiver(user_logged_out)
def audit_voluntary_logout(sender, request, user, **kwargs):
    if not request or not user or getattr(request, "_suppress_security_logout_signal", False):
        return
    from .models import AccountSecurityEvent, AccountSessionRecord
    from .session_policy import SESSION_ID_KEY, close_session_record
    from .session_security import notify_websocket_revocation

    identifier = request.session.get(SESSION_ID_KEY)
    if not identifier:
        return
    close_session_record(
        user=user,
        identifier=identifier,
        reason=AccountSessionRecord.END_VOLUNTARY,
        request=request,
        event_type=AccountSecurityEvent.LOGOUT_VOLUNTARY,
    )
    notify_websocket_revocation(
        user,
        reason=AccountSessionRecord.END_VOLUNTARY,
        identifier=identifier,
    )


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


@receiver(post_save, sender=Profile)
def mirror_legacy_profile_into_split_profiles(sender, instance, **kwargs):
    """Double écriture transitoire tant que les formulaires utilisent Profile."""
    if getattr(instance, "_skip_public_mirror", False):
        return
    PublicCommunityProfile.objects.update_or_create(
        user=instance.user,
        defaults={
            "bio": instance.bio,
            "location": instance.location,
            "website": instance.website,
            "main_domain": instance.main_domain,
            "reputation": instance.reputation,
            "total_topics": instance.total_topics,
            "total_answers": instance.total_answers,
            "total_accepted_answers": instance.total_accepted_answers,
            "total_upvotes_received": instance.total_upvotes_received,
            "total_views_generated": instance.total_views_generated,
            "badge_gold": instance.badge_gold,
            "badge_silver": instance.badge_silver,
            "badge_bronze": instance.badge_bronze,
            "is_public": instance.is_public,
        },
    )
    if instance.position:
        institutional, _created = InstitutionalProfile.objects.get_or_create(
            user=instance.user,
            defaults={"position": instance.position},
        )
        institutional._security_mirror_from_legacy = True
        institutional.position = instance.position
        institutional.branch = instance.branch
        institutional.employee_code = instance.employee_code
        institutional.salary_base = instance.salary_base
        institutional.teacher_hourly_rate = instance.teacher_hourly_rate
        institutional.employment_status = instance.employment_status
        institutional.hire_date = instance.hire_date
        institutional.save()
        del institutional._security_mirror_from_legacy
    else:
        # La suppression explicite d'une affectation SYSTEM ne doit jamais
        # laisser une position institutionnelle fantôme.
        InstitutionalProfile.objects.filter(user=instance.user).delete()


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
