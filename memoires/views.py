from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.generic import DetailView, ListView
from datetime import timedelta

from formations.models import Filiere

from .models import ConsultationLog, Memoire, PageMemoire
from .services.watermark import get_watermarked_page, watermark_identity

PAGE_SIZE = 12


class MemoireListView(ListView):
    model = Memoire
    template_name = "memoires/liste.html"
    context_object_name = "memoires"
    paginate_by = PAGE_SIZE

    def get_template_names(self):
        if self.request.headers.get("HX-Request"):
            return ["memoires/partials/_resultats.html"]
        return [self.template_name]

    def get_queryset(self):
        queryset = Memoire.objects.filter(statut=Memoire.Statut.PUBLIE).select_related("filiere")

        recherche = self.request.GET.get("q", "").strip()
        if recherche:
            queryset = queryset.filter(
                Q(titre__icontains=recherche)
                | Q(auteurs__icontains=recherche)
                | Q(mots_cles__icontains=recherche)
            )

        filiere = self.request.GET.get("filiere", "").strip()
        if filiere.isdigit():
            queryset = queryset.filter(filiere_id=filiere)

        niveau = self.request.GET.get("niveau", "").strip()
        if niveau:
            queryset = queryset.filter(niveau=niveau)

        annee = self.request.GET.get("annee", "").strip()
        if annee:
            queryset = queryset.filter(annee=annee)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        depuis_30_jours = timezone.now() - timedelta(days=30)
        plus_consultes_ids = (
            ConsultationLog.objects.filter(date__gte=depuis_30_jours)
            .values("memoire_id")
            .annotate(total=Count("id"))
            .order_by("-total")
            .values_list("memoire_id", flat=True)[:5]
        )
        plus_consultes = list(
            Memoire.objects.filter(id__in=plus_consultes_ids, statut=Memoire.Statut.PUBLIE)
        )
        plus_consultes.sort(key=lambda m: list(plus_consultes_ids).index(m.id))

        context.update(
            {
                "mis_en_avant": Memoire.objects.filter(
                    statut=Memoire.Statut.PUBLIE, est_mis_en_avant=True
                )[:6],
                "plus_consultes_mois": plus_consultes,
                "filieres": Filiere.objects.filter(is_active=True).order_by("name"),
                "niveaux": Memoire.Niveau.choices,
                "q": self.request.GET.get("q", ""),
                "filiere_active": self.request.GET.get("filiere", ""),
                "niveau_actif": self.request.GET.get("niveau", ""),
                "annee_active": self.request.GET.get("annee", ""),
            }
        )
        return context


class MemoireDetailView(DetailView):
    model = Memoire
    template_name = "memoires/detail.html"
    context_object_name = "memoire"

    def get_queryset(self):
        return Memoire.objects.filter(statut=Memoire.Statut.PUBLIE).select_related("filiere")

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        self._comptabiliser_vue(request)
        return response

    def _comptabiliser_vue(self, request):
        session_key = f"memoire_vue_{self.object.pk}"
        if request.session.get(session_key):
            return

        Memoire.objects.filter(pk=self.object.pk).update(
            nombre_vues=self.object.nombre_vues + 1
        )
        ConsultationLog.objects.create(memoire=self.object)
        request.session[session_key] = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["pages_numeros"] = range(1, self.object.nb_pages + 1)
        context["mots_cles_liste"] = [
            mot.strip() for mot in self.object.mots_cles.split(",") if mot.strip()
        ]
        context["memoires_similaires"] = (
            Memoire.objects.filter(statut=Memoire.Statut.PUBLIE, filiere=self.object.filiere)
            .exclude(pk=self.object.pk)
            .select_related("filiere")[:3]
        )
        return context


def servir_page(request, slug, numero):
    memoire = get_object_or_404(Memoire, slug=slug, statut=Memoire.Statut.PUBLIE)
    page = get_object_or_404(PageMemoire, memoire=memoire, numero=numero)

    identity = watermark_identity(request)
    try:
        image_bytes = get_watermarked_page(page, identity)
    except FileNotFoundError as exc:
        raise Http404("Page introuvable.") from exc

    response = HttpResponse(image_bytes, content_type="image/webp")
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response["Pragma"] = "no-cache"
    return response
