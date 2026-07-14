from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("academics", "0023_academiccalendar_academiccalendarentry_and_more")]

    operations = [
        migrations.AlterField(
            model_name="academiccalendar",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Brouillon"),
                    ("validated", "Valide"),
                    ("published", "Publie"),
                    ("archived", "Archive"),
                ],
                db_index=True,
                default="draft",
                max_length=20,
            ),
        ),
    ]
