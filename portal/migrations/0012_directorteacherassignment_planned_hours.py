from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0011_directorteacherassignment_room_label"),
    ]

    operations = [
        migrations.AddField(
            model_name="directorteacherassignment",
            name="planned_hours",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=6, null=True),
        ),
    ]
