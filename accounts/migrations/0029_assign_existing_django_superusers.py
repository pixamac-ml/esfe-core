from django.conf import settings
from django.db import migrations


def assign_existing_superusers(apps, schema_editor):
    user_app_label, user_model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(user_app_label, user_model_name)
    Profile = apps.get_model("accounts", "Profile")
    InstitutionalProfile = apps.get_model("accounts", "InstitutionalProfile")
    Group = apps.get_model("auth", "Group")

    group, _created = Group.objects.get_or_create(name="super_admin")
    for user in User.objects.filter(is_superuser=True):
        profile, _created = Profile.objects.get_or_create(user_id=user.pk)
        if profile.position:
            continue
        profile.position = "super_admin"
        profile.role = "superadmin"
        profile.save(update_fields=["position", "role"])
        InstitutionalProfile.objects.update_or_create(
            user_id=user.pk,
            defaults={"position": "super_admin", "branch_id": None},
        )
        user.groups.add(group)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0028_normalize_institutional_position_groups"),
    ]

    operations = [
        migrations.RunPython(assign_existing_superusers, migrations.RunPython.noop),
    ]
