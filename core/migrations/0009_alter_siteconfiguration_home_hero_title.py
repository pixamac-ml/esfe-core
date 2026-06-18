from django.db import migrations, models

OFFICIAL_NAME = "École de Santé Félix Houphouët-Boigny Mali"


def set_official_name(apps, schema_editor):
    SiteConfiguration = apps.get_model("core", "SiteConfiguration")
    SiteConfiguration.objects.update(home_hero_title=OFFICIAL_NAME)


def restore_previous_default(apps, schema_editor):
    SiteConfiguration = apps.get_model("core", "SiteConfiguration")
    SiteConfiguration.objects.filter(home_hero_title=OFFICIAL_NAME).update(home_hero_title="ESFE")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_siteconfiguration_about_hero_background_image"),
    ]

    operations = [
        migrations.AlterField(
            model_name="siteconfiguration",
            name="home_hero_title",
            field=models.CharField(
                default=OFFICIAL_NAME,
                max_length=255,
                verbose_name="Titre Hero Accueil",
            ),
        ),
        migrations.RunPython(set_official_name, restore_previous_default),
    ]
