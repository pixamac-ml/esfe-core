# ESFé Core — Spécification d'implémentation : Application `memoires`

> **Destinataire :** Claude Code (implémentation directe dans le dépôt ESFé Core).
> **Auteur de la spec :** Mohamed Aly Camara
> **Date :** 18 juin 2026
> **Objectif :** Créer une nouvelle application Django `memoires` permettant le **dépôt côté Super Admin** et la **consultation en ligne publique** des mémoires, avec une nouvelle rubrique dans la navbar.
> **Règle d'or :** Code Django propre, modulaire, production-ready. **Aucun hack, aucune solution temporaire.** Sécurité et performance pensées dès le départ.

---

## 0. À FAIRE EN PREMIER — Inspecter l'existant (cohérence obligatoire)

Avant d'écrire la moindre ligne, **inspecter le dépôt** et **t'aligner sur ce qui existe** :

1. **App UI / front-end existante :** Mohamed a une application dédiée au front-end (layout, composants, styles, base templates). **Repère-la**, lis son `base.html`/layout, ses partials (navbar, footer), ses classes Tailwind et ses conventions. **Le front-end de `memoires` doit hériter de ces templates et réutiliser ces composants** — pas de nouveau design parallèle.
2. **Conventions du projet :** structure des apps, nommage (fr/en), organisation `urls.py`, découpage `views.py`, emplacement des templates (`templates/<app>/...`), gestion des settings (par environnement ?), façon dont les autres apps exposent leurs URLs au projet racine.
3. **Stack confirmée :** Django, HTMX, AJAX, JavaScript, Tailwind CSS.

➡️ **Reproduis ces patterns.** Si un choix de cette spec entre en conflit avec une convention déjà en place dans le dépôt, **la convention du dépôt l'emporte** — signale-le simplement.

---

## 1. Décisions de conception (non négociables)

| Sujet | Décision |
|---|---|
| Téléchargement | **❌ Interdit, totalement.** Aucun bouton, aucun lien, aucune demande. **Lecture en ligne seule.** |
| Stockage des fichiers | **Bucket privé compatible S3** via `django-storages`. Jamais d'accès public direct. |
| Servir les fichiers | **URLs signées courtes** générées côté serveur, ou streaming via vue authentifiée (voir §6). |
| Protection du corps | Corps rendu **page par page en images** (pas de couche texte → rien à copier) + **filigrane** à l'identité de l'utilisateur. |
| Résumé (abstract) | **Vrai texte HTML** (sélectionnable, indexable, bon SEO). |
| Popularité | **Nombre de vues** (objectif). ❌ Pas d'étoiles / notation. |

> **⚠️ Honnêteté technique :** aucun blocage navigateur n'est inviolable (capture + OCR, devtools…). On **dissuade fortement** et on **trace** via filigrane. Ne jamais présenter cela comme une protection absolue.

---

## 2. Création de l'application

```bash
python manage.py startapp memoires
```

Ajouter `'memoires'` à `INSTALLED_APPS`. Brancher ses URLs dans le `urls.py` racine selon la convention du projet (préfixe suggéré : `/memoires/`).

**Arborescence cible :**
```
memoires/
├── __init__.py
├── apps.py
├── admin.py
├── models.py
├── views.py
├── urls.py
├── forms.py            # validation upload (taille, MIME réel)
├── services/
│   ├── __init__.py
│   ├── rendering.py     # PDF -> images de pages (pré-génération)
│   └── watermark.py     # filigrane par utilisateur
├── signals.py           # déclenche le rendu après upload
├── templates/
│   └── memoires/
│       ├── liste.html       # hérite du base.html de l'app UI
│       ├── detail.html      # métadonnées + résumé + visionneur
│       └── partials/
│           ├── carte_memoire.html
│           └── visionneur.html
├── static/
│   └── memoires/
│       ├── css/visionneur.css
│       └── js/visionneur.js
└── migrations/
```

---

## 3. Dépendances

```
Pillow            # filigrane, manipulation d'images
PyMuPDF           # (import fitz) rendu PDF -> images, rapide et fiable
django-storages   # backend de stockage S3
boto3             # client S3
```

> PyMuPDF (`fitz`) est recommandé pour le rendu PDF→image : rapide, pas de dépendance système lourde (contrairement à `pdf2image` qui exige `poppler`).

---

## 4. Configuration du stockage (settings)

À adapter aux conventions de settings du projet. Tout en **variables d'environnement** — rien en dur.

```python
# settings (extrait)
STORAGES = {
    "default": {  # fichiers privés (mémoires, pages rendues)
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("S3_BUCKET"),
            "endpoint_url": env("S3_ENDPOINT_URL"),     # fournisseur compatible S3
            "access_key": env("S3_ACCESS_KEY"),
            "secret_key": env("S3_SECRET_KEY"),
            "default_acl": "private",                   # JAMAIS public
            "querystring_auth": True,                   # URLs signées
            "querystring_expire": 300,                  # 5 min
            "file_overwrite": False,
        },
    },
    "staticfiles": { ... },  # selon l'existant
}
```

> Le fournisseur (Cloudflare R2, Backblaze B2, Wasabi, Scaleway…) n'est qu'une question d'`endpoint_url` + clés. Décision fournisseur prise séparément.

---

## 5. Modèle de données (`models.py`)

```python
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.urls import reverse


class Filiere(models.Model):
    nom = models.CharField(max_length=150, unique=True)
    slug = models.SlugField(max_length=160, unique=True)

    def __str__(self):
        return self.nom


class Memoire(models.Model):
    class Niveau(models.TextChoices):
        LICENCE = "licence", "Licence"
        MASTER = "master", "Master"
        DOCTORAT = "doctorat", "Doctorat"

    class Statut(models.TextChoices):
        BROUILLON = "brouillon", "Brouillon"
        PUBLIE = "publie", "Publié"

    titre = models.CharField(max_length=300)
    slug = models.SlugField(max_length=320, unique=True)
    auteurs = models.CharField(max_length=300, help_text="Auteur(s) du mémoire")
    encadreur = models.CharField(max_length=200, blank=True)
    filiere = models.ForeignKey(
        Filiere, on_delete=models.PROTECT, related_name="memoires"
    )
    niveau = models.CharField(max_length=20, choices=Niveau.choices)
    annee = models.PositiveIntegerField()

    resume = models.TextField(help_text="Résumé / abstract affiché publiquement (HTML autorisé).")
    mots_cles = models.CharField(max_length=300, blank=True, help_text="Séparés par des virgules")

    # Fichier source PRIVÉ — jamais servi directement
    fichier_source = models.FileField(upload_to="memoires/sources/")
    nb_pages = models.PositiveIntegerField(default=0)

    est_mis_en_avant = models.BooleanField(default=False, db_index=True)
    statut = models.CharField(
        max_length=20, choices=Statut.choices, default=Statut.BROUILLON, db_index=True
    )
    nombre_vues = models.PositiveIntegerField(default=0)

    date_depot = models.DateTimeField(default=timezone.now)
    date_publication = models.DateTimeField(null=True, blank=True)

    cree_par = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name="memoires_deposes"
    )

    class Meta:
        ordering = ["-date_publication", "-date_depot"]
        indexes = [
            models.Index(fields=["statut", "niveau"]),
            models.Index(fields=["-nombre_vues"]),
        ]

    def __str__(self):
        return f"{self.titre} ({self.annee})"

    def get_absolute_url(self):
        return reverse("memoires:detail", kwargs={"slug": self.slug})

    @property
    def est_public(self):
        return self.statut == self.Statut.PUBLIE


class PageMemoire(models.Model):
    """Image pré-générée d'une page (corps protégé, non copiable)."""
    memoire = models.ForeignKey(Memoire, on_delete=models.CASCADE, related_name="pages")
    numero = models.PositiveIntegerField()
    image = models.ImageField(upload_to="memoires/pages/")  # bucket privé

    class Meta:
        ordering = ["numero"]
        unique_together = ("memoire", "numero")


class ConsultationLog(models.Model):
    """Journal des consultations -> permet le classement 'les plus consultés du mois'."""
    memoire = models.ForeignKey(Memoire, on_delete=models.CASCADE, related_name="consultations")
    date = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["memoire", "date"])]
```

**Choix expliqués :**
- `PageMemoire` stocke les **images pré-rendues** : le visionneur n'expose jamais le PDF, et il n'y a **aucun texte à sélectionner**.
- `ConsultationLog` permet le « plus consulté **du mois** » (impossible avec un simple compteur). `nombre_vues` reste le total cumulé pour l'affichage rapide.
- `on_delete=PROTECT` sur `filiere` : empêche de supprimer une filière qui contient des mémoires (intégrité).

---

## 6. Rendu PDF → images + filigrane (`services/`)

### 6.1 Pré-génération à l'upload (`services/rendering.py`)
À la sauvegarde d'un `Memoire` avec un `fichier_source` (via `signals.py`, en tâche post-save) :
1. Ouvrir le PDF avec `fitz`.
2. Rendre chaque page en image (DPI ~120–150, format **WebP** pour le poids).
3. Créer un `PageMemoire` par page (stockage privé).
4. Mettre à jour `nb_pages`.

> ⚠️ **Performance :** ne JAMAIS rendre à la volée à chaque consultation. Le rendu se fait **une seule fois** au dépôt. Si une file de tâches (Celery/RQ) existe déjà dans le projet, déporter le rendu en asynchrone ; sinon, le faire en synchrone à la sauvegarde admin avec un message clair.

### 6.2 Filigrane par utilisateur (`services/watermark.py`)
Le filigrane porte l'identité de l'utilisateur connecté (ex. email + horodatage), en semi-transparence répétée.

**Approche recommandée (traçabilité solide) :** filigrane **incrusté côté serveur** avec Pillow au moment de servir la page, **avec cache** par `(user_id, memoire_id, page)` pour ne pas recalculer à chaque requête.

**Alternative plus légère (MVP) :** servir l'image de base via URL signée + **overlay de filigrane en CSS/JS** côté client. Plus rapide, mais retirable via devtools. *Documenter ce compromis.*

➡️ **Par défaut : approche serveur avec cache.** Basculer sur l'overlay seulement si la charge CPU pose problème.

---

## 7. Vues (`views.py`)

1. **`MemoireListView` (publique)** — uniquement `statut=PUBLIE`. Filtres (filière, niveau, année), recherche (titre/auteurs/mots-clés), **pagination**. Contextes additionnels : `mis_en_avant` (épinglés) et `plus_consultes_mois` (via `ConsultationLog`).
2. **`MemoireDetailView` (publique)** — métadonnées + **résumé HTML** + visionneur. Incrémente la vue **une fois par session** (dédoublonnage via `request.session`) et crée un `ConsultationLog`.
3. **`servir_page` (authentification/contrôle requis)** — `GET /memoires/<slug>/page/<int:numero>/` :
   - vérifie que le mémoire est public,
   - récupère l'image de base depuis le bucket privé,
   - applique le filigrane utilisateur (cache),
   - **streame l'image** (`HttpResponse` `image/webp`) **ou** redirige vers une URL signée courte de la version filigranée.
   - En-têtes anti-cache navigateur sur la réponse.

> Recherche : si PostgreSQL est utilisé, privilégier `SearchVector`/`SearchQuery` (full-text) sur titre + résumé + mots-clés. Sinon, `icontains` filtré, en attendant.

---

## 8. URLs (`urls.py`)

```python
from django.urls import path
from . import views

app_name = "memoires"

urlpatterns = [
    path("", views.MemoireListView.as_view(), name="liste"),
    path("<slug:slug>/", views.MemoireDetailView.as_view(), name="detail"),
    path("<slug:slug>/page/<int:numero>/", views.servir_page, name="page"),
]
```

---

## 9. Administration (`admin.py`) — dépôt côté Super Admin

- Enregistrer `Memoire`, `Filiere` dans l'admin Super Admin (selon l'admin existant du projet).
- Formulaire de dépôt : champs métadonnées + upload `fichier_source`.
- **Validation à l'upload** (dans `forms.py`) : extension **ET type MIME réel** = PDF, **taille max** (ex. 50 Mo), rejet sinon.
- Le passage `statut = Publié` renseigne `date_publication` et déclenche (ou confirme) la génération des pages.
- Action admin : « (Re)générer les images de pages ».
- `prepopulated_fields = {"slug": ("titre",)}`.

---

## 10. Front-end — hériter de l'app UI existante

- **`liste.html` et `detail.html` étendent le `base.html` de l'app UI** et réutilisent ses composants (cartes, boutons, grille, couleurs Tailwind).
- **`partials/carte_memoire.html`** : titre, auteurs, filière/niveau/année, extrait du résumé, badge « Mis en avant », nombre de vues.
- **`detail.html`** : métadonnées + **résumé en HTML** + visionneur.
- **`partials/visionneur.html` + `static/memoires/js/visionneur.js`** :
  - affichage **page par page en images**, navigation précédent/suivant, **lazy loading** (charger la page n+1 à l'approche),
  - **aucun bouton de téléchargement**, aucune URL de fichier source exposée,
  - anti-copie : `user-select: none`, blocage des événements `copy`, `contextmenu`, `dragstart` sur le visionneur,
  - chargement des pages via l'endpoint `memoires:page`.

> HTMX peut servir la navigation/pagination de la liste pour rester cohérent avec le reste du site.

---

## 11. Navbar — nouvelle rubrique

Ajouter une entrée **« Mémoires »** dans la **navbar du haut** (le partial de navigation de l'app UI), pointant vers `{% url 'memoires:liste' %}`. Respecter le style et l'état actif des autres liens.

---

## 12. Sécurité — checklist non négociable

- [ ] `fichier_source` et `PageMemoire.image` en **bucket privé** (`default_acl="private"`).
- [ ] Aucune URL de fichier source exposée au client.
- [ ] Accès aux pages via **URLs signées courtes** ou vue contrôlée.
- [ ] **Filigrane utilisateur** sur chaque page servie.
- [ ] **Validation upload** : MIME réel + taille max + extension.
- [ ] Vue `servir_page` : vérifie le statut publié ; en-têtes anti-cache.
- [ ] Anti-copie côté client (en complément, pas en remplacement de l'absence de texte).
- [ ] Pas de secrets en dur — tout en variables d'environnement.

---

## 13. Performance

- [ ] Rendu des pages **une seule fois** au dépôt (jamais à la consultation).
- [ ] Images en **WebP**, DPI raisonnable.
- [ ] **Lazy loading** page par page ; **pagination** sur la liste.
- [ ] **Cache** des pages filigranées par utilisateur.
- [ ] Index DB déjà déclarés sur le modèle.

---

## 14. Critères d'acceptation (definition of done)

- [ ] App `memoires` créée, cohérente avec la structure et l'UI existantes.
- [ ] Dépôt d'un mémoire depuis le Super Admin → publication automatique côté public.
- [ ] Page liste : recherche, filtres, pagination, « mis en avant », « plus consultés du mois ».
- [ ] Page détail : métadonnées + résumé HTML + visionneur en ligne stylisé.
- [ ] Visionneur : pages en images, lazy loading, **aucun téléchargement**, anti-copie, filigrane.
- [ ] Stockage privé S3 + URLs signées + validation upload opérationnels.
- [ ] Compteur de vues + journal de consultation fonctionnels.
- [ ] Rubrique « Mémoires » présente dans la navbar.
- [ ] Aucune régression sur le reste du site ; conventions du projet respectées.

---

## 15. Variables d'environnement à prévoir

```
S3_ENDPOINT_URL=
S3_BUCKET=
S3_ACCESS_KEY=
S3_SECRET_KEY=
MEMOIRE_UPLOAD_MAX_MB=50
MEMOIRE_RENDER_DPI=130
```
