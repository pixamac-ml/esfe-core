from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0005_ecgrade_sessions"),
    ]

    operations = [
        migrations.AddField(
            model_name="semester",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Brouillon"),
                    ("NORMAL_ENTRY", "Saisie normale"),
                    ("NORMAL_LOCKED", "Session normale terminee"),
                    ("RETAKE_ENTRY", "Rattrapage"),
                    ("FINALIZED", "Finalise"),
                    ("PUBLISHED", "Publie"),
                ],
                default="DRAFT",
                max_length=20,
            ),
        ),
    ]
