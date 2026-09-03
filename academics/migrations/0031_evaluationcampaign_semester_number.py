from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("academics", "0030_evaluationproctor_evaluationproctorassignment_and_more")]

    operations = [
        migrations.AddField(
            model_name="evaluationcampaign",
            name="semester_number",
            field=models.PositiveSmallIntegerField(blank=True, choices=[(1, "Semestre 1"), (2, "Semestre 2")], null=True),
        ),
    ]
