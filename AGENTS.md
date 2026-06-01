# ESFE Core — Agent Guide

**Django 6.0 / Python 3.14** monolith for ESFE (Mali) school management. French-language project.

## Quick start

```powershell
# activate venv first
pip install -r requirements.txt
npm install
python manage.py migrate
npm run watch:css       # tailwind dev (output: static/public/css/main.css)
python manage.py runserver
```

## Critical commands

| Task | Command |
|------|---------|
| Run tests (all) | `python manage.py test` |
| Run tests (single app) | `python manage.py test core` |
| Run tests (no Postgres/Redis) | `python manage.py test --settings=config.settings_test_local core` |
| Tailwind watch | `npm run watch:css` |
| Tailwind build | `npm run build:css` |
| Seed data | `python manage.py seed_<tab>` (see `seed_bundle/`) |

Use `--settings=config.settings_test_local` for isolated testing — swaps to SQLite, MD5PasswordHasher, InMemoryChannelLayer, and a restricted URL conf (`config.urls_test_local`).

## Architecture

- **ASGI primary** (`config.asgi`) — daphne/channels for WebSocket support via `communication.realtime.routing`
- **WSGI fallback** (`config.wsgi`) — gunicorn + whitenoise for HTTP
- **~19 Django apps** — monolithic layout. Major groups:
  - `core` — home, about, contact, legal pages, SEO, sitemap
  - `ui` — django-components (registered in `core/apps.py:ready()`, live under `ui/components/`), templates, templatetags
  - `communication` — email (Brevo SMTP via `.env`), realtime/WebSocket, notifications, tasks
  - `accounts` / `portal` / `secretary` / `students` — user dashboards
  - `admissions` / `inscriptions` / `payments` / `academic_cycle` / `academics` — core school workflows
  - `shop`, `blog`, `news`, `community`, `formations`, `branches`, `superadmin`, `marketing`
- **Settings**: `config.settings` by default, loads `.env` at project root via `python-dotenv`
- **Postgres** in dev/prod, **SQLite** for local tests
- **Channels layers**: Redis if `REDIS_URL` + `channels_redis` available, else InMemoryChannelLayer
- **Tailwind** via PostCSS — input: `static/src/css/input.css`, output: `static/public/css/main.css`
- **WSGI/ASGI shared state**: `ClientDisconnectSafeASGIApp` wrapper in `config.asgi` swallows `CancelledError` for HTTP
- **Email**: custom `StableSMTPEmailBackend` in `core.mail_backends`; provider "brevo" via SMTP (configured in `.env`)
- **PDF**: weasyprint (legal pages), reportlab (elsewhere)
- **Rich text**: django-ckeditor-5
- **HTMX**: `django_htmx.middleware.HtmxMiddleware` active
- **Admin theme**: django-jazzmin

## URL layout (partial)

```
/                           core:home
/apropos/                   core:about
/contact/                   core:contact
/admin/                     Django admin
/accounts/                  auth + accounts
/portal/                    accounts_portal (namespace)
/portal/student-dashboard/  student portal
/secretary/                 secretary dashboard
/students/                  student management
/formations/                formations
/admissions/, /inscriptions/, /payments/, /academic-cycle/
/blog/, /actualites/        news (namespace "news")
/shop/                      shop (namespace "shop")
/community/                 community
/communication/             communication (namespace)
/marketing/                 marketing (namespace)
/superadmin/                superadmin
/surveillance/general/      IT surveillance API
/ckeditor5/                 CKEditor 5 uploads
```

Full URL config: `config/urls.py` (includes `fallback_404` catch-all). Test URL config: `config/urls_test_local.py` (subset).

## Django components

Registered in `core/apps.py:CoreConfig.ready()` via explicit imports. All components live under `ui/components/`. Pattern:

```python
import ui.components.<category>.<component_name>.<component_name>
```

## Template filter gotchas

- `intcomma` requires `{% load humanize %}` in **every** template that uses it, including HTMX partials rendered independently. Django does not propagate `{% load %}` from parent/including templates.
- `django.contrib.humanize` **is** in `INSTALLED_APPS` — if `intcomma` fails, the partial template lacks `{% load humanize %}`.
- Custom template tag libraries exist at `accounts/templatetags/custom_filters.py` and `core/templatetags/extra_filters.py`.
- The `accounts` dashboard partials under `accounts/templates/accounts/dashboard/partials/` are frequently rendered directly via HTMX views and each must independently load its required libraries.

## Manager (gestionnaire) dashboard layout

Entrypoints in `accounts/dashboards/`:
- `manager_dashboard.py` — main dashboard views (`manager_dashboard`, `manager_candidatures`, `manager_inscriptions`, `manager_paiements`)
- `htmx_manager.py` — all HTMX actions (candidatures, inscriptions, payments, cash sessions, salaries, honoraria, expenses, donations, closures, reports)
- `htmx_admissions.py` / `htmx_finance.py` — legacy HTMX admissions/finance views
- `permissions.py` / `helpers.py` — `is_manager()`, `get_user_branch()`

Access system in `accounts/access.py` provides `can_access()`, `get_user_scope()`. Documented in `accounts/ACCESS_MAPPING.md`.

## Testing quirks

- No pytest or CI config — uses vanilla `unittest`/`TestCase`
- `settings_test_local` bypasses Postgres/Redis — use for quick smoke tests
- Test URL conf is a subset — some app URLs are not included
- All `tests.py` files live inside each app directory

## Important constraints

- **.env contains real secrets** — do not commit, do not expose in logs
- `media/` is gitignored — uploaded files not in repo
- Static build output (`staticfiles/`) is gitignored — run `build:css` before deploy
- No pre-commit hooks, no lint/typecheck config — rely on Django's own checks

# GESTIONNAIRE DASHBOARD — BUSINESS RULES

## Important

Avant toute modification :

* analyser l'existant ;
* comprendre les modèles déjà présents ;
* comprendre les services déjà présents ;
* comprendre les vues HTMX déjà présentes ;
* comprendre les dashboards existants ;
* ne jamais casser le backend actuel ;
* ne jamais supprimer des fonctionnalités existantes ;
* privilégier les extensions et l'amélioration progressive.

---

## Rôle réel de la gestionnaire

La gestionnaire est le centre de pilotage opérationnel et financier d'une annexe.

Elle gère :

* candidatures ;
* inscriptions ;
* paiements ;
* dépenses ;
* caisse ;
* salaires du personnel administratif ;
* honoraires enseignants ;
* boutique ;
* rapports ;
* clôtures mensuelles ;
* versements bancaires.

Le dashboard doit refléter cette réalité métier.

---

## Filtrage obligatoire par annexe

Toutes les données doivent être filtrées par annexe.

Aucune donnée d'une autre annexe ne doit être visible.

Cette règle est critique.

---

## Salaires du personnel administratif

Le système doit générer automatiquement les fiches de paie.

Ne pas demander à la gestionnaire de créer manuellement les fiches.

Lorsqu'un utilisateur STAFF est créé :

* informaticien ;
* surveillant ;
* directeur des études ;
* secrétaire ;
* secrétaire adjointe ;
* gestionnaire ;
* gardien ;

le système doit disposer d'un champ :

salaire

Le système prépare automatiquement les fiches de paiement.

La gestionnaire :

* vérifie ;
* corrige si nécessaire ;
* valide ;
* paie.

Les fiches doivent rester éditables.

---

## Honoraires enseignants

Ne jamais mélanger :

* salaires staff ;
* honoraires enseignants.

Lors de la création d'un enseignant :

ajouter :

tarif_horaire

Le système doit :

* récupérer les heures validées ;
* calculer automatiquement les honoraires ;
* préparer automatiquement la fiche de paiement.

Formule :

heures_validées × tarif_horaire

La gestionnaire :

* contrôle ;
* corrige si nécessaire ;
* valide ;
* paie.

---

## Rapports

Les rapports doivent être :

* journaliers ;
* hebdomadaires ;
* mensuels ;
* personnalisés.

Format prioritaire :

tableaux de type Excel.

Les rapports doivent détailler :

* admissions ;
* inscriptions ;
* paiements ;
* dons ;
* ventes boutique ;
* dépenses ;
* salaires ;
* honoraires ;
* résultat net.

---

## Clôture mensuelle

Chaque fin de mois :

1. Vérification des opérations
2. Vérification des paiements
3. Vérification des salaires
4. Vérification des honoraires
5. Génération du bilan
6. Versement bancaire
7. Archivage
8. Clôture

Les données ne doivent jamais être supprimées.

Le système doit créer des archives consultables.

Les indicateurs repartent à zéro pour la nouvelle période.

L'historique reste disponible.

---

## Versements bancaires

Le système doit gérer :

* banque ;
* référence ;
* date ;
* montant ;
* justificatif ;
* commentaire.

Le DG doit voir les versements reçus par annexe.

---

## Boutique

Objectif :

Créer un système complet de commande et retrait.

Workflow :

Etudiant :
Commande → Paiement → Reçu PDF

Gestionnaire :
Notification → Préparation → Validation → Livraison

Le système doit :

* gérer les stocks ;
* générer les reçus ;
* historiser les retraits ;
* tracer les mouvements financiers.

---

## Intégration Frontend

Le backend existe déjà.

Avant toute modification du frontend :

* vérifier que les endpoints existent ;
* vérifier les services existants ;
* vérifier les modèles existants ;
* vérifier les vues HTMX existantes.

Adapter la maquette au backend.

Ne jamais reconstruire un backend déjà présent sans analyse.

---

## Validation obligatoire

Après chaque développement :

Tests backend :

* modèles ;
* services ;
* permissions ;
* filtrage annexe ;
* calculs financiers ;
* génération des rapports.

Tests frontend :

* affichage ;
* HTMX ;
* responsive ;
* boutons ;
* formulaires ;
* workflows.

Aucune fonctionnalité ne doit être considérée terminée sans validation backend et frontend.

---

## Session du 31/05/2026 — Dons dans rapport Excel + Liste commandes boutique étudiant

### Résumé

**1. Rapport financier Excel — Ajout des dons**
- `accounts/services/excel_reports.py` : requête `report_donations` (filtre `SOURCE_DONATION`), ligne "Dons / Donations" dans le détail + résumé, `donation_revenue` intégrée dans `total_revenue` et `net_result`
- Variables `expenses_paid` et `total_revenue` extraites pour supprimer les doublons de requêtes

**2. Liste commandes boutique étudiant**
- Vue `portal/student/views.py:shop_orders_partial()` — 50 dernières commandes de l'étudiant
- URL `partials/shop-orders/` nommée `portal_student:shop_orders_partial`
- Template `templates/portal/student/partials/shop_orders_student.html` (cartès statut + total + lien détail)
- Nav item "Boutique" (icône `shopping-bag`) dans `dashboard.js`
- Section HTMX lazy-load dans `dashboard.html`

### Fichiers modifiés
- `accounts/services/excel_reports.py` — ajout donation revenue
- `portal/student/views.py` — ajout vue `shop_orders_partial`
- `portal/student/urls.py` — ajout route `shop_orders_partial`
- `templates/portal/student/partials/shop_orders_student.html` — nouveau fichier
- `static/portal/student/dashboard.js` — nav item + sectionMeta + ensureSectionLoaded
- `templates/portal/student/dashboard.html` — section block boutique
- `AUDIT_GESTIONNAIRE.md` — marqué comme fait
