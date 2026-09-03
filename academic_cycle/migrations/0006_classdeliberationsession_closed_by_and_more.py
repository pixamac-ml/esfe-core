from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("academic_cycle", "0005_rename_classdeliberationsession_index"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="classdeliberationsession",
            name="closed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="classdeliberationsession",
            name="closed_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="closed_deliberation_sessions", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name="classdeliberationsession",
            name="status",
            field=models.CharField(choices=[("preparation", "Préparation"), ("in_session", "En séance"), ("ready", "Prête à clôturer"), ("closed", "Clôturée par le DE"), ("transmitted", "Transmise au DG"), ("official", "Officielle")], db_index=True, default="preparation", max_length=20),
        ),
    ]
