from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import portal.models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("branches", "0002_branch_image"),
        ("portal", "0008_directorteacherassignment"),
    ]

    operations = [
        migrations.CreateModel(
            name="TeacherDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("document_type", models.CharField(choices=[("id", "Piece d'identite"), ("diploma", "Diplome"), ("cv", "CV"), ("contract", "Contrat"), ("other", "Autre")], db_index=True, default="other", max_length=30)),
                ("file", models.FileField(upload_to=portal.models.teacher_document_upload_path)),
                ("note", models.CharField(blank=True, max_length=255)),
                ("is_verified", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("branch", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="teacher_documents", to="branches.branch")),
                ("teacher", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="teacher_documents", to=settings.AUTH_USER_MODEL)),
                ("uploaded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="uploaded_teacher_documents", to=settings.AUTH_USER_MODEL)),
                ("verified_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="verified_teacher_documents", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Document enseignant",
                "verbose_name_plural": "Documents enseignants",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="teacherdocument",
            index=models.Index(fields=["branch", "teacher"], name="portal_teac_branch__473720_idx"),
        ),
        migrations.AddIndex(
            model_name="teacherdocument",
            index=models.Index(fields=["branch", "document_type"], name="portal_teac_branch__accdf0_idx"),
        ),
    ]
