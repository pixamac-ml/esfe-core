from django.contrib import admin, messages

from .forms import MemoireForm
from .models import ConsultationLog, Memoire, PageMemoire
from .services.rendering import render_memoire_pages


class PageMemoireInline(admin.TabularInline):
    model = PageMemoire
    extra = 0
    readonly_fields = ["numero", "image"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Memoire)
class MemoireAdmin(admin.ModelAdmin):
    form = MemoireForm
    list_display = [
        "titre", "auteurs", "filiere", "niveau", "annee",
        "statut", "est_mis_en_avant", "nombre_vues", "nb_pages",
    ]
    list_filter = ["statut", "niveau", "filiere", "annee", "est_mis_en_avant"]
    search_fields = ["titre", "auteurs", "mots_cles"]
    prepopulated_fields = {"slug": ("titre",)}
    readonly_fields = ["nb_pages", "nombre_vues", "date_publication"]
    inlines = [PageMemoireInline]
    actions = ["regenerer_pages"]

    def save_model(self, request, obj, form, change):
        if not obj.cree_par_id:
            obj.cree_par = request.user
        fichier_modifie = "fichier_source" in form.changed_data
        super().save_model(request, obj, form, change)

        if fichier_modifie or not obj.pages.exists():
            self._generer_pages(request, obj)

    def _generer_pages(self, request, memoire):
        try:
            nb_pages = render_memoire_pages(memoire)
        except Exception as exc:  # noqa: BLE001 - on veut un message clair en admin
            self.message_user(
                request,
                f"Échec de la génération des pages pour « {memoire.titre} » : {exc}",
                level=messages.ERROR,
            )
        else:
            self.message_user(
                request,
                f"{nb_pages} page(s) générée(s) pour « {memoire.titre} ».",
                level=messages.SUCCESS,
            )

    @admin.action(description="(Re)générer les images de pages")
    def regenerer_pages(self, request, queryset):
        for memoire in queryset:
            self._generer_pages(request, memoire)


@admin.register(ConsultationLog)
class ConsultationLogAdmin(admin.ModelAdmin):
    list_display = ["memoire", "date"]
    list_filter = ["date"]
    readonly_fields = ["memoire", "date"]

    def has_add_permission(self, request):
        return False
