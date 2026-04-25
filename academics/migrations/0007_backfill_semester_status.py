from django.db import migrations


def set_existing_semesters_to_normal_entry(apps, schema_editor):
    Semester = apps.get_model("academics", "Semester")
    Semester.objects.filter(status="DRAFT").update(status="NORMAL_ENTRY")


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0006_semester_status"),
    ]

    operations = [
        migrations.RunPython(
            set_existing_semesters_to_normal_entry,
            migrations.RunPython.noop,
        ),
    ]
