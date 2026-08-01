# Analyse & Notation — ESFE Core

**Projet :** Django 6.0 / Python 3.14 — ERP scolaire pour ESFE (Mali)  
**Date :** 02/06/2026  
**Note globale :** 13.5 / 20

---

## 1. Structure générale — 15/20

**~19 apps Django** réparties en groupes cohérents :

| Groupe | Apps |
|--------|------|
| Infrastructure | `core`, `ui` |
| Communication | `communication` |
| Auth & Rôles | `accounts`, `portal` |
| Gestion courante | `secretary`, `students`, `superadmin` |
| Cœur métier | `admissions`, `inscriptions`, `payments`, `academic_cycle`, `academics` |
| Contenu & Marketing | `blog`, `news`, `community`, `formations`, `branches`, `marketing` |
| E-commerce | `shop` |

**✅ Points positifs :**
- Séparation claire des responsabilités par app
- Dashboards isolés dans leur propre sous-dossier (`accounts/dashboards/`)
- Services bien séparés des vues (`accounts/services/`, `payments/services/`, etc.)

**❌ Points négatifs :**
- `htmx_manager.py` : **1553 lignes** monolithiques
- `manager_dashboard.py` : **914 lignes** avec une fonction `_manager_context()` surchargée (>400 variables)
- Certains modèles très longs (`accounts/models.py` : 835 lignes)
- Pas de README.md à la racine

---

## 2. Qualité du code — 11/20

**✅ Points positifs :**
- Conventions Django globalement respectées (`get_user_model()`, `on_delete`, `Meta` classes)
- Nommage clair des champs et modèles
- `@property` bien utilisée pour les calculs financiers
- Constantes de classe pour les statuts (`VALID_TRANSITIONS`)

**❌ Points négatifs :**
- **Aucune annotation de type** dans la quasi-totalité du code
- Pas de linter configuré (ruff, flake8)
- Pas de type checker (mypy, pyright)
- Mélange français/anglais dans les chaînes
- Quelques incohérences dans `settings.py` (syntaxe, commentaires)

---

## 3. Architecture — 16/20

**Couches bien identifiées :**

| Couche | Emplacement |
|--------|-------------|
| Modèles | `*/models.py` |
| Vues | `*/views.py`, `*/dashboards/*.py` |
| Services | `*/services/*.py` |
| Formulaires | `*/forms.py` |
| Templates | `*/templates/*` |

**✅ Points positifs :**
- **Système de permissions centralisé** : `accounts/access.py` (477 lignes) avec matrice d'accès, mapping des rôles, détection d'annexe — très mature
- **Filtrage par annexe systématique** dans toutes les requêtes gestionnaire
- Services dédiés : `excel_reports.py`, `manager_intelligence.py`, `accounting_documents.py`
- `transaction.atomic()` et `select_for_update()` pour l'intégrité financière
- Machine à états formelle (`VALID_TRANSITIONS`, `refresh_status()`)
- Architecture ASGI + WSGI avec `ClientDisconnectSafeASGIApp`

**❌ Points négatifs :**
- Trop de logique dans les vues (notamment `_manager_context()`)
- Duplication de code entre vues et services
- Pas de `signals.py` dédié
- Fichiers trop longs et peu modulaires

---

## 4. Frontend — 12/20

**Stack :** Tailwind v3 (PostCSS), HTMX, Django Components, Alpine.js, Font Awesome

**✅ Points positifs :**
- Design system cohérent avec couleurs personnalisées
- HTMX bien intégré (modals, row updates, toasts, lazy-loading)
- 37 composants Django dans `ui/components/`
- SEO complet (Open Graph, Twitter Cards, Schema.org JSON-LD)
- Dashboard gestionnaire avec CSS très élaboré (variables, gradients, transitions)

**❌ Points négatifs :**
- **CSS inline massif** dans le template du dashboard (100+ lignes dans `<style>`)
- Dépendances CDN externes (Font Awesome, AOS, Google Fonts)
- Template `manager_dashboard.html` : **1510 lignes**
- Alpine.js minimal, pas de framework JS structuré

---

## 5. Tests — 10/20

**✅ Points positifs :**
- `accounts/tests.py` : **2472 lignes**, très complet (permissions, flux, régressions)
- Utilisation de `@patch` pour mocker les services externes
- Tests de régression identifiés
- `settings_test_local.py` bien pensé (SQLite, InMemoryChannelLayer)

**❌ Points négatifs :**
- **Couverture très inégale** : `formations/tests.py` = 3 lignes (vide)
- Pas de tests pour les services Excel, documents comptables, `manager_intelligence.py`
- Pas de `factory_boy` / `model_bakery` — tests verbeux
- **Pas de CI/CD**
- Pas de métriques de couverture (`coverage.py`)

---

## 6. Sécurité — 16/20

**✅ Points positifs :**
- CSRF, X-Frame-Options, HSTS, Secure cookies, Content-Type nosniff
- Permissions robustes avec `can_access()` et décorateur `manager_required`
- Filtrage par annexe
- Validation métier (`clean()`, `full_clean()`)
- Soft delete sur `Candidature`
- Transactions atomiques pour les opérations financières

**❌ Points négatifs :**
- `SECRET_KEY` avec fallback `"dev-insecure-key-change-me"`
- `DEBUG = True` par défaut
- Pas de rate limiting
- Pas de `CSRF_COOKIE_HTTPONLY`
- `.env` contient des secrets réels

---

## 7. Documentation — 14/20

**✅ Points positifs :**
- `AGENTS.md` très complet (383 lignes)
- `ACCESS_MAPPING.md` (133 lignes)
- `AUDIT_GESTIONNAIRE.md` (529 lignes)
- Multiples documents d'architecture et blueprints
- Docstrings sur les modèles et champs

**❌ Points négatifs :**
- **Pas de README.md** à la racine
- ~20 fichiers `.txt` éparpillés à la racine (non organisés)
- Certains documents sont des notes de travail

---

## 8. Complexité métier — 17/20

**✅ Points positifs :**
- Modélisation très riche et réaliste d'un ERP scolaire
- Traçabilité complète : `FinancialLog`, `StatusHistory`, `AcademicAuditLog`
- Workflows métier avec transitions validées
- Contraintes d'intégrité et indexation bien pensées
- Système de paie complet (salaires staff + honoraires enseignants)
- Boutique avec stocks, commandes, sessions cash

**❌ Points négatifs :**
- Complexité parfois excessive (8 statuts Inscription, 9 AcademicReEnrollment)
- `is_valid` / `is_validated` redondants sur `CandidatureDocument`
- `StudentYearDecision` dans deux apps différentes (`students` et `academic_cycle`)

---

## Synthèse

### Points forts
1. Architecture de permissions centralisée et documentée
2. Filtrage par annexe systématique
3. Modélisation métier très complète
4. Traçabilité financière complète
5. Tests solides sur le module critique (`accounts`)
6. Services bien séparés des vues
7. HTMX bien intégré pour l'UX réactive

### Points faibles à corriger
1. **Dette technique** : découper `htmx_manager.py` (1553 lignes)
2. **Typage absent** : ajouter des annotations Python
3. **Couverture de tests inégale** : couvrir les apps sans tests
4. **Pas de CI/CD**
5. **Pas de linter/type checker** (ruff, mypy)
6. **CSS inline** dans le template dashboard
7. **Pas de README.md** à la racine
8. **Documentation éparpillée** dans des fichiers `.txt`

---

**Conclusion :** Projet fonctionnellement riche et solide, avec une excellente compréhension des besoins métier, mais qui nécessite un refactoring ciblé pour atteindre un niveau professionnel supérieur en qualité de code et pratiques d'ingénierie.

---

## AUDIT ET STABILISATION DU TUNNEL DE DÉCOUVERTE DES FORMATIONS

**Date de recette :** 16/07/2026
**Verdict final : PASS**

### Rôle fonctionnel

Le projet conserve deux parcours publics distincts :

- le catalogue classique `/formations/`, sa fiche détaillée et son formulaire de candidature historique ;
- le tunnel guidé `/admissions/`, utilisable pour découvrir les formations, sélectionner un campus et poursuivre vers une candidature.

Le tunnel offre désormais une entrée de découverte sans demander d'abord les données personnelles. Un lien partageable peut ouvrir directement l'étape de découverte : `/admissions/?step=3`. Il peut aussi présélectionner des données réelles, par exemple `/admissions/?step=3&branch=<slug-annexe>&formation=<slug-formation>`.

### Fichiers et routes concernés

Fichiers applicatifs modifiés :

- `admissions/views.py` ;
- `admissions/tests.py` ;
- `admissions/templates/admissions/tunnel.html` ;
- `admissions/templates/admissions/done.html` ;
- les fragments `step1.html`, `step2.html`, `step3.html`, `step3_documents.html`, `formation_options.html` et `hero_admission.html` ;
- `tailwind.config.js` et le CSS compilé `static/public/css/main.css` ;
- `_audit/tunnel_visual_check.py` pour la recette navigateur reproductible.

Routes auditées, conservées sans suppression ni fusion :

- `GET|POST /admissions/` ;
- `GET /admissions/partials/step3/formations/` ;
- `GET /admissions/partials/step3/documents/` ;
- `GET /admissions/done/<id>/` ;
- `GET|POST /admissions/s-inscrire/<slug>/` ;
- `GET /formations/` ;
- `GET /formations/<slug>/`.

### Source des données

Le tunnel lit les mêmes modèles métier que le catalogue et la candidature : `Programme`, `Cycle`, `Diploma`, `ProgrammeYear`, `Fee`, `RequiredDocument`, `ProgrammeRequiredDocument`, `Branch` et `AcademicYear`. Les titres, slugs, cycles, diplômes, durées, descriptions, illustrations, frais de première année, documents requis, annexes actives et année académique sont donc issus de la base.

Le modèle `Programme` ne possède pas de champ `is_published` distinct : `is_active` constitue actuellement le statut public effectif, comme dans le catalogue classique.

La table historique de disponibilité « programme × annexe » a été supprimée par une migration antérieure. En l'absence de cette relation métier, toutes les formations actives sont proposées dans chaque annexe active acceptant l'inscription en ligne. Aucun modèle ou workflow métier n'a été recréé arbitrairement pendant cette stabilisation.

### Incohérences détectées

- aucune conservation des choix ou informations après rafraîchissement ;
- aucune présélection fiable par URL ;
- année d'entrée calculée depuis une valeur cliente falsifiable plutôt que depuis le cycle réel du programme ;
- possibilité d'envoyer un genre absent puis d'enregistrer implicitement « masculin » ;
- email, date de naissance et pièces jointes insuffisamment validés côté serveur ;
- libellés de programme et d'annexe envoyés par le navigateur au lieu d'être systématiquement recalés sur la base ;
- cartes de formation limitées au titre, à la durée et au coût ;
- plusieurs requêtes HTMX concurrentes possibles lors d'une même sélection ;
- image héro inexistante (`/static/images/hero_institution.png`) ;
- panneau annexe vide lorsqu'aucune image n'était configurée ;
- textes français non accentués dans plusieurs zones importantes.

### Problèmes visuels et de navigation corrigés

- cartes enrichies avec cycle, diplôme, description, durée, frais formatés, image ou repli visuel ;
- état sélectionné explicite et boutons accessibles ;
- repli photographique pour les annexes sans image ;
- image héro corrigée et textes principaux révisés ;
- choix du genre ajouté à l'interface ;
- bouton « Découvrir d'abord les formations » ajouté au tunnel ;
- prise en charge de l'accès direct à l'étape 3 et des paramètres `branch`, `annexe`, `branch_id`, `formation` et `formation_slug` ;
- brouillon conservé dans `sessionStorage` pendant l'onglet courant, puis supprimé après une candidature réussie ;
- suppression des déclenchements HTMX redondants ;
- aucune largeur horizontale excédentaire à 390 px, 820 px et 1440 px.

### Corrections de fiabilité

- validation serveur de l'email, de la date de naissance, du genre, du niveau et de l'identifiant d'annexe ;
- rejet des formations inactives, annexes inactives et cycles incompatibles ;
- calcul de `entry_year` depuis le cycle réel du programme ;
- libellés de formation et d'annexe remplacés par les valeurs de la base avant enregistrement ;
- formats de documents limités à PDF, JPG, PNG, DOC et DOCX, avec une taille maximale de 10 Mo par fichier ;
- journalisation interne des erreurs techniques inattendues ;
- aucune migration et aucune modification des modèles métier.

### Tests exécutés et résultats

- `python manage.py test --settings=config.settings_session_qa --keepdb --noinput admissions formations` : **13/13 PASS** ;
- `python manage.py check --settings=config.settings_test_local` : **PASS**, aucune anomalie ;
- `npm run build:css` : **PASS** ;
- recette Playwright `_audit/tunnel_visual_check.py` : **PASS** ;
- tunnel direct : HTTP 200 sur mobile, tablette et ordinateur ;
- HTMX documents et formations : HTTP 200 ;
- restauration du brouillon après rafraîchissement : **PASS** ;
- catalogue classique `/formations/` : HTTP 200 et formation visible ;
- fiche classique `/formations/<slug>/` : HTTP 200 et bonne formation visible ;
- erreurs JavaScript/console pendant la recette finale : **0**.

### Captures et preuves

- mobile 390 × 844 : `_audit/tunnel_mobile.png` ;
- tablette 820 × 1180 : `_audit/tunnel_tablet.png` ;
- ordinateur 1440 × 1000 : `_audit/tunnel_desktop.png` ;
- script reproductible : `_audit/tunnel_visual_check.py`.

### Risques de régression résiduels

- si l'offre de formations devient différente selon l'annexe, une relation métier explicite devra être réintroduite puis appliquée simultanément au chargement HTMX et à la validation POST ;
- les fichiers sélectionnés ne peuvent pas être restaurés après rafraîchissement pour des raisons de sécurité du navigateur ; les autres données du brouillon sont restaurées ;
- les cycles guidés restent volontairement limités à Licence et Master, conformément aux données et au workflow actuel du tunnel.

### Conclusion

Les deux systèmes sont conservés. Le tunnel est stabilisé et perfectionné sans remplacer ni restructurer le catalogue classique. Les données affichées proviennent des modèles réels, la sélection conduit à la bonne formation, la candidature est contrôlée côté serveur et le parcours classique reste fonctionnel.
