from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notifier", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="notificationmessage",
            name="archived_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddIndex(
            model_name="notificationmessage",
            index=models.Index(
                fields=["recipient", "channel", "archived_at", "created_at"],
                name="notifier_rec_chan_arch_idx",
            ),
        ),
    ]
