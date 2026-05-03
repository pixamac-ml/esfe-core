from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("branches", "0002_branch_image"),
        ("inscriptions", "0002_alter_inscription_status"),
        ("portal", "0002_rename_portal_supp_branch__9a31d8_idx_portal_supp_branch__f33938_idx_and_more"),
        ("students", "0004_remove_studentattendance_students_unique_attendance_student_date_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="supportauditlog",
            name="action_type",
            field=models.CharField(choices=[("password_reset", "Reinitialisation mot de passe"), ("account_activated", "Activation compte"), ("account_deactivated", "Desactivation compte"), ("diagnostic_viewed", "Diagnostic consulte"), ("ticket_created", "Ticket cree"), ("ticket_assigned", "Ticket assigne"), ("ticket_status_changed", "Statut ticket modifie"), ("ticket_commented", "Commentaire ticket")], db_index=True, max_length=30),
        ),
        migrations.CreateModel(
            name="SupportTicket",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=180)),
                ("description", models.TextField(blank=True)),
                ("category", models.CharField(choices=[("account", "Compte"), ("document", "Document"), ("grades", "Notes"), ("student", "Etudiant"), ("other", "Autre")], db_index=True, default="other", max_length=20)),
                ("priority", models.CharField(choices=[("low", "Basse"), ("normal", "Normale"), ("high", "Haute"), ("critical", "Critique")], db_index=True, default="normal", max_length=20)),
                ("status", models.CharField(choices=[("open", "Ouvert"), ("in_progress", "En cours"), ("resolved", "Resolu"), ("rejected", "Rejete")], db_index=True, default="open", max_length=20)),
                ("resolution", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("resolved_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("assigned_to", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_support_tickets", to=settings.AUTH_USER_MODEL)),
                ("branch", models.ForeignKey(blank=True, db_index=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="support_tickets", to="branches.branch")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_support_tickets", to=settings.AUTH_USER_MODEL)),
                ("inscription", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="support_tickets", to="inscriptions.inscription")),
                ("requester_user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="requested_support_tickets", to=settings.AUTH_USER_MODEL)),
                ("resolved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="resolved_support_tickets", to=settings.AUTH_USER_MODEL)),
                ("student", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="support_tickets", to="students.student")),
            ],
            options={
                "verbose_name": "Ticket support",
                "verbose_name_plural": "Tickets support",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="SupportTicketComment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("body", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("author", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="support_ticket_comments", to=settings.AUTH_USER_MODEL)),
                ("ticket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="comments", to="portal.supportticket")),
            ],
            options={
                "verbose_name": "Commentaire ticket support",
                "verbose_name_plural": "Commentaires tickets support",
                "ordering": ["created_at", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="supportticket",
            index=models.Index(fields=["branch", "status", "created_at"], name="portal_supp_branch__92514d_idx"),
        ),
        migrations.AddIndex(
            model_name="supportticket",
            index=models.Index(fields=["assigned_to", "status", "created_at"], name="portal_supp_assigne_86e31d_idx"),
        ),
        migrations.AddIndex(
            model_name="supportticket",
            index=models.Index(fields=["category", "status", "created_at"], name="portal_supp_categor_b01161_idx"),
        ),
    ]
