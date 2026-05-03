from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0015_weekly_schedule_slot"),
    ]

    operations = [
        migrations.CreateModel(
            name="Language",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("code", models.CharField(blank=True, max_length=20)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Langue",
                "verbose_name_plural": "Langues",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="Profession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150, unique=True)),
                ("description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Metier",
                "verbose_name_plural": "Metiers",
                "ordering": ["name"],
            },
        ),
    ]
