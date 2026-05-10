from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_alter_siteconfiguration_about_hero_image_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfiguration",
            name="about_hero_background_image",
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to="site/about/hero/background/",
                verbose_name="Image de fond Hero (A propos)",
            ),
        ),
    ]

