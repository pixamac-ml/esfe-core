import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("academics", "0029_evaluationcampaign_and_more"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(name="EvaluationProctor", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("kind", models.CharField(choices=[("internal", "Personnel interne"), ("external", "Surveillant externe")], default="internal", max_length=12)),
            ("full_name", models.CharField(blank=True, max_length=180)), ("phone", models.CharField(blank=True, max_length=50)), ("is_active", models.BooleanField(default=True)),
            ("branch", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="evaluation_proctors", to="branches.branch")),
            ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="evaluation_proctor_profiles", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="EvaluationProctorAssignment", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("role", models.CharField(default="Surveillant", max_length=80)),
            ("present", models.BooleanField(blank=True, null=True)), ("signed_at", models.DateTimeField(blank=True, null=True)), ("proof", models.FileField(blank=True, null=True, upload_to="academics/evaluation_proofs/")),
            ("validated_at", models.DateTimeField(blank=True, null=True)),
            ("event", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="proctor_assignments", to="academics.academicscheduleevent")),
            ("proctor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="assignments", to="academics.evaluationproctor")),
            ("validated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="validated_evaluation_proctor_assignments", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="EvaluationRequirement", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("subject_due_at", models.DateTimeField(blank=True, null=True)), ("critical_at", models.DateTimeField(blank=True, null=True)),
            ("subject_status", models.CharField(choices=[("expected", "Sujet attendu"), ("received", "Sujet reçu"), ("missing", "Sujet manquant")], db_index=True, default="expected", max_length=12)),
            ("subject_file", models.FileField(blank=True, null=True, upload_to="academics/evaluation_subjects/")), ("received_at", models.DateTimeField(blank=True, null=True)), ("last_reminded_at", models.DateTimeField(blank=True, null=True)), ("notes", models.TextField(blank=True)),
            ("academic_class", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="evaluation_requirements", to="academics.academicclass")), ("campaign", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="requirements", to="academics.evaluationcampaign")), ("ec", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="evaluation_requirements", to="academics.ec")),
            ("received_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="received_evaluation_subjects", to=settings.AUTH_USER_MODEL)), ("responsible_teacher", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="evaluation_requirements", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="EvaluationScriptBatch", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("expected_count", models.PositiveIntegerField(default=0)), ("received_count", models.PositiveIntegerField(default=0)),
            ("status", models.CharField(choices=[("available", "Copies disponibles"), ("collected", "Copies retirées"), ("correction", "Correction en cours"), ("returned", "Notes retournées")], db_index=True, default="available", max_length=14)),
            ("collected_at", models.DateTimeField(blank=True, null=True)), ("returned_at", models.DateTimeField(blank=True, null=True)), ("proof", models.FileField(blank=True, null=True, upload_to="academics/evaluation_scripts/")), ("notes", models.TextField(blank=True)),
            ("collected_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="collected_evaluation_scripts", to=settings.AUTH_USER_MODEL)), ("event", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="script_batch", to="academics.academicscheduleevent")),
        ]),
        migrations.AddIndex(model_name="evaluationproctor", index=models.Index(fields=["branch", "kind", "is_active"], name="academics_e_branch__938f1d_idx")),
        migrations.AddConstraint(model_name="evaluationproctorassignment", constraint=models.UniqueConstraint(fields=("event", "proctor"), name="academics_unique_evaluation_proctor_assignment")),
        migrations.AddIndex(model_name="evaluationrequirement", index=models.Index(fields=["campaign", "subject_status"], name="academics_e_campaig_6b0b11_idx")),
        migrations.AddIndex(model_name="evaluationrequirement", index=models.Index(fields=["critical_at", "subject_status"], name="academics_e_critica_188144_idx")),
        migrations.AddConstraint(model_name="evaluationrequirement", constraint=models.UniqueConstraint(fields=("campaign", "academic_class", "ec"), name="academics_unique_evaluation_requirement")),
        migrations.AddIndex(model_name="evaluationscriptbatch", index=models.Index(fields=["status", "returned_at"], name="academics_e_status_07e39b_idx")),
    ]
