from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("branches", "0002_branch_image"),
    ]

    operations = [
        migrations.CreateModel(
            name="SupportAuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action_type", models.CharField(choices=[("password_reset", "Reinitialisation mot de passe"), ("account_activated", "Activation compte"), ("account_deactivated", "Desactivation compte"), ("diagnostic_viewed", "Diagnostic consulte")], db_index=True, max_length=30)),
                ("target_label", models.CharField(blank=True, max_length=255)),
                ("details", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="performed_support_audit_logs", to=settings.AUTH_USER_MODEL)),
                ("branch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="support_audit_logs", to="branches.branch")),
                ("target_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="targeted_support_audit_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Journal support",
                "verbose_name_plural": "Journal support",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="supportauditlog",
            index=models.Index(fields=["branch", "created_at"], name="portal_supp_branch__9a31d8_idx"),
        ),
        migrations.AddIndex(
            model_name="supportauditlog",
            index=models.Index(fields=["actor", "created_at"], name="portal_supp_actor_i_0d4c2c_idx"),
        ),
        migrations.AddIndex(
            model_name="supportauditlog",
            index=models.Index(fields=["action_type", "created_at"], name="portal_supp_action__bf983d_idx"),
        ),
    ]
