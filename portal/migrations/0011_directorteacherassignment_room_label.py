from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0010_transferrequest"),
    ]

    operations = [
        migrations.AddField(
            model_name="directorteacherassignment",
            name="room_label",
            field=models.CharField(blank=True, max_length=120),
        ),
    ]
