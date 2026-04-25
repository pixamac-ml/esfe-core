from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0004_alter_ecgrade_note"),
    ]

    operations = [
        migrations.AddField(
            model_name="ecgrade",
            name="final_score",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AddField(
            model_name="ecgrade",
            name="normal_score",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
        migrations.AddField(
            model_name="ecgrade",
            name="retake_score",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
    ]
