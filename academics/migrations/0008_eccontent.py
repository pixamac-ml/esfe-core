import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0007_backfill_semester_status"),
    ]

    operations = [
        migrations.CreateModel(
            name="ECContent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("file", models.FileField(blank=True, null=True, upload_to="courses/")),
                ("content_type", models.CharField(choices=[("pdf", "PDF"), ("text", "Text")], max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("ec", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="contents", to="academics.ec")),
            ],
            options={
                "verbose_name": "Contenu EC",
                "verbose_name_plural": "Contenus EC",
                "ordering": ["-created_at", "id"],
            },
        ),
    ]
