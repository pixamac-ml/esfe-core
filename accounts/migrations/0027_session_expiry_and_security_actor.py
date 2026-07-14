import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0026_account_session_security")]

    operations = [
        migrations.AddField(
            model_name="accountsessionrecord",
            name="absolute_expires_at",
            field=models.DateTimeField(db_index=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="accountsecurityevent",
            name="actor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="acted_security_events",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
