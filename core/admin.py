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






from django.contrib import admin, messages
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags, format_html
from django.utils.safestring import mark_safe
from django.conf import settings
from django.utils import timezone

from .models import ContactMessage


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

    # ==================================
    # AFFICHAGE RÉFÉRENCE COURTE
    # ==================================

    def reference_short(self, obj):
        return str(obj.reference)[:8]
    reference_short.short_description = "Réf."

    # ==================================
    # RESPONSABLE
    # ==================================

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

    # ==================================
    # BADGE PRIORITÉ
    # ==================================

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

    # ==================================
    # BADGE STATUT
    # ==================================

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

    # ==================================
    # INDICATEUR SLA
    # ==================================

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

    # ==================================
    # ENVOI EMAIL + WORKFLOW
    # ==================================

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

            html_content = render_to_string(
                "emails/contact_reply.html",
                context
            )

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

    # ==================================
    # PROTECTION APRÈS CLÔTURE
    # ==================================

    def has_change_permission(self, request, obj=None):
        if obj and obj.status == "closed":
            return False
        return super().has_change_permission(request, obj)



@admin.register(AboutSection)
class AboutSectionAdmin(admin.ModelAdmin):

    list_display = ("title", "is_active", "order")
    list_editable = ("is_active", "order")
    ordering = ("order",)
    search_fields = ("title",)

    fieldsets = (
        ("Contenu", {
            "fields": (
                "title",
                "content",
            )
        }),
        ("Organisation", {
            "fields": (
                "is_active",
                "order",
            )
        }),
    )