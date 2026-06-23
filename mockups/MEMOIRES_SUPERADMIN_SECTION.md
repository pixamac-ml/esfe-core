## 9-bis. Intégration dans l'application Super Admin (gestion des mémoires)

> **⚠️ Important — corrige/complète la section 9.** Le projet possède **deux espaces distincts** :
> - l'**admin Django par défaut** (`django.contrib.admin`) ;
> - une **application Super Admin personnalisée** (dashboard maison) qui est l'espace de travail réel de Mohamed.
>
> **La gestion des mémoires doit être implémentée dans l'application Super Admin personnalisée**, pas seulement dans l'admin Django. L'enregistrement dans `admin.py` (section 9) est conservé uniquement comme **filet de secours technique** ; le workflow officiel (dépôt, édition, suppression) se fait **dans le Super Admin**.

### 9-bis.1 À faire en premier — inspecter le Super Admin existant
Avant de coder, **lire l'application Super Admin** et reproduire ses patterns :
- son **layout / base template** (sidebar, header, structure de page) ;
- la façon dont les **autres modules y sont branchés** (où sont définies leurs vues, leurs URLs, leur entrée de menu) ;
- son **contrôle d'accès** (mixin/décorateur réservant l'accès aux super admins) ;
- ses **composants UI** (tableaux, formulaires, boutons, modales de confirmation).

➡️ La nouvelle section « Mémoires » doit être **indiscernable** des modules déjà présents dans le Super Admin (même style, même comportement). Si un module existant fait déjà du CRUD, **copie son approche**.

### 9-bis.2 Emplacement du code
Garder la **logique métier dans l'app `memoires`** (modèles, services de rendu, validation), mais les **vues de gestion** s'affichent dans le **layout du Super Admin** et sont branchées sous l'espace d'URL du Super Admin. Suivre la convention du projet :
- soit des vues de gestion dans `memoires/` dont les templates **étendent le base du Super Admin** ;
- soit, si les autres modules logent leurs vues d'administration dans l'app Super Admin, faire pareil.

➡️ **Respecter le pattern déjà en place** (la cohérence prime sur la préférence).

### 9-bis.3 Section « Mémoires » dans le Super Admin — fonctionnalités
Une rubrique complète de gestion, accessible **aux super admins uniquement** :

| Action | Vue | Description |
|---|---|---|
| Lister | `GestionMemoireListView` | Tous les mémoires (**y compris brouillons**), recherche + filtres (filière, niveau, statut, année), pagination. Colonnes : titre, auteurs, niveau, statut, vues, date. |
| Ajouter / Déposer | `GestionMemoireCreateView` | Formulaire métadonnées + upload du PDF. À l'enregistrement : validation (MIME réel, taille), `cree_par = request.user`, puis **génération des images de pages** (service de rendu). |
| Éditer | `GestionMemoireUpdateView` | Modifier les métadonnées. Si le fichier source est remplacé → **régénérer les pages** et purger les anciennes. |
| Supprimer | `GestionMemoireDeleteView` | Confirmation (modale du Super Admin), puis suppression **avec nettoyage du stockage** (voir 9-bis.5). |
| Publier / Dépublier | action / toggle | Bascule `statut` brouillon ↔ publié ; renseigne `date_publication` à la première publication. |
| Mettre en avant | toggle | Bascule `est_mis_en_avant`. |
| (Ré)générer les pages | action | Relance le rendu PDF→images si besoin. |

### 9-bis.4 Vues — squelette (à adapter au pattern du Super Admin)

```python
# vues de gestion (dans memoires/ ou dans l'app Super Admin selon la convention)
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from .models import Memoire
from .forms import MemoireForm


class SuperAdminRequisMixin(LoginRequiredMixin, UserPassesTestMixin):
    """À REMPLACER par le contrôle d'accès Super Admin déjà utilisé dans le projet."""
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_superuser
        # -> utiliser le vrai critère "super admin" du projet


class GestionMemoireListView(SuperAdminRequisMixin, ListView):
    model = Memoire
    template_name = "superadmin/memoires/liste.html"   # étend le base du Super Admin
    paginate_by = 20
    # + recherche/filtres via get_queryset()


class GestionMemoireCreateView(SuperAdminRequisMixin, CreateView):
    model = Memoire
    form_class = MemoireForm
    template_name = "superadmin/memoires/formulaire.html"
    success_url = reverse_lazy("superadmin_memoires:liste")

    def form_valid(self, form):
        form.instance.cree_par = self.request.user
        response = super().form_valid(form)
        # déclencher le rendu PDF -> images (service rendering)
        return response


class GestionMemoireUpdateView(SuperAdminRequisMixin, UpdateView):
    model = Memoire
    form_class = MemoireForm
    template_name = "superadmin/memoires/formulaire.html"
    success_url = reverse_lazy("superadmin_memoires:liste")
    # si fichier_source remplacé -> purger + régénérer les pages


class GestionMemoireDeleteView(SuperAdminRequisMixin, DeleteView):
    model = Memoire
    template_name = "superadmin/memoires/confirmer_suppression.html"
    success_url = reverse_lazy("superadmin_memoires:liste")
```

### 9-bis.5 Suppression propre — nettoyage du stockage (production)
> Django **ne supprime pas** automatiquement les fichiers d'un `FileField`/`ImageField` à la suppression d'un objet. Sans nettoyage, on accumule des fichiers orphelins → coûts de stockage et fuites.

À l'effacement d'un `Memoire`, supprimer du bucket :
- `fichier_source` ;
- toutes les images des `PageMemoire` liés ;
- toute version filigranée en cache.

Implémenter via un signal `post_delete` (ou réutiliser `django-cleanup` s'il est déjà dans le projet) :

```python
# signals.py
from django.db.models.signals import post_delete
from django.dispatch import receiver
from .models import Memoire, PageMemoire

@receiver(post_delete, sender=PageMemoire)
def supprimer_image_page(sender, instance, **kwargs):
    if instance.image:
        instance.image.delete(save=False)

@receiver(post_delete, sender=Memoire)
def supprimer_fichier_source(sender, instance, **kwargs):
    if instance.fichier_source:
        instance.fichier_source.delete(save=False)
    # purger aussi le cache des pages filigranées
```

### 9-bis.6 URLs (espace Super Admin)
À brancher sous le préfixe du Super Admin, selon la convention du projet :

```python
app_name = "superadmin_memoires"

urlpatterns = [
    path("memoires/", GestionMemoireListView.as_view(), name="liste"),
    path("memoires/ajouter/", GestionMemoireCreateView.as_view(), name="ajouter"),
    path("memoires/<slug:slug>/editer/", GestionMemoireUpdateView.as_view(), name="editer"),
    path("memoires/<slug:slug>/supprimer/", GestionMemoireDeleteView.as_view(), name="supprimer"),
]
```

### 9-bis.7 Entrée de menu dans le Super Admin
Ajouter un item **« Mémoires »** dans le **menu/sidebar du Super Admin** (au même endroit que les autres modules), pointant vers `superadmin_memoires:liste`, avec l'icône et l'état actif au style des autres entrées.

### 9-bis.8 Sécurité
- [ ] Toutes les vues de gestion réservées aux **super admins** (réutiliser le contrôle d'accès existant, ne pas réinventer).
- [ ] **CSRF** sur tous les formulaires ; validation d'upload (MIME réel + taille).
- [ ] Suppression = **confirmation explicite** + nettoyage du stockage.
- [ ] Les fichiers restent en **bucket privé** (jamais exposés depuis le Super Admin non plus).

### 9-bis.9 Critères d'acceptation (à ajouter à la section 14)
- [ ] Section « Mémoires » visible dans le **menu du Super Admin**, au style du projet.
- [ ] CRUD complet depuis le Super Admin : lister, déposer/ajouter, éditer, supprimer.
- [ ] Publier/dépublier et mettre en avant depuis le Super Admin.
- [ ] Dépôt déclenche la génération des pages ; remplacement du fichier les régénère.
- [ ] Suppression nettoie réellement le stockage (aucun fichier orphelin).
- [ ] Accès strictement réservé aux super admins.
