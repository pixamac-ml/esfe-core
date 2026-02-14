from django.contrib import admin, messages
from django.db import transaction
from django.utils.html import format_html
from django.utils import timezone

from .models import Candidature, CandidatureDocument
from inscriptions.services import create_inscription_from_candidature


# ==================================================
# INLINE : DOCUMENTS DE LA CANDIDATURE
# ==================================================
class CandidatureDocumentInline(admin.TabularInline):
    model = CandidatureDocument
    extra = 0
    fields = (
        "document_type",
        "file",
        "is_valid",
        "admin_note",
        "uploaded_at",
    )
    readonly_fields = ("uploaded_at",)
    autocomplete_fields = ("document_type",)


# ==================================================
# ADMIN : CANDIDATURE
# ==================================================
@admin.register(Candidature)
class CandidatureAdmin(admin.ModelAdmin):

    # ----------------------------------------------
    # PERFORMANCE
    # ----------------------------------------------
    list_select_related = ("programme",)
    date_hierarchy = "submitted_at"

    # ----------------------------------------------
    # LISTE
    # ----------------------------------------------
    list_display = (
        "full_name",
        "programme",
        "academic_year",
        "entry_year",
        "documents_progress",
        "status_badge",
        "submitted_at",
        "reviewed_at",
    )

    list_filter = (
        "status",
        "academic_year",
        "programme__cycle",
        "programme__filiere",
        "programme",
        "entry_year",
    )

    search_fields = (
        "first_name",
        "last_name",
        "email",
        "phone",
        "programme__title",
    )

    ordering = ("-submitted_at",)
    list_per_page = 25
    autocomplete_fields = ("programme",)

    # ----------------------------------------------
    # LECTURE SEULE
    # ----------------------------------------------
    readonly_fields = (
        "submitted_at",
        "reviewed_at",
        "updated_at",
    )

    # ----------------------------------------------
    # STRUCTURE FORMULAIRE
    # ----------------------------------------------
    fieldsets = (
        ("Programme académique", {
            "fields": (
                "programme",
                "academic_year",
                "entry_year",
            )
        }),
        ("Informations personnelles", {
            "fields": (
                "first_name",
                "last_name",
                "gender",
                "birth_date",
                "birth_place",
            )
        }),
        ("Coordonnées", {
            "fields": (
                "phone",
                "email",
                "address",
                "city",
                "country",
            )
        }),
        ("Décision administrative", {
            "fields": (
                "status",
                "admin_comment",
                "reviewed_at",
            )
        }),
        ("Système", {
            "classes": ("collapse",),
            "fields": (
                "submitted_at",
                "updated_at",
            )
        }),
    )

    inlines = (CandidatureDocumentInline,)

    # ----------------------------------------------
    # ACTIONS
    # ----------------------------------------------
    actions = (
        "mark_under_review",
        "mark_accepted",
        "mark_accepted_with_reserve",
        "mark_to_complete",
        "mark_rejected",
    )

    # ==================================================
    # AFFICHAGES
    # ==================================================

    @admin.display(description="Candidat")
    def full_name(self, obj):
        return obj.full_name

    @admin.display(description="Documents")
    def documents_progress(self, obj):
        total = obj.documents_count
        valid = obj.validated_documents_count

        color = "danger"
        if total and valid == total:
            color = "success"
        elif valid > 0:
            color = "warning"

        return format_html(
            '<span class="badge badge-{}">{}/{} validés</span>',
            color,
            valid,
            total
        )

    @admin.display(description="Statut", ordering="status")
    def status_badge(self, obj):
        classes = {
            "submitted": "secondary",
            "under_review": "primary",
            "to_complete": "warning",
            "accepted": "success",
            "accepted_with_reserve": "info",
            "rejected": "danger",
        }

        return format_html(
            '<span class="badge badge-{}">{}</span>',
            classes.get(obj.status, "secondary"),
            obj.get_status_display()
        )

    # ==================================================
    # SÉCURISATION DES ACTIONS
    # ==================================================

    def get_actions(self, request):
        actions = super().get_actions(request)

        # Exemple futur : restreindre certaines actions
        if not request.user.is_superuser:
            actions.pop("mark_rejected", None)

        return actions

    # ==================================================
    # ACTIONS MÉTIER
    # ==================================================

    @admin.action(description="📂 Passer en cours d’analyse")
    def mark_under_review(self, request, queryset):
        updated = queryset.exclude(status="accepted").update(
            status="under_review",
            reviewed_at=timezone.now()
        )
        messages.success(request, f"{updated} dossier(s) mis en analyse.")

    @admin.action(description="✅ Accepter et créer inscription")
    def mark_accepted(self, request, queryset):

        accepted = 0
        skipped = 0

        for candidature in queryset.select_related("programme"):

            if candidature.status not in (
                "submitted",
                "under_review",
                "to_complete",
            ):
                skipped += 1
                continue

            if getattr(candidature, "inscription_id", None):
                skipped += 1
                continue

            programme = candidature.programme

            if not hasattr(programme, "get_inscription_amount_for_year"):
                messages.error(
                    request,
                    f"{programme} : méthode de calcul absente."
                )
                continue

            amount_due = programme.get_inscription_amount_for_year(
                candidature.entry_year
            )

            if not amount_due or amount_due <= 0:
                messages.error(
                    request,
                    f"Aucun frais configuré pour {programme}."
                )
                continue

            with transaction.atomic():
                create_inscription_from_candidature(
                    candidature=candidature,
                    amount_due=amount_due
                )

                candidature.status = "accepted"
                candidature.reviewed_at = timezone.now()
                candidature.save(update_fields=["status", "reviewed_at"])

            accepted += 1

        if accepted:
            messages.success(
                request,
                f"{accepted} inscription(s) créée(s)."
            )

        if skipped:
            messages.warning(
                request,
                f"{skipped} dossier(s) ignoré(s)."
            )

    @admin.action(description="⚠️ Accepter sous réserve")
    def mark_accepted_with_reserve(self, request, queryset):

        updated = queryset.update(
            status="accepted_with_reserve",
            reviewed_at=timezone.now()
        )

        messages.success(
            request,
            f"{updated} dossier(s) acceptée(s) sous réserve."
        )

    @admin.action(description="📝 Dossier à compléter")
    def mark_to_complete(self, request, queryset):
        updated = queryset.update(
            status="to_complete",
            reviewed_at=timezone.now()
        )
        messages.success(request, f"{updated} dossier(s) marqués à compléter.")

    @admin.action(description="❌ Refuser")
    def mark_rejected(self, request, queryset):
        updated = queryset.update(
            status="rejected",
            reviewed_at=timezone.now()
        )
        messages.success(request, f"{updated} dossier(s) refusé(s).")


# ==================================================
# ADMIN : DOCUMENTS DE CANDIDATURE
# ==================================================
@admin.register(CandidatureDocument)
class CandidatureDocumentAdmin(admin.ModelAdmin):

    list_select_related = ("candidature", "document_type")
    date_hierarchy = "uploaded_at"

    list_display = (
        "candidature",
        "document_type",
        "is_valid",
        "uploaded_at",
    )

    list_filter = (
        "is_valid",
        "document_type",
    )

    search_fields = (
        "candidature__first_name",
        "candidature__last_name",
        "document_type__name",
    )

    ordering = ("-uploaded_at",)
    list_per_page = 25
    readonly_fields = ("uploaded_at",)
