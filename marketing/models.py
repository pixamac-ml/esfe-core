from django.conf import settings
from django.db import models
from django.utils import timezone


class MarketingAudienceMixin(models.Model):
    SCOPE_ALL = "all"
    SCOPE_BRANCHES = "branches"
    SCOPE_CUSTOM = "custom"
    SCOPE_CHOICES = [
        (SCOPE_ALL, "Tout ESFE"),
        (SCOPE_BRANCHES, "Annexes selectionnees"),
        (SCOPE_CUSTOM, "Ciblage avance"),
    ]

    audience_scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default=SCOPE_ALL, db_index=True)
    branches = models.ManyToManyField("branches.Branch", blank=True)
    formations = models.ManyToManyField("formations.Programme", blank=True)
    cycles = models.ManyToManyField("formations.Cycle", blank=True)
    classes = models.ManyToManyField("academics.AcademicClass", blank=True)
    target_roles = models.JSONField(default=list, blank=True)
    target_user_types = models.JSONField(default=list, blank=True)
    audience_tags = models.JSONField(default=list, blank=True)

    class Meta:
        abstract = True

    @property
    def audience_label(self):
        if self.audience_scope == self.SCOPE_ALL:
            return "Tout ESFE"
        branch_names = list(self.branches.values_list("name", flat=True)[:3])
        if branch_names:
            suffix = "..." if self.branches.count() > 3 else ""
            return ", ".join(branch_names) + suffix
        return self.get_audience_scope_display()


class Announcement(MarketingAudienceMixin):
    TYPE_EVENT = "event"
    TYPE_GENERAL = "general"
    TYPE_URGENCY = "urgency"
    TYPE_REMINDER = "reminder"
    TYPE_ACADEMIC = "academic"
    TYPE_DG = "dg"
    TYPE_COURSE_SUSPENSION = "course_suspension"
    TYPE_INTERNAL_CAMPAIGN = "internal_campaign"
    TYPE_CHOICES = [
        (TYPE_EVENT, "Evenement"),
        (TYPE_GENERAL, "Annonce generale"),
        (TYPE_URGENCY, "Urgence"),
        (TYPE_REMINDER, "Rappel"),
        (TYPE_ACADEMIC, "Information academique"),
        (TYPE_DG, "Communication DG"),
        (TYPE_COURSE_SUSPENSION, "Suspension cours"),
        (TYPE_INTERNAL_CAMPAIGN, "Campagne interne"),
    ]

    PRIORITY_LOW = "low"
    PRIORITY_NORMAL = "normal"
    PRIORITY_HIGH = "high"
    PRIORITY_CRITICAL = "critical"
    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Faible"),
        (PRIORITY_NORMAL, "Normale"),
        (PRIORITY_HIGH, "Haute"),
        (PRIORITY_CRITICAL, "Critique"),
    ]

    STATUS_DRAFT = "draft"
    STATUS_SCHEDULED = "scheduled"
    STATUS_ACTIVE = "active"
    STATUS_EXPIRED = "expired"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Brouillon"),
        (STATUS_SCHEDULED, "Planifiee"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_EXPIRED, "Expiree"),
        (STATUS_ARCHIVED, "Archivee"),
    ]

    title = models.CharField(max_length=180, db_index=True)
    announcement_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default=TYPE_GENERAL, db_index=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default=PRIORITY_NORMAL, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="marketing_announcements")
    content = models.TextField(blank=True)
    channels = models.JSONField(default=list, blank=True)
    show_popup = models.BooleanField(default=False, db_index=True)
    is_blocking_popup = models.BooleanField(default=False)
    starts_at = models.DateTimeField(default=timezone.now, db_index=True)
    ends_at = models.DateTimeField(null=True, blank=True, db_index=True)
    scheduled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "priority", "starts_at"]),
            models.Index(fields=["announcement_type", "status"]),
        ]

    def __str__(self):
        return self.title


class Campaign(MarketingAudienceMixin):
    STATUS_DRAFT = "draft"
    STATUS_SCHEDULED = "scheduled"
    STATUS_ACTIVE = "active"
    STATUS_PAUSED = "paused"
    STATUS_COMPLETED = "completed"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Brouillon"),
        (STATUS_SCHEDULED, "Planifiee"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAUSED, "En pause"),
        (STATUS_COMPLETED, "Terminee"),
        (STATUS_ARCHIVED, "Archivee"),
    ]
    CHANNEL_EMAIL = "email"
    CHANNEL_WHATSAPP_FUTURE = "whatsapp_future"
    CHANNEL_SMS_FUTURE = "sms_future"
    CHANNEL_CHOICES = [
        (CHANNEL_EMAIL, "Email Brevo"),
        (CHANNEL_WHATSAPP_FUTURE, "WhatsApp futur"),
        (CHANNEL_SMS_FUTURE, "SMS futur"),
    ]

    name = models.CharField(max_length=180, db_index=True)
    objective = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    channel = models.CharField(max_length=30, choices=CHANNEL_CHOICES, default=CHANNEL_EMAIL, db_index=True)
    starts_at = models.DateTimeField(null=True, blank=True, db_index=True)
    ends_at = models.DateTimeField(null=True, blank=True, db_index=True)
    budget_estimate = models.PositiveBigIntegerField(default=0)
    content = models.TextField(blank=True)
    progress = models.PositiveSmallIntegerField(default=0)
    brevo_campaign_id = models.CharField(max_length=120, blank=True, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="marketing_campaigns")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "channel", "starts_at"]),
        ]

    def __str__(self):
        return self.name


class CampaignAudience(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="audience_segments")
    name = models.CharField(max_length=120)
    source = models.CharField(max_length=80, blank=True)
    filters = models.JSONField(default=dict, blank=True)
    estimated_size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["campaign", "name"]

    def __str__(self):
        return f"{self.campaign} - {self.name}"


class MarketingMedia(models.Model):
    TYPE_POSTER = "poster"
    TYPE_VIDEO = "video"
    TYPE_LOGO = "logo"
    TYPE_PDF = "pdf"
    TYPE_REEL = "reel"
    TYPE_FLYER = "flyer"
    TYPE_JINGLE = "jingle"
    TYPE_CHOICES = [
        (TYPE_POSTER, "Affiche"),
        (TYPE_VIDEO, "Video"),
        (TYPE_LOGO, "Logo"),
        (TYPE_PDF, "PDF"),
        (TYPE_REEL, "Reel"),
        (TYPE_FLYER, "Flyer"),
        (TYPE_JINGLE, "Jingle"),
    ]

    title = models.CharField(max_length=160, db_index=True)
    media_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_POSTER, db_index=True)
    file = models.FileField(upload_to="marketing/media/")
    tags = models.JSONField(default=list, blank=True)
    branches = models.ManyToManyField("branches.Branch", blank=True, related_name="marketing_media")
    is_archived = models.BooleanField(default=False, db_index=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="marketing_media_uploads")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["media_type", "is_archived"])]

    def __str__(self):
        return self.title


class ProspectLead(models.Model):
    SOURCE_WEBSITE = "website"
    SOURCE_FORM = "form"
    SOURCE_NEWSLETTER = "newsletter"
    SOURCE_CSV = "csv"
    SOURCE_EVENT = "event"
    SOURCE_CAMPAIGN = "campaign"
    SOURCE_CHOICES = [
        (SOURCE_WEBSITE, "Site web"),
        (SOURCE_FORM, "Formulaire"),
        (SOURCE_NEWSLETTER, "Newsletter"),
        (SOURCE_CSV, "Import CSV"),
        (SOURCE_EVENT, "Evenement"),
        (SOURCE_CAMPAIGN, "Campagne"),
    ]

    full_name = models.CharField(max_length=160, db_index=True)
    email = models.EmailField(blank=True, db_index=True)
    phone = models.CharField(max_length=40, blank=True, db_index=True)
    city = models.CharField(max_length=100, blank=True, db_index=True)
    interested_branch = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.SET_NULL, related_name="marketing_prospects")
    interested_programme = models.ForeignKey("formations.Programme", null=True, blank=True, on_delete=models.SET_NULL, related_name="marketing_prospects")
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES, default=SOURCE_FORM, db_index=True)
    tags = models.JSONField(default=list, blank=True)
    consent_email = models.BooleanField(default=True)
    brevo_contact_id = models.CharField(max_length=120, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["source", "created_at"])]

    def __str__(self):
        return self.full_name


class DispatchLog(models.Model):
    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"
    STATUS_CHOICES = [
        (STATUS_PENDING, "En attente"),
        (STATUS_SENT, "Envoye"),
        (STATUS_FAILED, "Erreur"),
        (STATUS_SKIPPED, "Ignore"),
    ]

    announcement = models.ForeignKey(Announcement, null=True, blank=True, on_delete=models.SET_NULL, related_name="dispatch_logs")
    campaign = models.ForeignKey(Campaign, null=True, blank=True, on_delete=models.SET_NULL, related_name="dispatch_logs")
    channel = models.CharField(max_length=40, db_index=True)
    provider = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    audience_snapshot = models.JSONField(default=dict, blank=True)
    recipients_count = models.PositiveIntegerField(default=0)
    opened_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="marketing_dispatch_logs")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["channel", "status", "created_at"])]

    def __str__(self):
        source = self.announcement or self.campaign or "Diffusion"
        return f"{source} - {self.channel} - {self.status}"


class ScheduledCampaign(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="schedules")
    scheduled_for = models.DateTimeField(db_index=True)
    recurrence = models.CharField(max_length=60, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_processed = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["scheduled_for"]
        indexes = [models.Index(fields=["is_processed", "scheduled_for"])]

    def __str__(self):
        return f"{self.campaign} - {self.scheduled_for:%Y-%m-%d %H:%M}"


class MarketingSettings(models.Model):
    sender_email = models.EmailField(blank=True)
    sender_name = models.CharField(max_length=120, blank=True)
    brevo_api_key_label = models.CharField(max_length=120, blank=True)
    popup_primary_color = models.CharField(max_length=20, default="#2563eb")
    popup_duration_seconds = models.PositiveSmallIntegerField(default=8)
    notification_behaviour = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Parametre marketing"
        verbose_name_plural = "Parametres marketing"

    def __str__(self):
        return "Parametres marketing"
