from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("academics", "0033_allow_parallel_class_groups")]

    operations = [
        migrations.AddField(
            model_name="lessonlog",
            name="review_comment",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="lessonlog",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="lessonlog",
            name="reviewed_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_lesson_logs", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name="lessonlog",
            name="status",
            field=models.CharField(choices=[("planned", "Planifie"), ("submitted", "Soumis au controle"), ("returned", "Retourne pour correction"), ("done", "Cours fait - approuve"), ("cancelled", "Annule"), ("absent_teacher", "Enseignant absent")], db_index=True, default="planned", max_length=20),
        ),
    ]
