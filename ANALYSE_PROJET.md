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
