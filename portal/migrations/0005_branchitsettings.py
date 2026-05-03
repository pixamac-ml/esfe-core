from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("branches", "0002_branch_image"),
        ("portal", "0004_accountsupportstate_and_account_actions"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="BranchITSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("validation_threshold", models.DecimalField(decimal_places=2, default=10, max_digits=4)),
                ("active_academic_year", models.CharField(blank=True, max_length=20)),
                ("local_config", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("branch", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="it_settings", to="branches.branch")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_branch_it_settings", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Parametres informaticien annexe",
                "verbose_name_plural": "Parametres informaticien annexes",
            },
        ),
    ]
