from django.contrib.auth import get_user_model
from django.test import Client
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone

from community.models import Category, Topic, Answer, Notification
from community.services.notifications import create_notification

User = get_user_model()

# Setup users non-admin
AUTEUR_USERNAME = "qa_auteur"
MEMBRE_USERNAME = "qa_membre"
PASSWORD = "Test12345!"

auteur, _ = User.objects.get_or_create(
    username=AUTEUR_USERNAME,
    defaults={"email": "qa_auteur@example.com", "is_staff": False, "is_superuser": False},
)
auteur.set_password(PASSWORD)
auteur.is_staff = False
auteur.is_superuser = False
auteur.save(update_fields=["password", "is_staff", "is_superuser"])

membre, _ = User.objects.get_or_create(
    username=MEMBRE_USERNAME,
    defaults={"email": "qa_membre@example.com", "is_staff": False, "is_superuser": False},
)
membre.set_password(PASSWORD)
membre.is_staff = False
membre.is_superuser = False
membre.save(update_fields=["password", "is_staff", "is_superuser"])

cat, _ = Category.objects.get_or_create(name="QA Community", defaults={"is_active": True})
cat.subscribers.add(membre)

with override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"]):
    client_a = Client()
    client_b = Client()
    assert client_a.login(username=AUTEUR_USERNAME, password=PASSWORD)
    assert client_b.login(username=MEMBRE_USERNAME, password=PASSWORD)

    # 1) Create topic
    create_url = reverse("community:create_topic")
    resp_create = client_a.post(
        create_url,
        {
            "title": "Question QA smoke test communautaire",
            "category": cat.id,
            "content": "Ce contenu de test est suffisamment long pour passer la validation formulaire community.",
            "subscribe": "on",
        },
    )
    created_topic = Topic.objects.filter(author=auteur, title__icontains="QA smoke test").order_by("-id").first()
    print("CREATE_TOPIC_STATUS", resp_create.status_code)
    print("TOPIC_CREATED", bool(created_topic))

    if not created_topic:
        raise SystemExit("Topic non cree, test interrompu.")

    # 2) Add answer
    answer_url = reverse("community:add_answer", kwargs={"slug": created_topic.slug})
    resp_answer = client_b.post(answer_url, {"content": "Voici une reponse de test non-admin pour valider le workflow."})
    created_answer = Answer.objects.filter(topic=created_topic, author=membre).order_by("-id").first()
    print("ADD_ANSWER_STATUS", resp_answer.status_code)
    print("ANSWER_CREATED", bool(created_answer))

    if not created_answer:
        raise SystemExit("Reponse non creee, test interrompu.")

    # 3) Vote
    vote_url = reverse("community:vote_answer", kwargs={"answer_id": created_answer.id})
    resp_vote = client_a.post(vote_url, {"value": "1"})
    created_answer.refresh_from_db()
    print("VOTE_STATUS", resp_vote.status_code)
    print("ANSWER_SCORE_AFTER_VOTE", created_answer.score)

    # 4) Accept answer
    accept_url = reverse("community:accept_answer", kwargs={"answer_id": created_answer.id})
    resp_accept = client_a.post(accept_url)
    created_topic.refresh_from_db()
    print("ACCEPT_STATUS", resp_accept.status_code)
    print("ACCEPTED_ANSWER_MATCH", created_topic.accepted_answer_id == created_answer.id)

    # 5) Notifications checks
    notif_for_auteur = Notification.objects.filter(
        user=auteur,
        topic=created_topic,
        notification_type="new_answer",
    ).count()
    notif_for_member = Notification.objects.filter(
        user=membre,
        topic=created_topic,
        notification_type="accepted_answer",
    ).count()
    print("NOTIF_NEW_ANSWER_FOR_AUTEUR", notif_for_auteur)
    print("NOTIF_ACCEPTED_FOR_MEMBER", notif_for_member)
    print("UNREAD_AUTEUR", Notification.objects.filter(user=auteur, is_read=False).count())
    print("UNREAD_MEMBER", Notification.objects.filter(user=membre, is_read=False).count())

    # 6) Email smoke-test with unique topic to avoid deduplication constraint
    email_topic, _ = Topic.objects.get_or_create(
        slug=f"qa-email-topic-{timezone.now().strftime('%Y%m%d%H%M%S')}",
        defaults={
            "title": f"Sujet email QA {timezone.now().strftime('%H%M%S')}",
            "author": auteur,
            "category": cat,
            "content": "Sujet dedie au test email notification.",
        },
    )

    with override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend", DEFAULT_FROM_EMAIL="noreply@example.com"):
        notif_email = create_notification(
            user=membre,
            actor=auteur,
            topic=email_topic,
            notification_type="new_topic",
            send_email=True,
        )
        print("EMAIL_NOTIFICATION_CREATED", bool(notif_email))
        print("EMAIL_SENT_FLAG", bool(notif_email and notif_email.email_sent))

print("SMOKE_TEST_DONE")

