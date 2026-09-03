from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0030_cards_hardening_and_staff"),
        ("students", "0015_cards_hardening_and_staff"),
    ]

    operations = [
        migrations.AddField(
            model_name="verificationlog",
            name="staff_card",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="verifications",
                to="accounts.cartepersonnel",
            ),
        ),
    ]
