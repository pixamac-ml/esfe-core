import uuid

from django.db import migrations, models


def populate_student_card_references(apps, schema_editor):
    CarteEtudiant = apps.get_model("students", "CarteEtudiant")
    for card in CarteEtudiant.objects.filter(public_reference__isnull=True).iterator():
        card.public_reference = uuid.uuid4()
        card.save(update_fields=["public_reference"])


class Migration(migrations.Migration):
    dependencies = [
        ("students", "0014_supervisor_operational_observations"),
    ]

    operations = [
        migrations.AddField(
            model_name="carteetudiant",
            name="public_reference",
            field=models.UUIDField(blank=True, editable=False, null=True),
        ),
        migrations.RunPython(populate_student_card_references, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="carteetudiant",
            name="public_reference",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AddConstraint(
            model_name="carteetudiant",
            constraint=models.UniqueConstraint(
                fields=("etudiant", "annee"),
                name="unique_student_card_per_academic_year",
            ),
        ),
    ]
