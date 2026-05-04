from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0016_language_profession"),
        ("branches", "0002_branch_image"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("portal", "0007_it_dashboard_audit_actions"),
    ]

    operations = [
        migrations.CreateModel(
            name="DirectorTeacherAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("academic_class", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="director_teacher_assignments", to="academics.academicclass")),
                ("branch", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="director_teacher_assignments", to="branches.branch")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_director_teacher_assignments", to=settings.AUTH_USER_MODEL)),
                ("ec", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="director_teacher_assignments", to="academics.ec")),
                ("teacher", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="director_teacher_assignments", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Affectation enseignant direction",
                "verbose_name_plural": "Affectations enseignants direction",
                "ordering": ["teacher__last_name", "teacher__first_name", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="directorteacherassignment",
            index=models.Index(fields=["branch", "teacher"], name="portal_dire_branch__a99098_idx"),
        ),
        migrations.AddIndex(
            model_name="directorteacherassignment",
            index=models.Index(fields=["branch", "academic_class"], name="portal_dire_branch__9460f6_idx"),
        ),
        migrations.AddIndex(
            model_name="directorteacherassignment",
            index=models.Index(fields=["branch", "ec"], name="portal_dire_branch__c0c912_idx"),
        ),
        migrations.AddConstraint(
            model_name="directorteacherassignment",
            constraint=models.UniqueConstraint(fields=("teacher", "academic_class", "ec"), name="portal_unique_director_teacher_assignment"),
        ),
    ]
