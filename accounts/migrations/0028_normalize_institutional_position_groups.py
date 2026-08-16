from django.db import migrations


CANONICAL_GROUPS = {
    "student",
    "teacher",
    "annex_manager",
    "finance_manager",
    "payment_agent",
    "secretary",
    "admissions",
    "academic_supervisor",
    "it_support",
    "director_of_studies",
    "marketing_manager",
    "executive_director",
    "deputy_executive_director",
    "super_admin",
}

LEGACY_ACCESS_GROUPS = {
    "admissions_managers",
    "finance_agents",
    "finance",
    "gestionnaire",
    "manager",
    "executive",
    "secretaries",
    "marketing",
    "branch_manager",
    "deputy_director",
}

POSITION_TO_GROUP = {
    "student": "student",
    "teacher": "teacher",
    "finance_manager": "finance_manager",
    "payment_agent": "payment_agent",
    "secretary": "secretary",
    "admissions": "admissions",
    "director_of_studies": "director_of_studies",
    "executive_director": "executive_director",
    "deputy_executive_director": "deputy_executive_director",
    "annex_manager": "annex_manager",
    "academic_supervisor": "academic_supervisor",
    "it_support": "it_support",
    "marketing_manager": "marketing_manager",
    "super_admin": "super_admin",
}

COMPATIBILITY_ROLE = {
    "student": "student",
    "teacher": "teacher",
    "finance_manager": "finance",
    "payment_agent": "finance",
    "admissions": "admissions",
    "director_of_studies": "executive",
    "executive_director": "executive",
    "deputy_executive_director": "executive",
    "super_admin": "superadmin",
}

# Les permissions présentes sur les anciens groupes sont recopiées dans le
# groupe canonique avant la normalisation des membres.
PERMISSION_SOURCES = {
    "admissions": {"admissions", "admissions_managers", "Admissions"},
    "finance_manager": {"finance", "finance_agents", "Finance", "Agent Paiement"},
    "payment_agent": {"finance", "finance_agents", "Finance", "Agent Paiement"},
    "annex_manager": {"gestionnaire", "manager", "Gestionnaire", "branch_manager"},
    "secretary": {"secretary", "secretaries", "Secretaire Academique"},
    "academic_supervisor": {"Surveillant Academique"},
    "it_support": {"Informaticien"},
    "teacher": {"Enseignant"},
    "student": {"Etudiant"},
    "director_of_studies": {"Direction"},
    "executive_director": {"executive", "Direction"},
    "deputy_executive_director": {"deputy_director", "executive", "Direction"},
    "marketing_manager": {"marketing"},
    "super_admin": {"Superadmin"},
}


def normalize_access_assignments(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Profile = apps.get_model("accounts", "Profile")
    InstitutionalProfile = apps.get_model("accounts", "InstitutionalProfile")

    groups = {}
    for name in CANONICAL_GROUPS:
        groups[name], _created = Group.objects.get_or_create(name=name)

    for target_name, source_names in PERMISSION_SOURCES.items():
        target = groups[target_name]
        source_permissions = Group.objects.filter(
            name__in=source_names,
            permissions__isnull=False,
        ).values_list("permissions", flat=True)
        target.permissions.add(*source_permissions)

    controlled_groups = list(CANONICAL_GROUPS | LEGACY_ACCESS_GROUPS)
    for profile in Profile.objects.select_related("user").all():
        raw_position = (profile.position or "").strip().lower()
        position = "annex_manager" if raw_position == "branch_manager" else raw_position
        expected_group_name = POSITION_TO_GROUP.get(position)

        # A staff user without an institutional position must not retain a
        # legacy authorisation through role/group alone. The account remains
        # active and is reported for explicit reassignment by an administrator.
        profile.user.groups.remove(*Group.objects.filter(name__in=controlled_groups))

        if not expected_group_name:
            if profile.role:
                profile.role = ""
                profile.save(update_fields=["role"])
            InstitutionalProfile.objects.filter(user_id=profile.user_id).delete()
            continue

        changed_fields = []
        expected_role = COMPATIBILITY_ROLE.get(position, "")
        if profile.position != position:
            profile.position = position
            changed_fields.append("position")
        if profile.role != expected_role:
            profile.role = expected_role
            changed_fields.append("role")
        if changed_fields:
            profile.save(update_fields=changed_fields)

        profile.user.groups.add(groups[expected_group_name])
        InstitutionalProfile.objects.filter(user_id=profile.user_id).update(position=position)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0027_session_expiry_and_security_actor"),
    ]

    operations = [
        migrations.RunPython(normalize_access_assignments, migrations.RunPython.noop),
    ]
