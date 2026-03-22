# ==========================
# SIGNALS GAMIFICATION
# ==========================
from django.db.models.signals import post_save
from django.dispatch import receiver

from community.models import Topic, Answer, Vote


@receiver(post_save, sender=Topic)
def award_xp_on_topic_create(sender, instance, created, **kwargs):
    """Attribue des XP lors de la création d'un sujet"""
    if created and not instance.is_deleted:
        from community.services.gamification import GamificationService
        GamificationService.award_xp(instance.author, "create_topic")


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