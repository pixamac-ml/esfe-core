from django.contrib import admin
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from .models import (
    Institution,
    LegalPage,
    LegalSection,
    LegalSidebarBlock,
    LegalPageHistory,
    InstitutionStat, ContactMessage, AboutSection,
    Notification,
    StatusHistory,
)


# ==========================================================
# INSTITUTION
# ==========================================================

@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "city",
        "country",
        "phone",
        "email",
        "updated_at",
    )

    search_fields = ("name", "city", "email")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("Informations générales", {
            "fields": (
                "name",
                "short_name",
                "legal_status",
                "approval_number",
            )
        }),
        ("Coordonnées", {
            "fields": (
                "address",
                "city",
                "country",
                "phone",
                "email",
            )
        }),
        ("Hébergement", {
            "fields": (
                "hosting_provider",
                "hosting_location",
            )
        }),
        ("Métadonnées", {
            "fields": (
                "created_at",
                "updated_at",
            )
        }),
    )

    def has_add_permission(self, request):
        """
        Empêche la création de plusieurs institutions.
        """
        if Institution.objects.exists():
            return False
        return True


# ==========================================================
# SECTIONS INLINE
# ==========================================================

class LegalSectionInline(admin.TabularInline):
    model = LegalSection
    extra = 1
    ordering = ("order",)
    fields = ("order", "title", "content")


class LegalSidebarInline(admin.TabularInline):
    model = LegalSidebarBlock
    extra = 1
    ordering = ("order",)
    fields = ("order", "title", "content")


# ==========================================================
# PAGE LÉGALE
# ==========================================================

@admin.register(LegalPage)
class LegalPageAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "page_type",
        "status",
        "version",
        "updated_at",
    )

    list_filter = ("page_type", "status")
    search_fields = ("title", "version")
    readonly_fields = ("created_at", "updated_at")

    inlines = [LegalSectionInline, LegalSidebarInline]

    fieldsets = (
        ("Informations principales", {
            "fields": (
                "page_type",
                "title",
                "introduction",
            )
        }),
        ("Publication", {
            "fields": (
                "status",
                "version",
            )
        }),
        ("Métadonnées", {
            "fields": (
                "created_at",
                "updated_at",
            )
        }),
    )


# ==========================================================
# HISTORIQUE (LECTURE SEULE)
# ==========================================================

@admin.register(LegalPageHistory)
class LegalPageHistoryAdmin(admin.ModelAdmin):

    list_display = ("page", "version", "created_at")
    list_filter = ("version",)
    search_fields = ("page__title", "version")
    readonly_fields = ("page", "version", "content_snapshot", "created_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ==========================================================
# INSTITUTION STATS
# ==========================================================

@admin.register(InstitutionStat)
class InstitutionStatAdmin(admin.ModelAdmin):

    list_display = ("label", "value", "suffix", "order")
    list_editable = ("value", "suffix", "order")
    search_fields = ("label",)
    ordering = ("order",)

    fieldsets = (
        ("Statistique", {
            "fields": (
                "label",
                "value",
                "suffix",
                "order",
            )
        }),
    )


# ==========================================================
# MESSAGES DE CONTACT
# ==========================================================

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags, format_html
from django.conf import settings
from django.utils import timezone


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):

    list_display = (
        "reference_short",
        "full_name",
        "colored_priority",
        "colored_status",
        "sla_indicator",
        "assigned_display",
        "created_at",
    )

    list_filter = (
        "status",
        "priority",
        "subject",
        "assigned_to",
        "created_at",
    )

    search_fields = (
        "reference",
        "full_name",
        "email",
        "message",
        "reply",
    )

    readonly_fields = (
        "reference",
        "ip_address",
        "user_agent",
        "created_at",
        "answered_at",
        "sla_hours",
    )

    ordering = ("-created_at",)
    list_per_page = 25

    def reference_short(self, obj):
        return str(obj.reference)[:8]
    reference_short.short_description = "Réf."

    def assigned_display(self, obj):
        if obj.assigned_to:
            name = obj.assigned_to.get_full_name() or obj.assigned_to.username
            return format_html(
                '<span style="color:#1e4f6f;font-weight:600;">{}</span>',
                name
            )
        return mark_safe(
            '<span style="color:#dc2626;font-weight:600;">Non assigné</span>'
        )
    assigned_display.short_description = "Responsable"

    def colored_priority(self, obj):
        colors = {
            "low": "#94a3b8",
            "normal": "#2563eb",
            "high": "#f97316",
            "urgent": "#dc2626",
        }
        color = colors.get(obj.priority, "#2563eb")
        return format_html(
            '<span style="color:white;background:{};padding:5px 10px;border-radius:20px;font-weight:600;">{}</span>',
            color,
            obj.get_priority_display()
        )
    colored_priority.short_description = "Priorité"

    def colored_status(self, obj):
        colors = {
            "new": "#dc2626",
            "in_progress": "#f59e0b",
            "answered": "#16a34a",
            "closed": "#64748b",
        }
        color = colors.get(obj.status, "#64748b")
        return format_html(
            '<span style="color:white;background:{};padding:5px 10px;border-radius:20px;font-weight:600;">{}</span>',
            color,
            obj.get_status_display()
        )
    colored_status.short_description = "Statut"

    def sla_indicator(self, obj):
        if obj.status in ["answered", "closed"]:
            return mark_safe(
                '<span style="color:#16a34a;font-weight:600;">✓ Traité</span>'
            )
        if obj.is_overdue:
            return mark_safe(
                '<span style="color:white;background:#dc2626;padding:5px 10px;border-radius:20px;font-weight:600;">⚠ En retard</span>'
            )
        return format_html(
            '<span style="color:#2563eb;font-weight:600;">{} h restantes</span>',
            obj.remaining_hours
        )
    sla_indicator.short_description = "SLA"

    def save_model(self, request, obj, form, change):
        reply_added = "reply" in form.changed_data and obj.reply
        already_answered = obj.answered_at is not None

        if reply_added and not already_answered:
            staff_name = request.user.get_full_name() or request.user.username
            context = {
                "message_obj": obj,
                "institution_name": "École de Santé Félix Houphouët Boigny",
                "staff_name": staff_name,
                "contact_email": settings.DEFAULT_FROM_EMAIL,
                "reply_date": timezone.now(),
            }
            html_content = render_to_string("emails/contact_reply.html", context)
            text_content = strip_tags(html_content)
            email = EmailMultiAlternatives(
                subject=f"[ESFé] Réponse à votre demande - {obj.get_subject_display()}",
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[obj.email],
            )
            email.attach_alternative(html_content, "text/html")
            email.send(fail_silently=False)
            obj.status = "answered"
            obj.answered_at = timezone.now()
            messages.success(request, "✔ Réponse envoyée avec succès.")

        super().save_model(request, obj, form, change)

    def has_change_permission(self, request, obj=None):
        if obj and obj.status == "closed":
            return False
        return super().has_change_permission(request, obj)


# ==========================================================
# ABOUT SECTION
# ==========================================================

@admin.register(AboutSection)
class AboutSectionAdmin(admin.ModelAdmin):

    list_display = (
        "section_key",
        "title",
        "order",
        "is_active",
        "updated_at",
        "image_preview",
    )

    list_editable = (
        "order",
        "is_active",
    )

    list_filter = (
        "is_active",
        "section_key",
        "background",
    )

    search_fields = (
        "title",
        "subtitle",
        "content",
    )

    ordering = ("order",)

    readonly_fields = (
        "updated_at",
        "image_preview",
    )

    fieldsets = (
        ("Identification", {
            "fields": (
                "section_key",
                "title",
                "subtitle",
            )
        }),
        ("Contenu principal", {
            "fields": (
                "content",
                "image",
                "image_preview",
                "highlights",
            )
        }),
        ("Apparence", {
            "fields": (
                "icon",
                "background",
            )
        }),
        ("Organisation", {
            "fields": (
                "order",
                "is_active",
            )
        }),
        ("Métadonnées", {
            "fields": (
                "updated_at",
            ),
            "classes": ("collapse",)
        }),
    )

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:70px;border-radius:8px;box-shadow:0 2px 6px rgba(0,0,0,0.1);" />',
                obj.image.url
            )
        return "-"
    image_preview.short_description = "Preview"

    def has_add_permission(self, request):
        max_sections = len(AboutSection.SECTION_CHOICES)
        if AboutSection.objects.count() >= max_sections:
            return False
        return super().has_add_permission(request)


# ==========================================================
# NOTIFICATIONS
# ==========================================================

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):

    list_display = (
        "notification_type_display",
        "recipient_name",
        "recipient_email",
        "title",
        "email_status_badge",
        "sent_at",
        "created_at",
    )

    list_filter = (
        "notification_type",
        "email_sent",
        "created_at",
    )

    search_fields = (
        "recipient_name",
        "recipient_email",
        "title",
        "message",
    )

    readonly_fields = (
        "recipient_email",
        "recipient_name",
        "notification_type",
        "title",
        "message",
        "related_candidature",
        "related_inscription",
        "related_payment",
        "email_sent",
        "sent_at",
        "created_at",
    )

    ordering = ("-created_at",)

    def notification_type_display(self, obj):
        return obj.get_notification_type_display()
    notification_type_display.short_description = "Type"

    def email_status_badge(self, obj):
        if obj.email_sent:
            return format_html(
                '<span style="color:white;background:#16a34a;padding:4px 8px;border-radius:4px;font-weight:600;">✓ Envoyé</span>'
            )
        return format_html(
            '<span style="color:white;background:#f59e0b;padding:4px 8px;border-radius:4px;font-weight:600;">En attente</span>'
        )
    email_status_badge.short_description = "Email"

    def has_add_permission(self, request):
        return False

from django.utils.safestring import mark_safe
# ==========================================================
# HISTORIQUE DES STATUTS
# ==========================================================

@admin.register(StatusHistory)
class StatusHistoryAdmin(admin.ModelAdmin):

    list_display = (
        "entity_display",
        "old_status",
        "new_status",
        "changed_by_display",
        "created_at",
    )

    list_filter = (
        "new_status",
        "created_at",
    )

    search_fields = (
        "candidature__last_name",
        "candidature__first_name",
        "candidature__email",
        "inscription__public_token",
    )

    # Plus de readonly_fields avec ForeignKey
    # On utilise list_display avec des méthodes
    readonly_fields = (
        "old_status",
        "new_status",
        "comment",
        "created_at",
    )

    ordering = ("-created_at",)

    def entity_display(self, obj):
        if obj.candidature:
            c = obj.candidature
            return mark_safe(f"<span class='text-blue-600'>Candidature:</span> {c.last_name} {c.first_name}")
        elif obj.inscription:
            return mark_safe(f"<span class='text-green-600'>Inscription:</span> {obj.inscription.public_token}")
        return "-"
    entity_display.short_description = "Entité"
    entity_display.admin_order_field = "inscription"

    def changed_by_display(self, obj):
        if obj.changed_by:
            return obj.changed_by.get_full_name() or obj.changed_by.username
        return "-"
    changed_by_display.short_description = "Modifié par"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False



