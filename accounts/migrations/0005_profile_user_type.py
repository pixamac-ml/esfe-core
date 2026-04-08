from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_profile_branch_profile_role_alter_profile_avatar_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="user_type",
            field=models.CharField(
                blank=True,
                choices=[("public", "Public"), ("staff", "Staff")],
                db_index=True,
                help_text="Type utilisateur normalisé pour le portail",
                max_length=20,
            ),
        ),
    ]

