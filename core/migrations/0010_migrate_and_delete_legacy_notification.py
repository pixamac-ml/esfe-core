from django.db import migrations


def migrate_legacy_notifications(apps, schema_editor):
    LegacyNotification = apps.get_model("core", "Notification")
    NotificationEvent = apps.get_model("notifier", "NotificationEvent")
    NotificationMessage = apps.get_model("notifier", "NotificationMessage")

    for legacy in LegacyNotification.objects.all().iterator():
        legacy_object_id = str(legacy.pk)
        if NotificationMessage.objects.filter(
            legacy_source="core.Notification",
            legacy_object_id=legacy_object_id,
        ).exists():
            continue

        metadata = {
            "recipient_email": legacy.recipient_email,
            "recipient_name": legacy.recipient_name,
            "related_candidature_id": legacy.related_candidature_id,
            "related_inscription_id": legacy.related_inscription_id,
            "related_payment_id": legacy.related_payment_id,
        }
        event = NotificationEvent.objects.create(
            event_type=legacy.notification_type,
            source_app="core_legacy",
            payload=metadata,
            metadata={"legacy_model": "core.Notification", "legacy_id": legacy.pk},
            status="processed" if legacy.email_sent else "pending",
            processed_at=legacy.sent_at,
        )
        message = NotificationMessage.objects.create(
            event=event,
            title=legacy.title,
            body=legacy.message,
            notification_type=legacy.notification_type,
            event_type=legacy.notification_type,
            channel="email_transactional",
            status="sent" if legacy.email_sent else "pending",
            metadata=metadata,
            legacy_source="core.Notification",
            legacy_object_id=legacy_object_id,
            sent_at=legacy.sent_at,
        )
        NotificationEvent.objects.filter(pk=event.pk).update(created_at=legacy.created_at)
        NotificationMessage.objects.filter(pk=message.pk).update(created_at=legacy.created_at)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0009_alter_siteconfiguration_home_hero_title"),
        ("notifier", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(migrate_legacy_notifications, migrations.RunPython.noop),
        migrations.DeleteModel(name="Notification"),
    ]
