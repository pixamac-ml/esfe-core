from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("portal", "0005_branchitsettings"),
    ]

    operations = [
        migrations.AlterField(
            model_name="supportauditlog",
            name="action_type",
            field=models.CharField(
                choices=[
                    ("password_reset", "Reinitialisation mot de passe"),
                    ("account_activated", "Activation compte"),
                    ("account_deactivated", "Desactivation compte"),
                    ("diagnostic_viewed", "Diagnostic consulte"),
                    ("ticket_created", "Ticket cree"),
                    ("ticket_assigned", "Ticket assigne"),
                    ("ticket_status_changed", "Statut ticket modifie"),
                    ("ticket_commented", "Commentaire ticket"),
                    ("account_suspended", "Compte suspendu"),
                    ("account_reactivated", "Compte reactive"),
                    ("account_unblocked", "Compte debloque"),
                    ("email_updated", "Email corrige"),
                    ("grade_updated", "Note modifiee"),
                    ("grades_imported", "Import notes"),
                    ("branch_settings_updated", "Parametres annexe modifies"),
                ],
                db_index=True,
                max_length=30,
            ),
        ),
    ]
