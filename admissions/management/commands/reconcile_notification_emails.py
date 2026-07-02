from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
from django.utils import timezone

from admissions.emails import send_notification_email
from notifier.models import NotificationMessage


class Command(BaseCommand):
    help = "Audit/reprise des notifications email centralisees en attente (report, send, mark-sent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--action",
            choices=["report", "send", "mark-sent"],
            default="report",
            help="Action a executer sur les notifications non envoyees.",
        )
        parser.add_argument(
            "--notification-type",
            action="append",
            dest="types",
            help="Filtrer par type de notification (option reutilisable).",
        )
        parser.add_argument(
            "--older-than-days",
            type=int,
            default=None,
            help="Filtrer les notifications creees avant N jours.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Limiter le nombre de notifications traitees.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Confirmer explicitement les actions send/mark-sent.",
        )

    def handle(self, *args, **options):
        action = options["action"]
        selected_types = options.get("types") or []
        older_than_days = options.get("older_than_days")
        limit = options.get("limit")
        confirmed = options.get("yes", False)

        qs = NotificationMessage.objects.filter(
            channel=NotificationMessage.CHANNEL_EMAIL_TRANSACTIONAL,
            status__in=[
                NotificationMessage.STATUS_PENDING,
                NotificationMessage.STATUS_QUEUED,
                NotificationMessage.STATUS_FAILED,
            ],
        ).order_by("created_at")

        if selected_types:
            qs = qs.filter(event_type__in=selected_types)

        if older_than_days is not None:
            if older_than_days < 0:
                raise CommandError("--older-than-days doit etre positif ou nul.")
            threshold = timezone.now() - timedelta(days=older_than_days)
            qs = qs.filter(created_at__lt=threshold)

        if limit is not None:
            if limit <= 0:
                raise CommandError("--limit doit etre > 0.")
            qs = qs[:limit]

        notifications = list(qs)
        total = len(notifications)

        self.stdout.write(self.style.NOTICE(f"Action: {action}"))
        self.stdout.write(self.style.NOTICE(f"Notifications ciblees: {total}"))

        grouped = (
            NotificationMessage.objects.filter(pk__in=[n.pk for n in notifications])
            .values("event_type")
            .annotate(total=Count("id"))
            .order_by("-total")
        )
        for row in grouped:
            self.stdout.write(f" - {row['event_type']}: {row['total']}")

        if action == "report":
            return

        if not confirmed:
            raise CommandError("Ajoutez --yes pour confirmer l'action destructive.")

        if action == "send":
            sent = 0
            failed = 0
            for notification in notifications:
                if send_notification_email(notification.pk):
                    sent += 1
                else:
                    failed += 1

            self.stdout.write(self.style.SUCCESS(f"Envoyes: {sent}"))
            self.stdout.write(self.style.WARNING(f"Echecs: {failed}"))
            return

        if action == "mark-sent":
            ids = [n.pk for n in notifications]
            updated = NotificationMessage.objects.filter(pk__in=ids).update(
                status=NotificationMessage.STATUS_SENT,
                sent_at=timezone.now(),
            )
            self.stdout.write(self.style.SUCCESS(f"Marquees status=sent: {updated}"))
            return

