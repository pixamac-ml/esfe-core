import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("branches", "0003_branch_cash_reserve_target"),
        ("core", "0010_migrate_and_delete_legacy_notification"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SignatureRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("purpose", models.CharField(choices=[("lesson_log", "Cahier de texte"), ("payment", "Paiement"), ("document", "Document")], db_index=True, max_length=40)),
                ("object_id", models.PositiveBigIntegerField(db_index=True)),
                ("title", models.CharField(max_length=255)),
                ("snapshot", models.JSONField(blank=True, default=dict)),
                ("document_digest", models.CharField(db_index=True, max_length=64)),
                ("token_hash", models.CharField(editable=False, max_length=64, unique=True)),
                ("status", models.CharField(choices=[("awaiting_signature", "En attente de signature"), ("signed", "Signée"), ("approved", "Approuvée"), ("returned", "Retournée"), ("expired", "Expirée"), ("cancelled", "Annulée")], db_index=True, default="awaiting_signature", max_length=30)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("signature_data", models.TextField(blank=True)),
                ("signature_sha256", models.CharField(blank=True, max_length=64)),
                ("signed_at", models.DateTimeField(blank=True, null=True)),
                ("signed_ip", models.GenericIPAddressField(blank=True, null=True)),
                ("signed_user_agent", models.CharField(blank=True, max_length=300)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("return_reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="approved_signature_requests", to=settings.AUTH_USER_MODEL)),
                ("branch", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="signature_requests", to="branches.branch")),
                ("content_type", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="contenttypes.contenttype")),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="requested_signature_requests", to=settings.AUTH_USER_MODEL)),
                ("signer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="signature_requests_to_sign", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(model_name="signaturerequest", index=models.Index(fields=["branch", "purpose", "status"], name="core_signat_branch__9e02ac_idx")),
        migrations.AddIndex(model_name="signaturerequest", index=models.Index(fields=["content_type", "object_id", "status"], name="core_signat_content_3fcc56_idx")),
        migrations.AddIndex(model_name="signaturerequest", index=models.Index(fields=["signer", "status", "expires_at"], name="core_signat_signer__31b641_idx")),
    ]
