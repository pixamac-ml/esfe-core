from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0025_ec_archived_at_ec_structure_status_ue_archived_at_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="academiccalendarentry",
            name="supervisors",
            field=models.ManyToManyField(
                blank=True,
                related_name="supervised_exam_sessions",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Surveillants assignes",
            ),
        ),
    ]
