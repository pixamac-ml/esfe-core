from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_profile_accounts_pr_user_ty_77c9a6_idx"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="position",
            field=models.CharField(
                blank=True,
                choices=[
                    ("student", "Etudiant"),
                    ("teacher", "Enseignant"),
                    ("finance_manager", "Responsable finance"),
                    ("payment_agent", "Agent de paiement"),
                    ("secretary", "Secretaire"),
                    ("admissions", "Admissions"),
                    ("director_of_studies", "Directeur des etudes"),
                    ("executive_director", "Direction executive"),
                    ("branch_manager", "Gestionnaire annexe"),
                    ("academic_supervisor", "Surveillant academique"),
                    ("super_admin", "Super administrateur"),
                ],
                db_index=True,
                help_text="Fonction metier principale pour le routage dashboard.",
                max_length=40,
            ),
        ),
        migrations.AddIndex(
            model_name="profile",
            index=models.Index(fields=["position"], name="accounts_pr_position_250d35_idx"),
        ),
    ]
