from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0031_evaluationcampaign_semester_number"),
    ]

    operations = [
        migrations.AlterField(
            model_name="evaluationcampaign",
            name="semester_number",
            field=models.PositiveSmallIntegerField(blank=True, null=True),
        ),
    ]
