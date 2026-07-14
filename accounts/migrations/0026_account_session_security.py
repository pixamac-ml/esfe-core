import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0025_split_public_and_institutional_profiles"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountSessionRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("identifier", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("position", models.CharField(blank=True, db_index=True, max_length=40)),
                ("started_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("last_activity_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("ended_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("end_reason", models.CharField(blank=True, choices=[("IDLE_TIMEOUT", "Expiration pour inactivite"), ("ABSOLUTE_TIMEOUT", "Expiration absolue"), ("VOLUNTARY_LOGOUT", "Deconnexion volontaire"), ("ADMIN_REVOKED", "Revocation administrative"), ("PASSWORD_CHANGED", "Changement de mot de passe"), ("ACCOUNT_RESTRICTED", "Compte restreint")], db_index=True, max_length=32)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=300)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="system_session_records", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-started_at"]},
        ),
        migrations.CreateModel(
            name="AccountSecurityEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("session_identifier", models.UUIDField(blank=True, db_index=True, null=True)),
                ("event_type", models.CharField(choices=[("LOGIN_SUCCESS", "Connexion reussie"), ("LOGOUT_VOLUNTARY", "Deconnexion volontaire"), ("IDLE_TIMEOUT", "Expiration pour inactivite"), ("ABSOLUTE_TIMEOUT", "Expiration absolue"), ("ADMIN_REVOKED", "Revocation administrative"), ("PASSWORD_CHANGED", "Changement de mot de passe"), ("ACCOUNT_SUSPENDED", "Suspension"), ("ACCOUNT_BLOCKED", "Blocage"), ("ACCOUNT_DEACTIVATED", "Desactivation"), ("POSITION_CHANGED", "Changement de position"), ("BRANCH_CHANGED", "Changement d'annexe")], db_index=True, max_length=32)),
                ("reason", models.CharField(blank=True, max_length=80)),
                ("authentication_method", models.CharField(blank=True, max_length=32)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=300)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="security_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.AddIndex(model_name="accountsessionrecord", index=models.Index(fields=["user", "ended_at"], name="accounts_ac_user_id_8026b0_idx")),
        migrations.AddIndex(model_name="accountsessionrecord", index=models.Index(fields=["identifier", "ended_at"], name="accounts_ac_identif_8917b1_idx")),
        migrations.AddIndex(model_name="accountsecurityevent", index=models.Index(fields=["user", "created_at"], name="accounts_ac_user_id_d09911_idx")),
        migrations.AddIndex(model_name="accountsecurityevent", index=models.Index(fields=["event_type", "created_at"], name="accounts_ac_event_t_9d5f32_idx")),
    ]
