from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import communication.models.messaging


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CommunicationEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(max_length=120)),
                ("source_app", models.CharField(default="core", max_length=80)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("processed", "Processed"), ("partial", "Partial"), ("failed", "Failed")], default="pending", max_length=20)),
                ("processed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="communication_events_emitted", to=settings.AUTH_USER_MODEL)),
                ("recipient", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="communication_events_received", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Conversation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("subject", models.CharField(blank=True, max_length=255)),
                ("conversation_type", models.CharField(choices=[("direct", "Direct"), ("group", "Group"), ("support", "Support"), ("system", "System")], default="direct", max_length=20)),
                ("status", models.CharField(choices=[("active", "Active"), ("archived", "Archived"), ("closed", "Closed")], default="active", max_length=20)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_conversations", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-updated_at"]},
        ),
        migrations.CreateModel(
            name="CommunicationNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("body", models.TextField(blank=True)),
                ("notification_type", models.CharField(max_length=100)),
                ("event_type", models.CharField(max_length=120)),
                ("channel", models.CharField(choices=[("in_app", "In-app"), ("email_transactional", "Email transactionnel"), ("email_marketing", "Email marketing"), ("websocket", "WebSocket"), ("sms_future", "SMS futur")], max_length=30)),
                ("priority", models.CharField(choices=[("low", "Low"), ("normal", "Normal"), ("high", "High"), ("critical", "Critical")], default="normal", max_length=12)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("queued", "Queued"), ("sent", "Sent"), ("delivered", "Delivered"), ("read", "Read"), ("failed", "Failed"), ("skipped", "Skipped")], default="pending", max_length=20)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("legacy_source", models.CharField(blank=True, max_length=80)),
                ("legacy_object_id", models.CharField(blank=True, max_length=64)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="communication_notifications_sent", to=settings.AUTH_USER_MODEL)),
                ("event", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notifications", to="communication.communicationevent")),
                ("recipient", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="communication_notifications", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ConversationMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("message_type", models.CharField(choices=[("text", "Text"), ("system", "System"), ("event", "Event")], default="text", max_length=20)),
                ("body", models.TextField()),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("edited_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("author", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="conversation_messages", to=settings.AUTH_USER_MODEL)),
                ("conversation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="communication.conversation")),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="replies", to="communication.conversationmessage")),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.CreateModel(
            name="CommunicationDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("channel", models.CharField(choices=[("in_app", "In-app"), ("email_transactional", "Email transactionnel"), ("email_marketing", "Email marketing"), ("websocket", "WebSocket"), ("sms_future", "SMS futur")], max_length=30)),
                ("provider", models.CharField(blank=True, max_length=50)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("queued", "Queued"), ("sent", "Sent"), ("delivered", "Delivered"), ("read", "Read"), ("failed", "Failed"), ("skipped", "Skipped")], default="pending", max_length=20)),
                ("attempt_count", models.PositiveIntegerField(default=0)),
                ("provider_message_id", models.CharField(blank=True, max_length=120)),
                ("payload_snapshot", models.JSONField(blank=True, default=dict)),
                ("error_message", models.TextField(blank=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("delivered_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("notification", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="deliveries", to="communication.communicationnotification")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ConversationParticipant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("member", "Member"), ("admin", "Admin"), ("system", "System")], default="member", max_length=20)),
                ("notifications_muted", models.BooleanField(default=False)),
                ("last_read_at", models.DateTimeField(blank=True, null=True)),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                ("conversation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="participants", to="communication.conversation")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="conversation_participations", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="MessageAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file", models.FileField(upload_to=communication.models.messaging.conversation_attachment_upload_path)),
                ("original_name", models.CharField(blank=True, max_length=255)),
                ("content_type", models.CharField(blank=True, max_length=120)),
                ("size_bytes", models.PositiveBigIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("message", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attachments", to="communication.conversationmessage")),
            ],
        ),
        migrations.CreateModel(
            name="MessageReadReceipt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("read_at", models.DateTimeField(auto_now_add=True)),
                ("message", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="read_receipts", to="communication.conversationmessage")),
                ("participant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="read_receipts", to="communication.conversationparticipant")),
            ],
        ),
        migrations.AddIndex(
            model_name="communicationevent",
            index=models.Index(fields=["event_type"], name="communicati_event_t_7ac77b_idx"),
        ),
        migrations.AddIndex(
            model_name="communicationevent",
            index=models.Index(fields=["source_app", "created_at"], name="communicati_source__e722d5_idx"),
        ),
        migrations.AddIndex(
            model_name="communicationevent",
            index=models.Index(fields=["status", "created_at"], name="communicati_status_0f0b1f_idx"),
        ),
        migrations.AddIndex(
            model_name="communicationevent",
            index=models.Index(fields=["recipient", "created_at"], name="communicati_recipie_0d5608_idx"),
        ),
        migrations.AddIndex(
            model_name="conversation",
            index=models.Index(fields=["conversation_type", "status"], name="communicati_convers_1ac95d_idx"),
        ),
        migrations.AddIndex(
            model_name="conversation",
            index=models.Index(fields=["updated_at"], name="communicati_updated_7f68a3_idx"),
        ),
        migrations.AddIndex(
            model_name="communicationnotification",
            index=models.Index(fields=["recipient", "status", "created_at"], name="communicati_recipie_ba782d_idx"),
        ),
        migrations.AddIndex(
            model_name="communicationnotification",
            index=models.Index(fields=["channel", "status", "created_at"], name="communicati_channel_9547cb_idx"),
        ),
        migrations.AddIndex(
            model_name="communicationnotification",
            index=models.Index(fields=["event_type", "created_at"], name="communicati_event_t_4f092a_idx"),
        ),
        migrations.AddIndex(
            model_name="communicationnotification",
            index=models.Index(fields=["legacy_source", "legacy_object_id"], name="communicati_legacy__4ec0ab_idx"),
        ),
        migrations.AddIndex(
            model_name="conversationmessage",
            index=models.Index(fields=["conversation", "created_at"], name="communicati_convers_3d150a_idx"),
        ),
        migrations.AddIndex(
            model_name="conversationmessage",
            index=models.Index(fields=["author", "created_at"], name="communicati_author__d16053_idx"),
        ),
        migrations.AddIndex(
            model_name="communicationdelivery",
            index=models.Index(fields=["provider", "status", "created_at"], name="communicati_provider_5ad62a_idx"),
        ),
        migrations.AddIndex(
            model_name="communicationdelivery",
            index=models.Index(fields=["channel", "status", "created_at"], name="communicati_channel_49c6e7_idx"),
        ),
        migrations.AddIndex(
            model_name="conversationparticipant",
            index=models.Index(fields=["user", "joined_at"], name="communicati_user_id_9b4dcd_idx"),
        ),
        migrations.AddIndex(
            model_name="conversationparticipant",
            index=models.Index(fields=["conversation", "role"], name="communicati_convers_d86e02_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="conversationparticipant",
            unique_together={("conversation", "user")},
        ),
        migrations.AddIndex(
            model_name="messagereadreceipt",
            index=models.Index(fields=["participant", "read_at"], name="communicati_partici_2d6cd3_idx"),
        ),
        migrations.AlterUniqueTogether(
            name="messagereadreceipt",
            unique_together={("message", "participant")},
        ),
    ]
