from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("portal", "0003_supportticket_supportticketcomment"),
    ]

    operations = [
        migrations.AlterField(
            model_name="supportauditlog",
            name="action_type",
            field=models.CharField(choices=[("password_reset", "Reinitialisation mot de passe"), ("account_activated", "Activation compte"), ("account_deactivated", "Desactivation compte"), ("diagnostic_viewed", "Diagnostic consulte"), ("ticket_created", "Ticket cree"), ("ticket_assigned", "Ticket assigne"), ("ticket_status_changed", "Statut ticket modifie"), ("ticket_commented", "Commentaire ticket"), ("account_suspended", "Compte suspendu"), ("account_reactivated", "Compte reactive"), ("account_unblocked", "Compte debloque"), ("email_updated", "Email corrige")], db_index=True, max_length=30),
        ),
        migrations.CreateModel(
            name="AccountSupportState",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_suspended", models.BooleanField(db_index=True, default=False)),
                ("is_blocked", models.BooleanField(db_index=True, default=False)),
                ("must_change_password", models.BooleanField(db_index=True, default=False)),
                ("failed_login_count", models.PositiveSmallIntegerField(default=0)),
                ("blocked_until", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("note", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_account_support_states", to=settings.AUTH_USER_MODEL)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="support_state", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Etat support compte",
                "verbose_name_plural": "Etats support comptes",
            },
        ),
        migrations.AddIndex(
            model_name="accountsupportstate",
            index=models.Index(fields=["is_suspended", "is_blocked"], name="portal_acco_is_susp_9f2b2f_idx"),
        ),
        migrations.AddIndex(
            model_name="accountsupportstate",
            index=models.Index(fields=["must_change_password"], name="portal_acco_must_ch_bd9143_idx"),
        ),
    ]
