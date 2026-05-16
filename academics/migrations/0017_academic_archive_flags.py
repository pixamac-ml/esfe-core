from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0016_language_profession"),
    ]

    operations = [
        migrations.AddField(
            model_name="academicclass",
            name="archived_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="academicclass",
            name="is_archived",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="academicenrollment",
            name="archived_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="academicenrollment",
            name="is_archived",
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
