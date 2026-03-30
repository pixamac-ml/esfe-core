# core/admin.py

from django.contrib import admin
from django.contrib import messages
from django.utils.safestring import mark_safe
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.utils import timezone
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError
from django.shortcuts import redirect

from .models import (
    Institution,
    InstitutionPresentation,
    SiteConfiguration,
    Value,
    Infrastructure,
    Staff,
    InstitutionStat,
    Partner,
    LegalPage,
    LegalSection,
    LegalSidebarBlock,
    LegalPageHistory,
    ContactMessage,
    Notification,
    StatusHistory,
)


# ==========================================================
# INSTITUTION (SINGLETON)
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
                "director_title",
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
            ),
            "classes": ("collapse",)
        }),
        ("Métadonnées", {
            "fields": (
                "is_active",
                "created_at",
                "updated_at",
            ),
            "classes": ("collapse",)
        }),
    )

    def has_add_permission(self, request):
        if Institution.objects.exists():
            return False
        return True


# ==========================================================
# PRÉSENTATION INSTITUTIONNELLE (SINGLETON)
# ==========================================================

@admin.register(InstitutionPresentation)
class InstitutionPresentationAdmin(admin.ModelAdmin):

    list_display = (
        "__str__",
        "hero_title",
        "updated_at",
    )

    readonly_fields = ("updated_at",)

    fieldsets = (
        ("Hero (Bannière principale)", {
            "fields": (
                "hero_title",
                "hero_subtitle",
                "hero_image",
            ),
            "description": "Section d'en-tête de la page À propos"
        }),
        ("Présentation de l'école", {
            "fields": (
                "about_title",
                "about_text",
                "about_image",
            )
        }),
        ("Vision & Mission", {
            "fields": (
                "vision_title",
                "vision_text",
                "mission_title",
                "mission_text",
            )
        }),
        ("Appel à l'action (CTA)", {
            "fields": (
                "cta_title",
                "cta_subtitle",
                "cta_button_text",
                "cta_button_url",
            )
        }),
        ("Métadonnées", {
            "fields": ("updated_at",),
            "classes": ("collapse",)
        }),
    )

    def has_add_permission(self, request):
        if InstitutionPresentation.objects.exists():
            return False
        return True

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SiteConfiguration)
class SiteConfigurationAdmin(admin.ModelAdmin):
    list_display = ("__str__", "updated_at")
    readonly_fields = ("updated_at",)

    fieldsets = (
        ("Production - Images cles (Zero statique)", {
            "fields": (
                "home_hero_image",
                "home_about_image",
                "about_hero_image",
                "about_main_image",
            ),
            "description": "Ces 4 images alimentent directement la Landing et la page A propos."
        }),
        ("Branding", {
            "fields": ("site_logo",)
        }),
        ("Accueil - Hero", {
            "fields": (
                "home_hero_title",
                "home_hero_subtitle",
            )
        }),
        ("Accueil - Images sections", {
            "fields": (
                "home_why_image_1",
                "home_why_image_2",
                "home_why_image_3",
                "home_why_image_4",
                "home_annexe_image_1",
                "home_annexe_image_2",
                "home_annexe_image_3",
                "home_annexe_image_4",
                "home_stats_banner_image",
            ),
            "classes": ("collapse",)
        }),
        ("A propos", {
            "fields": (
                "about_stats_banner_image",
                "about_vision_title",
                "about_vision_text",
                "about_values_title",
                "about_values_subtitle",
            )
        }),
        ("Smart Rocket", {
            "fields": (
                "smart_rocket_enabled",
                "smart_rocket_title",
                "smart_rocket_message",
            )
        }),
        ("Metadonnees", {
            "fields": ("updated_at",),
            "classes": ("collapse",)
        }),
    )

    def has_add_permission(self, request):
        # Tant que la migration n'est pas appliquee, la table peut ne pas exister.
        try:
            return not SiteConfiguration.objects.exists()
        except (ProgrammingError, OperationalError):
            return True

    def has_delete_permission(self, request, obj=None):
        return False

    def _site_config_table_exists(self):
        try:
            return SiteConfiguration._meta.db_table in connection.introspection.table_names()
        except (ProgrammingError, OperationalError):
            return False

    def changelist_view(self, request, extra_context=None):
        if not self._site_config_table_exists():
            messages.warning(
                request,
                "La table de configuration du site n'est pas encore créée. "
                "Exécutez d'abord les migrations (python manage.py migrate core).",
            )
            return redirect("admin:index")
        return super().changelist_view(request, extra_context=extra_context)


# ==========================================================
# VALEURS (MAX 4)
# ==========================================================

@admin.register(Value)
class ValueAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "icon_preview",
        "order",
        "is_active",
    )

    list_editable = ("order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("title", "description")
    ordering = ("order",)

    fieldsets = (
        ("Contenu", {
            "fields": (
                "title",
                "description",
                "icon",
            )
        }),
        ("Organisation", {
            "fields": (
                "order",
                "is_active",
            )
        }),
    )

    def icon_preview(self, obj):
        if obj.icon:
            return format_html(
                '<i class="{}" style="font-size:1.5rem;color:#1e4f6f;"></i> <code>{}</code>',
                obj.icon,
                obj.icon
            )
        return "-"
    icon_preview.short_description = "Icône"


# ==========================================================
# INFRASTRUCTURES
# ==========================================================

@admin.register(Infrastructure)
class InfrastructureAdmin(admin.ModelAdmin):

    list_display = (
        "name",
        "category",
        "image_preview",
        "order",
        "is_active",
    )

    list_editable = ("order", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name", "description")
    ordering = ("order",)

    fieldsets = (
        ("Informations", {
            "fields": (
                "name",
                "category",
                "description",
            )
        }),
        ("Média", {
            "fields": (
                "image",
            )
        }),
        ("Caractéristiques", {
            "fields": (
                "features",
            ),
            "description": "Liste JSON des équipements (ex: [\"Microscopes\", \"Analyseurs\"])"
        }),
        ("Organisation", {
            "fields": (
                "order",
                "is_active",
            )
        }),
    )

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:50px;border-radius:6px;box-shadow:0 2px 4px rgba(0,0,0,0.1);" />',
                obj.image.url
            )
        return "-"
    image_preview.short_description = "Photo"


# ==========================================================
# PERSONNEL / STAFF
# ==========================================================

@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):

    list_display = (
        "photo_preview",
        "full_name",
        "position",
        "category_badge",
        "is_featured",
        "order",
        "is_active",
    )

    list_editable = ("order", "is_active", "is_featured")
    list_filter = ("category", "is_active", "is_featured")
    search_fields = ("full_name", "position", "bio")
    ordering = ("category", "order", "full_name")
    list_per_page = 20

    fieldsets = (
        ("Identité", {
            "fields": (
                "full_name",
                "position",
                "category",
                "photo",
            )
        }),
        ("Informations complémentaires", {
            "fields": (
                "bio",
                "email",
                "linkedin",
            ),
            "classes": ("collapse",)
        }),
        ("Organisation", {
            "fields": (
                "is_featured",
                "order",
                "is_active",
            )
        }),
    )

    def photo_preview(self, obj):
        if obj.photo:
            return format_html(
                '<img src="{}" style="width:45px;height:45px;border-radius:50%;object-fit:cover;box-shadow:0 2px 4px rgba(0,0,0,0.15);" />',
                obj.photo.url
            )
        return format_html(
            '<div style="width:45px;height:45px;border-radius:50%;background:#e5e7eb;display:flex;align-items:center;justify-content:center;color:#9ca3af;font-size:1.2rem;">?</div>'
        )
    photo_preview.short_description = ""

    def category_badge(self, obj):
        colors = {
            "direction": "#7c3aed",
            "teacher": "#2563eb",
            "admin": "#059669",
        }
        color = colors.get(obj.category, "#6b7280")
        return format_html(
            '<span style="color:white;background:{};padding:4px 10px;border-radius:20px;font-size:0.75rem;font-weight:600;">{}</span>',
            color,
            obj.get_category_display()
        )
    category_badge.short_description = "Catégorie"


# ==========================================================
# STATISTIQUES / CHIFFRES CLÉS
# ==========================================================

@admin.register(InstitutionStat)
class InstitutionStatAdmin(admin.ModelAdmin):

    list_display = (
        "label",
        "stat_preview",
        "order",
        "is_active",
    )

    list_editable = ("order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("label",)
    ordering = ("order",)

    fieldsets = (
        ("Statistique", {
            "fields": (
                "label",
                "prefix",
                "value",
                "suffix",
            )
        }),
        ("Organisation", {
            "fields": (
                "order",
                "is_active",
            )
        }),
    )

    def stat_preview(self, obj):
        return format_html(
            '<span style="font-size:1.25rem;font-weight:700;color:#1e4f6f;">{}{}{}</span>',
            obj.prefix or "",
            obj.value,
            obj.suffix or ""
        )
    stat_preview.short_description = "Aperçu"


# ==========================================================
# PARTENAIRES
# ==========================================================

@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):

    list_display = (
        "logo_preview",
        "name",
        "partner_type",
        "website_link",
        "order",
        "is_active",
    )

    list_editable = ("order", "is_active")
    list_filter = ("partner_type", "is_active")
    search_fields = ("name", "description")
    ordering = ("order", "name")

    fieldsets = (
        ("Informations", {
            "fields": (
                "name",
                "partner_type",
                "logo",
                "website",
            )
        }),
        ("Description", {
            "fields": (
                "description",
            ),
            "classes": ("collapse",)
        }),
        ("Organisation", {
            "fields": (
                "order",
                "is_active",
            )
        }),
    )

    def logo_preview(self, obj):
        if obj.logo:
            return format_html(
                '<img src="{}" style="height:40px;max-width:100px;object-fit:contain;" />',
                obj.logo.url
            )
        return "-"
    logo_preview.short_description = "Logo"

    def website_link(self, obj):
        if obj.website:
            return format_html(
                '<a href="{}" target="_blank" style="color:#2563eb;">Voir →</a>',
                obj.website
            )
        return "-"
    website_link.short_description = "Site"


# ==========================================================
# PAGES LÉGALES - INLINES
# ==========================================================

class LegalSectionInline(admin.TabularInline):
    model = LegalSection
    extra = 1
    ordering = ("order",)
    fields = ("order", "title", "content", "is_active")


class LegalSidebarInline(admin.TabularInline):
    model = LegalSidebarBlock
    extra = 1
    ordering = ("order",)
    fields = ("order", "title", "content", "is_active")


# ==========================================================
# PAGES LÉGALES
# ==========================================================

@admin.register(LegalPage)
class LegalPageAdmin(admin.ModelAdmin):

    list_display = (
        "title",
        "page_type",
        "status_badge",
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
            ),
            "classes": ("collapse",)
        }),
    )

    def status_badge(self, obj):
        colors = {
            "draft": "#f59e0b",
            "review": "#3b82f6",
            "published": "#16a34a",
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html(
            '<span style="color:white;background:{};padding:4px 10px;border-radius:20px;font-size:0.75rem;font-weight:600;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = "Statut"


# ==========================================================
# HISTORIQUE PAGES LÉGALES (LECTURE SEULE)
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
# MESSAGES DE CONTACT
# ==========================================================

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

    fieldsets = (
        ("Demandeur", {
            "fields": (
                "reference",
                "full_name",
                "email",
                "phone",
            )
        }),
        ("Message", {
            "fields": (
                "subject",
                "message",
            )
        }),
        ("Traitement", {
            "fields": (
                "status",
                "priority",
                "assigned_to",
                "reply",
            )
        }),
        ("Métadonnées", {
            "fields": (
                "sla_hours",
                "answered_at",
                "created_at",
                "ip_address",
                "user_agent",
            ),
            "classes": ("collapse",)
        }),
    )

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
        return format_html(
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
            return format_html(
                '<span style="color:#16a34a;font-weight:600;">✓ Traité</span>'
            )
        if obj.is_overdue:
            return format_html(
                '<span style="color:white;background:#dc2626;padding:5px 10px;border-radius:20px;font-weight:600;">⚠ En retard</span>'
            )
        # Calcul des heures restantes
        remaining = obj.deadline - timezone.now()
        hours_remaining = max(0, int(remaining.total_seconds() // 3600))
        return format_html(
            '<span style="color:#2563eb;font-weight:600;">{} h restantes</span>',
            hours_remaining
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
# NOTIFICATIONS (LECTURE SEULE)
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


# ==========================================================
# HISTORIQUE DES STATUTS (LECTURE SEULE)
# ==========================================================

@admin.register(StatusHistory)
class StatusHistoryAdmin(admin.ModelAdmin):

    list_display = (
        "candidature_display",
        "status_change",
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
    )

    readonly_fields = (
        "candidature",
        "old_status",
        "new_status",
        "changed_by",
        "comment",
        "created_at",
    )

    ordering = ("-created_at",)

    def candidature_display(self, obj):
        if obj.candidature:
            c = obj.candidature
            return f"{c.last_name} {c.first_name}"
        return "-"
    candidature_display.short_description = "Candidature"

    def status_change(self, obj):
        return format_html(
            '<span style="color:#6b7280;">{}</span> → <span style="color:#1e4f6f;font-weight:600;">{}</span>',
            obj.old_status,
            obj.new_status
        )
    status_change.short_description = "Changement"

    def changed_by_display(self, obj):
        if obj.changed_by:
            return obj.changed_by.get_full_name() or obj.changed_by.username
        return "-"
    changed_by_display.short_description = "Par"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False