from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import DetailView, ListView
from datetime import timedelta

from formations.models import Filiere

from .models import ConsultationLog, Memoire, MemoireFavori, PageMemoire
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
        context["memoires_similaires"] = self._trouver_similaires()

        # Vérifier si le mémoire est en favori pour l'utilisateur connecté
        context["est_favori"] = False
        if self.request.user.is_authenticated:
            context["est_favori"] = MemoireFavori.objects.filter(
                user=self.request.user, memoire=self.object
            ).exists()

        return context

    def _trouver_similaires(self):
        """Trouve les mémoires similaires par scoring multi-critères."""
        memoire = self.object
        candidats = Memoire.objects.filter(
            statut=Memoire.Statut.PUBLIE
        ).exclude(pk=memoire.pk).select_related("filiere")

        # Mots-clés du mémoire actuel
        cles_actuelles = {
            mot.strip().lower()
            for mot in memoire.mots_cles.split(",")
            if mot.strip()
        }

        score_map = {}
        for m in candidats:
            score = 0

            # 1. Même filière (+10 points)
            if m.filiere_id == memoire.filiere_id:
                score += 10

            # 2. Mots-clés en commun (+3 par mot commun)
            if cles_actuelles:
                cles_candidat = {
                    mot.strip().lower()
                    for mot in m.mots_cles.split(",")
                    if mot.strip()
                }
                communs = cles_actuelles & cles_candidat
                score += len(communs) * 3

            # 3. Même année (+2 points)
            if m.annee == memoire.annee:
                score += 2

            # 4. Même encadreur (+2 points)
            if memoire.encadreur and m.encadreur:
                if memoire.encadreur.lower().strip() == m.encadreur.lower().strip():
                    score += 2

            # 5. Même niveau (+1 point)
            if m.niveau == memoire.niveau:
                score += 1

            if score > 0:
                score_map[m] = score

        # Tri par score décroissant, puis par vues
        classés = sorted(score_map.items(), key=lambda x: (-x[1], -x[0].nombre_vues))
        return [m for m, _ in classés[:4]]


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


# ================= FAVORIS =================


@login_required
def toggle_favori(request, slug):
    """Ajoute ou retire un mémoire des favoris (POST uniquement)."""
    if request.method != "POST":
        return JsonResponse({"error": "Méthode non autorisée"}, status=405)

    memoire = get_object_or_404(Memoire, slug=slug, statut=Memoire.Statut.PUBLIE)
    favori, created = MemoireFavori.objects.get_or_create(
        user=request.user, memoire=memoire
    )

    if not created:
        favori.delete()
        return JsonResponse({"status": "removed", "favoris_count": MemoireFavori.objects.filter(memoire=memoire).count()})

    return JsonResponse({"status": "added", "favoris_count": MemoireFavori.objects.filter(memoire=memoire).count()})


@login_required
def favoris_liste(request):
    """Page listant les favoris de l'utilisateur."""
    favoris = MemoireFavori.objects.filter(
        user=request.user
    ).select_related("memoire", "memoire__filiere")

    page = request.GET.get("page")
    paginator = Paginator(favoris, 12)
    page_obj = paginator.get_page(page)

    return render(request, "memoires/favoris.html", {"page_obj": page_obj})
