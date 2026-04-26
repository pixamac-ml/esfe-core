import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0008_eccontent"),
    ]

    operations = [
        migrations.CreateModel(
            name="ECChapter",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("order", models.PositiveIntegerField(default=0)),
                ("ec", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chapters", to="academics.ec")),
            ],
            options={
                "verbose_name": "Chapitre EC",
                "verbose_name_plural": "Chapitres EC",
                "ordering": ["order", "id"],
            },
        ),
        migrations.AddField(
            model_name="eccontent",
            name="chapter",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="contents",
                to="academics.ecchapter",
            ),
        ),
        migrations.AddField(
            model_name="eccontent",
            name="order",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="eccontent",
            name="text_content",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="eccontent",
            name="video_url",
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="eccontent",
            name="content_type",
            field=models.CharField(
                choices=[
                    ("pdf", "PDF"),
                    ("video", "Vidéo"),
                    ("doc", "Word"),
                    ("excel", "Excel"),
                    ("text", "Texte"),
                ],
                max_length=20,
            ),
        ),
        migrations.AlterModelOptions(
            name="eccontent",
            options={
                "ordering": ["order", "id"],
                "verbose_name": "Contenu EC",
                "verbose_name_plural": "Contenus EC",
            },
        ),
        migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="eccontent",
            name="ec",
        ),
        migrations.AlterField(
            model_name="eccontent",
            name="chapter",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="contents", to="academics.ecchapter"),
        ),
    ]
