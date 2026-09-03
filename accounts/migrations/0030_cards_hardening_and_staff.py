import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0029_assign_existing_django_superusers"),
    ]

    operations = [
        migrations.CreateModel(
            name="CartePersonnel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_reference", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("annee", models.CharField(max_length=9)),
                ("code_annexe", models.CharField(max_length=20)),
                ("date_emission", models.DateField(auto_now_add=True)),
                ("date_expiration", models.DateField()),
                ("statut", models.CharField(choices=[("active", "Active"), ("revoquee", "Révoquée"), ("perdue", "Perdue"), ("expiree", "Expirée")], db_index=True, default="active", max_length=10)),
                ("token_version", models.CharField(default="v2", max_length=4)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="cartes_personnel", to="accounts.profile")),
            ],
            options={
                "verbose_name": "Carte personnel",
                "verbose_name_plural": "Cartes personnel",
                "ordering": ["-date_emission", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="cartepersonnel",
            constraint=models.UniqueConstraint(fields=("profile", "annee"), name="unique_staff_card_per_academic_year"),
        ),
        migrations.AddIndex(
            model_name="cartepersonnel",
            index=models.Index(fields=["profile", "statut"], name="accounts_ca_profile_d47c3f_idx"),
        ),
        migrations.AddIndex(
            model_name="cartepersonnel",
            index=models.Index(fields=["statut", "date_expiration"], name="accounts_ca_statut_751e30_idx"),
        ),
    ]
