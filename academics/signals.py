from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.urls import reverse

from academics.models import AcademicDiplomaAward, ECGrade
from academics.services.workflow import is_session_complete_for_class
from notifier.models import NotificationMessage
from notifier.services import NotificationBus


@receiver(pre_save, sender=AcademicDiplomaAward)
def diploma_award_track_status(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = sender.objects.get(pk=instance.pk)
            instance._old_status = old.status
        except sender.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=AcademicDiplomaAward)
def diploma_award_notify(sender, instance, created, **kwargs):
    old_status = getattr(instance, "_old_status", None)
    if instance.status != AcademicDiplomaAward.STATUS_DELIVERED:
        return
    if old_status == AcademicDiplomaAward.STATUS_DELIVERED:
        return

    student = instance.student
    user = getattr(student, "user", None)
    if not user or not user.email:
        return

    diploma_url = reverse("academics:diploma_award_detail", args=[instance.id])
    diploma_name = instance.diploma.name if instance.diploma else str(instance.programme)

    NotificationBus.send_email(
        subject=f"Votre diplome {diploma_name} est disponible",
        recipient=user,
        event_type="diploma_ready",
        template_key="diploma_ready",
        context={
            "student_name": str(student),
            "diploma_name": diploma_name,
            "reference": instance.reference,
            "academic_year": instance.academic_year.name,
            "final_average": str(instance.final_average) if instance.final_average else "-",
            "mention": instance.mention,
            "diploma_url": diploma_url,
        },
        priority="high",
    )

    NotificationBus.notify(
        recipient=user,
        actor=instance.delivered_by or instance.prepared_by,
        event_type="diploma_ready",
        title=f"Diplome disponible : {diploma_name}",
        body=f"Votre diplome {diploma_name} ({instance.reference}) a ete delivre. Consultez-le dans la section 'Mes diplomes' de votre portail.",
        source_app="academics",
        priority="high",
        legacy_source="academic_diploma_award",
        legacy_object_id=str(instance.id),
    )


def _directors_of_studies_for_branch(branch):
    from accounts.models import Profile

    return list(
        Profile.objects.select_related("user")
        .filter(position="director_of_studies", branch=branch, user__is_active=True)
        .values_list("user", flat=True)
    )


def _notify_directors_session_complete(branch, semester, session_type):
    from django.contrib.auth import get_user_model

    director_ids = _directors_of_studies_for_branch(branch)
    if not director_ids:
        return
    User = get_user_model()
    directors = User.objects.filter(pk__in=director_ids, is_active=True)
    session_label = "Rattrapage" if session_type == "retake" else "Normale"
    body = (
        f"Toutes les notes de la session {session_label.lower()} ont ete saisies pour la classe "
        f"{semester.academic_class.display_name} (Semestre {semester.number})."
    )
    for director in directors:
        NotificationBus.notify(
            recipient=director,
            event_type="grades_session_complete",
            title=f"Saisie terminee - {semester.academic_class.display_name}",
            body=body,
            source_app="academics",
            priority=NotificationMessage.PRIORITY_NORMAL,
            legacy_source="ec_grade_session_complete",
            legacy_object_id=f"{semester.id}:{session_type}",
        )


@receiver(pre_save, sender=ECGrade)
def ec_grade_track_session_completeness(sender, instance, **kwargs):
    """Memorise, avant sauvegarde, si chaque session etait deja complete pour
    toute la classe - permet de detecter dans le post_save la transition
    incomplete -> complete (et de ne notifier qu'a ce moment-la)."""
    instance._was_normal_complete = False
    instance._was_retake_complete = False
    if not instance.ec_id:
        return
    try:
        semester = instance.ec.ue.semester
    except Exception:
        return
    instance._was_normal_complete = is_session_complete_for_class(semester, "normal")
    instance._was_retake_complete = is_session_complete_for_class(semester, "retake")


@receiver(post_save, sender=ECGrade)
def ec_grade_notify_session_complete(sender, instance, created, **kwargs):
    """Notifie le Directeur des Etudes de l'annexe quand la saisie d'une
    session (normale ou rattrapage) vient de se terminer pour toute la classe."""
    try:
        semester = instance.ec.ue.semester
    except Exception:
        return
    branch = semester.academic_class.branch

    if not getattr(instance, "_was_normal_complete", False) and is_session_complete_for_class(semester, "normal"):
        _notify_directors_session_complete(branch, semester, "normal")
    if not getattr(instance, "_was_retake_complete", False) and is_session_complete_for_class(semester, "retake"):
        _notify_directors_session_complete(branch, semester, "retake")
