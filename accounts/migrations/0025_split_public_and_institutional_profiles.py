from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def copy_profiles_forward(apps, schema_editor):
    Profile = apps.get_model("accounts", "Profile")
    PublicProfile = apps.get_model("accounts", "PublicCommunityProfile")
    InstitutionalProfile = apps.get_model("accounts", "InstitutionalProfile")

    public_rows = []
    institutional_rows = []
    for profile in Profile.objects.all().iterator():
        public_rows.append(PublicProfile(
            user_id=profile.user_id,
            bio=profile.bio,
            location=profile.location,
            website=profile.website,
            main_domain=profile.main_domain,
            reputation=profile.reputation,
            total_topics=profile.total_topics,
            total_answers=profile.total_answers,
            total_accepted_answers=profile.total_accepted_answers,
            total_upvotes_received=profile.total_upvotes_received,
            total_views_generated=profile.total_views_generated,
            badge_gold=profile.badge_gold,
            badge_silver=profile.badge_silver,
            badge_bronze=profile.badge_bronze,
            is_public=profile.is_public,
        ))
        if profile.position:
            institutional_rows.append(InstitutionalProfile(
                user_id=profile.user_id,
                position=profile.position,
                branch_id=profile.branch_id,
                employee_code=profile.employee_code,
                salary_base=profile.salary_base,
                teacher_hourly_rate=profile.teacher_hourly_rate,
                employment_status=profile.employment_status,
                hire_date=profile.hire_date,
            ))

    PublicProfile.objects.bulk_create(public_rows, ignore_conflicts=True)
    InstitutionalProfile.objects.bulk_create(institutional_rows, ignore_conflicts=True)


def remove_split_profiles(apps, schema_editor):
    apps.get_model("accounts", "InstitutionalProfile").objects.all().delete()
    apps.get_model("accounts", "PublicCommunityProfile").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0024_alter_profile_position")]

    operations = [
        migrations.CreateModel(
            name="PublicCommunityProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("bio", models.TextField(blank=True)),
                ("location", models.CharField(blank=True, db_index=True, max_length=120)),
                ("website", models.URLField(blank=True)),
                ("main_domain", models.CharField(blank=True, db_index=True, max_length=120)),
                ("reputation", models.IntegerField(db_index=True, default=0)),
                ("total_topics", models.PositiveIntegerField(default=0)),
                ("total_answers", models.PositiveIntegerField(default=0)),
                ("total_accepted_answers", models.PositiveIntegerField(default=0)),
                ("total_upvotes_received", models.PositiveIntegerField(default=0)),
                ("total_views_generated", models.PositiveIntegerField(default=0)),
                ("badge_gold", models.PositiveIntegerField(default=0)),
                ("badge_silver", models.PositiveIntegerField(default=0)),
                ("badge_bronze", models.PositiveIntegerField(default=0)),
                ("is_public", models.BooleanField(db_index=True, default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="public_community_profile", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="InstitutionalProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.CharField(choices=[("student", "Etudiant"), ("teacher", "Enseignant"), ("finance_manager", "Responsable finance"), ("payment_agent", "Agent de paiement"), ("secretary", "Secretaire"), ("admissions", "Admissions"), ("director_of_studies", "Directeur des etudes"), ("executive_director", "Direction executive"), ("deputy_executive_director", "Direction generale adjointe"), ("branch_manager", "Gestionnaire annexe"), ("annex_manager", "Gestionnaire d'annexe"), ("academic_supervisor", "Surveillant academique"), ("it_support", "Informaticien"), ("marketing_manager", "Responsable marketing digital"), ("super_admin", "Super administrateur")], db_index=True, max_length=40)),
                ("employee_code", models.CharField(blank=True, db_index=True, max_length=30)),
                ("salary_base", models.PositiveBigIntegerField(default=0)),
                ("teacher_hourly_rate", models.PositiveBigIntegerField(default=0)),
                ("employment_status", models.CharField(choices=[("active", "Actif"), ("on_leave", "En conge"), ("suspended", "Suspendu"), ("inactive", "Inactif")], db_index=True, default="active", max_length=20)),
                ("hire_date", models.DateField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("branch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="institutional_profiles", to="branches.branch")),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="institutional_profile", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.RunPython(copy_profiles_forward, remove_split_profiles),
    ]
