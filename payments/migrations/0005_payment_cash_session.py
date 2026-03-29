from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0004_alter_cashpaymentsession_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="cash_session",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="payments",
                to="payments.cashpaymentsession",
            ),
        ),
    ]

