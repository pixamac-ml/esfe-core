# ==========================
# SIGNALS GAMIFICATION
# ==========================
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from accounts.models import Profile
from community.models import Topic, Answer, Vote


@receiver(post_save, sender=Topic)
def award_xp_on_topic_create(sender, instance, created, **kwargs):
    """Attribue des XP lors de la création d'un sujet"""
    if created and not instance.is_deleted:
        from community.services.gamification import GamificationService
        GamificationService.award_xp(instance.author, "create_topic")

        today = timezone.now().date()
        topics_today = Topic.objects.filter(
            author=instance.author,
            is_deleted=False,
            created_at__date=today,
        ).count()
        if topics_today == 1:
            GamificationService.award_xp(instance.author, "first_topic_of_day")


@receiver(post_save, sender=Answer)
def award_xp_on_answer_create(sender, instance, created, **kwargs):
    """Attribue des XP lors de la création d'une réponse"""
    if created and not instance.is_deleted:
        from community.services.gamification import GamificationService
        GamificationService.award_xp(instance.author, "create_answer")


@receiver(post_save, sender=Vote)
def award_xp_on_vote(sender, instance, created, **kwargs):
    """Attribue des XP lors d'un vote"""
    if created and instance.value == 1:  # Upvote seulement
        from community.services.gamification import GamificationService
        # XP pour celui qui vote
        GamificationService.award_xp(instance.user, "give_upvote")
        # XP pour celui qui reçoit le vote
        content_author = instance.answer.author if instance.answer else instance.topic.author
        if content_author != instance.user:
            GamificationService.award_xp(content_author, "receive_upvote")


@receiver(user_logged_in)
def award_xp_on_login(sender, request, user, **kwargs):
    """Connexion quotidienne : met à jour la série et attribue les XP une seule fois par jour"""
    from community.services.gamification import GamificationService

    is_new_day = GamificationService.update_daily_streak(user)
    if is_new_day:
        GamificationService.award_xp(user, "daily_login")


@receiver(post_save, sender=Profile)
def award_xp_on_profile_complete(sender, instance, **kwargs):
    """Récompense la complétion du profil (avatar + bio), une seule fois"""
    if not (instance.avatar and instance.bio.strip()):
        return

    from community.models_gamification import XPTransaction
    from community.services.gamification import GamificationService

    already_awarded = XPTransaction.objects.filter(
        user=instance.user, action="complete_profile"
    ).exists()
    if not already_awarded:
        GamificationService.award_xp(instance.user, "complete_profile")
