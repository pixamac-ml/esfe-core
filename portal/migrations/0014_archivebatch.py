from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0017_academic_archive_flags"),
        ("branches", "0002_branch_image"),
        ("portal", "0013_teacherdashboardpreference"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ArchiveBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("archive_type", models.CharField(choices=[("class", "Classe"), ("year", "Annee academique")], db_index=True, max_length=20)),
                ("status", models.CharField(choices=[("archived", "Archivee"), ("restored", "Restauree")], db_index=True, default="archived", max_length=20)),
                ("reason", models.TextField()),
                ("snapshot", models.JSONField(blank=True, default=dict)),
                ("classes_count", models.PositiveIntegerField(default=0)),
                ("enrollments_count", models.PositiveIntegerField(default=0)),
                ("inscriptions_count", models.PositiveIntegerField(default=0)),
                ("students_count", models.PositiveIntegerField(default=0)),
                ("grades_count", models.PositiveIntegerField(default=0)),
                ("payments_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("restored_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("academic_class", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="archive_batches", to="academics.academicclass")),
                ("academic_year", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="archive_batches", to="academics.academicyear")),
                ("branch", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="archive_batches", to="branches.branch")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_archive_batches", to=settings.AUTH_USER_MODEL)),
                ("restored_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="restored_archive_batches", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Lot d'archivage",
                "verbose_name_plural": "Lots d'archivage",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="archivebatch",
            index=models.Index(fields=["branch", "status", "created_at"], name="portal_arch_branch__a07eb8_idx"),
        ),
        migrations.AddIndex(
            model_name="archivebatch",
            index=models.Index(fields=["academic_year", "status"], name="portal_arch_academi_0f41bc_idx"),
        ),
        migrations.AddIndex(
            model_name="archivebatch",
            index=models.Index(fields=["archive_type", "status"], name="portal_arch_archive_735844_idx"),
        ),
    ]
