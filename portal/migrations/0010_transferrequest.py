from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import portal.models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0016_language_profession"),
        ("branches", "0002_branch_image"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("portal", "0009_teacherdocument"),
    ]

    operations = [
        migrations.CreateModel(
            name="TransferRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("transfer_type", models.CharField(choices=[("class", "Transfert de classe"), ("school", "Transfert d'ecole")], db_index=True, default="class", max_length=20)),
                ("target_school_name", models.CharField(blank=True, max_length=180)),
                ("reason", models.TextField(blank=True)),
                ("attachment", models.FileField(blank=True, null=True, upload_to=portal.models.transfer_attachment_upload_path)),
                ("status", models.CharField(choices=[("draft", "Brouillon"), ("submitted", "Soumis"), ("validated", "Valide"), ("rejected", "Rejete")], db_index=True, default="submitted", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("branch", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transfer_requests", to="branches.branch")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_transfer_requests", to=settings.AUTH_USER_MODEL)),
                ("enrollment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="transfer_requests", to="academics.academicenrollment")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_transfer_requests", to=settings.AUTH_USER_MODEL)),
                ("source_class", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="outgoing_transfer_requests", to="academics.academicclass")),
                ("target_class", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="incoming_transfer_requests", to="academics.academicclass")),
            ],
            options={
                "verbose_name": "Demande de transfert",
                "verbose_name_plural": "Demandes de transfert",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="transferrequest",
            index=models.Index(fields=["branch", "status"], name="portal_tran_branch__557a0b_idx"),
        ),
        migrations.AddIndex(
            model_name="transferrequest",
            index=models.Index(fields=["branch", "transfer_type"], name="portal_tran_branch__d1e213_idx"),
        ),
    ]
