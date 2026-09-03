from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("academic_cycle", "0004_classdeliberationsession_and_jury_fields")]

    operations = [
        migrations.RenameIndex(
            model_name="classdeliberationsession",
            old_name="academic_c_branch__c89d88_idx",
            new_name="academic_cy_branch__a7b5d4_idx",
        ),
    ]
