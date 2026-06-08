# Audit de Sécurité — ESFE Core

**Date :** 07/06/2026  
**Projet :** ESFE Core — Django 6.0 / Python 3.14  
**Auteur :** Analyse automatique (open code)

---

## Résumé exécutif

| Niveau | Nombre |
|--------|--------|
| 🔴 Critique | 4 |
| 🟠 Haute | 5 |
| 🟡 Moyenne | 4 |

**Points positifs :**
- Aucune injection SQL (pas de `raw()`, `extra()`, `cursor.execute`)
- Aucun `@csrf_exempt` — protection CSRF active partout
- Aucun `eval()` / `exec()` / `pickle`
- Dashboard gestionnaire bien sécurisé avec `@manager_required`
- Vues superadmin/superuser protégées
- Transactions `select_for_update()` utilisées correctement dans paiements
- `PaymentCorrection` immutable — audit trail complet
- Filtrage par annexe bien implémenté (branch scoping)

---

# 🔴 CRITIQUES

## C-1 : SECRET_KEY par défaut et DEBUG=True par défaut

**Fichier :** `config/settings.py`, lignes 36-37

```python
SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-key-change-me")
DEBUG = env_bool("DEBUG", True)
```

**Risque :** Si le fichier `.env` est absent ou que la variable `SECRET_KEY` n'est pas définie, Django utilise `dev-insecure-key-change-me`. Cela permet :
- La forge de sessions (signature de cookies)
- La prédiction de tokens CSRF
- Le contournement de signatures cryptographiques

`DEBUG` par défaut à `True` expose en production :
- Les stack traces complètes avec variables d'environnement
- Les requêtes SQL exécutées
- Le chemin complet du projet sur le serveur

**Correctif :**
```python
# Remplacer ligne 36 par :
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured("SECRET_KEY must be set in .env")

# Remplacer ligne 37 par :
DEBUG = env_bool("DEBUG", False)
```

---

## C-2 : Vues paiements sans authentification

**Fichier :** `payments/views.py`, lignes 52-411

Les vues suivantes n'ont **aucun décorateur d'authentification** (`@login_required`, `@permission_required`) :

| Ligne | Fonction | Action |
|-------|----------|--------|
| 52 | `student_initiate_payment` | Initie un paiement en base |
| 227 | `verify_agent` | Vérifie un agent de paiement |
| 283 | `initiate_cash_session` | Crée une session de caisse |
| 312 | `receipt_public_detail` | Affiche les détails d'un reçu |
| 328 | `receipt_pdf` | Télécharge un reçu PDF |
| 342 | `agents_list` | Liste les agents avec leurs codes |
| 360 | `payment_status` | Statut financier en temps réel (JSON) |
| 388 | `refresh_finance` | HTML partiel avec état financier complet |

**Risque :** Un attaquant non authentifié peut :
1. Deviner ou énumérer des numéros de reçu (séquentiels)
2. Télécharger des reçus PDF avec nom étudiant, montant, méthode
3. Lister tous les agents de paiement
4. Créer des paiements
5. Surveiller le statut financier de n'importe quelle inscription

**Correctif :** Ajouter `@login_required` sur toutes ces vues. Pour les reçus publics, implémenter des URLs signées ou vérifier que l'utilisateur est le propriétaire :
```python
@login_required
def receipt_public_detail(request, receipt_number):
    payment = get_object_or_404(Payment, receipt_number=receipt_number, status="validated")
    # Vérifier que l'utilisateur a droit à ce reçu
    if not request.user.is_staff and payment.inscription.student.user != request.user:
        raise Http404()
```

---

## C-3 : Reçus téléchargeables sans authentification

**Fichier :** `payments/views.py`, lignes 312-334

```python
def receipt_public_detail(request, receipt_number):
    payment = get_object_or_404(Payment, receipt_number=receipt_number, status="validated")

def receipt_pdf(request, receipt_number):
    payment = get_object_or_404(Payment, receipt_number=receipt_number, status="validated")
    return FileResponse(payment.receipt_pdf.open("rb"), content_type="application/pdf")
```

**Risque :** Les numéros de reçu sont prévisibles. Sans authentification ni vérification de propriété, n'importe qui peut télécharger le reçu PDF de n'importe quel paiement validé.

**Correctif :** Voir C-2 ci-dessus. Ajouter `@login_required` + vérification de propriété.

---

## C-4 : API agents de paiement publique

**Fichier :** `payments/views.py`, lignes 342-352

```python
@require_GET
def agents_list(request):
    agents = PaymentAgent.objects.select_related("user").filter(is_active=True)
    return JsonResponse({
        "agents": [{"id": a.id, "name": a.user.get_full_name(), "code": a.agent_code} for a in agents]
    })
```

**Risque :** Les codes d'agents (`agent_code`) sont utilisés pour vérifier les paiements en espèce. Les exposer publiquement permet :
- Usurpation d'identité d'agent
- Ingénierie sociale
- Contournement des vérifications de paiement

**Correctif :** Ajouter `@login_required` et ne pas exposer `agent_code` dans la réponse :
```python
@require_GET
@login_required
def agents_list(request):
    agents = PaymentAgent.objects.select_related("user").filter(is_active=True)
    return JsonResponse({
        "agents": [{"id": a.id, "name": a.user.get_full_name()} for a in agents]
    })
```

---

# 🟠 HAUTES

## H-1 : Mot de passe en clair envoyé par email

**Fichier :** `students/services/email.py`, lignes 25-26  
**Déclenché depuis :** `payments/models.py`, lignes 392-396

**Risque :** Le mot de passe généré pour l'étudiant est transmis en clair dans l'email de bienvenue. Un email intercepté (boîte compromise, relais SMTP non chiffré) expose les identifiants.

**Correctif :** Ne pas envoyer le mot de passe par email. À la place :
1. Créer un token à usage unique
2. Envoyer un lien de réinitialisation de mot de passe `https://domaine/accounts/reset/<token>/`
3. L'étudiant choisit son mot de passe lui-même

---

## H-2 : Aucun rate-limiting sur le login

**Fichier :** `accounts/auth_views.py`, lignes 25-33

```python
class PortalLoginView(auth_views.LoginView):
    template_name = "registration/login.html"
    authentication_form = PortalAuthenticationForm
```

**Risque :** Aucune limitation du nombre de tentatives. Brute-force illimité possible.

**Correctif :** Installer et configurer `django-axes` :
```bash
pip install django-axes
```
```python
# settings.py
INSTALLED_APPS.append("axes")
MIDDLEWARE.append("axes.middleware.AxesMiddleware")
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
```

---

## H-3 : Endpoint debug `/erreurs/*` accessible publiquement

**Fichier :** `core/views.py`, lignes 667-677 + `core/urls.py`, ligne 38

```python
# core/urls.py
path("erreurs/<int:error_code>/", views.preview_error_page, name="error_page_preview"),

# core/views.py
def preview_error_page(request, error_code):
    """Apercu rapide des pages d'erreur pour validation visuelle."""
    if error_code == 500:
        return custom_500(request)
    # ...
```

**Risque :** Accessible sans authentification. Permet de sonder la configuration erreur du site.

**Correctif :** Protéger par `if settings.DEBUG:` dans les URLs :
```python
if settings.DEBUG:
    urlpatterns.append(path("erreurs/<int:error_code>/", views.preview_error_page))
```

Ou ajouter un décorateur :
```python
@user_passes_test(lambda u: u.is_staff)
def preview_error_page(request, error_code):
```

---

## H-4 : Envoi du mot de passe en clair (email)

Suite de H-1. Même risque, lié à la création de compte étudiant lors de l'inscription.

**Correctif :** Remplacer l'envoi de mot de passe en clair par un workflow de réinitialisation.

---

## H-5 : Configuration sessions manquante

**Fichier :** `config/settings.py`

Les paramètres suivants ne sont pas définis explicitement :

| Paramètre | Valeur par défaut Django | Recommandé |
|-----------|--------------------------|------------|
| `SESSION_COOKIE_HTTPONLY` | True (explicite) | `True` |
| `SESSION_COOKIE_SAMESITE` | `'Lax'` | `'Lax'` |
| `SESSION_COOKIE_AGE` | 1209600 (2 semaines) | `28800` (8h) |
| `SESSION_EXPIRE_AT_BROWSER_CLOSE` | False | `True` |

**Risque :** Sessions persistantes de 2 semaines. Sur un poste partagé, l'utilisateur suivant peut reprendre la session.

**Correctif :**
```python
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 28800  # 8 heures
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
```

---

# 🟡 MOYENNES

## M-1 : Données POST intégralement loggées

**Fichier :** `payments/views.py`, lignes 98-103

```python
logger.warning(
    "Formulaire paiement invalide: token=%s data=%s errors=%s",
    token,
    dict(request.POST),  # LOGGE TOUT
    form.errors.get_json_data(),
)
```

**Correctif :** Logger uniquement les champs non sensibles :
```python
safe_data = {k: v for k, v in request.POST.items() if k not in {"verification_code"}}
```

---

## M-2 : Validation fichier par extension uniquement

**Fichier :** `portal/services/teacher_dashboard_service.py`, lignes 301-315

```python
extension = Path(uploaded_file.name or "").suffix.lower()
```

**Correctif :** Vérifier le MIME type réel avec `python-magic`.

---

## M-3 : Catch-all 404 masque les scanners

**Fichier :** `config/urls.py`, lignes 78-79

```python
urlpatterns += [
    re_path(r"^(?P<unmatched_path>.*)$", core_views.fallback_404, name="fallback_404"),
]
```

**Correctif :** Supprimer le catch-all et utiliser le `handler404` standard. Ou retourner un vrai statut 404 HTTP.

---

## M-4 : PII dans les logs

**Fichier :** `accounts/signals.py`, lignes 26, 40, 110-111, 162-163

Les noms d'utilisateurs et emails sont loggés.

**Correctif :** Logger avec des identifiants anonymes ou tronqués.

---

# Secrets exposés

**Fichier :** `.env` à la racine

Le fichier `.env` est correctement gitignoré (`.gitignore` ligne 58), mais il contient des secrets en clair :

| Secret | Valeur | Risque |
|--------|--------|--------|
| MOT_DE_PASSE_GMAIL | `jrijhletunyxrwko` | Ancien compte Gmail — à révoquer |
| BREVO_SMTP_PASSWORD | `PYpKMhszTbxG5dwc` | **Actif** — changer d'urgence |
| DB_PASSWORD | `2026` | Mot de passe très faible |
| SECRET_KEY | `django-insecure-change-this-key-later` | Clé de test — à générer |

**Actions :**
1. Générer un nouveau `SECRET_KEY` fort :
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(50))"
   ```
2. Changer le mot de passe Brevo SMTP depuis le dashboard Brevo
3. Changer le mot de passe PostgreSQL (`2026` → mot de passe fort)
4. Révoquer l'ancien mot de passe Gmail

---

# Plan de correction recommandé

## Phase 1 — CRITIQUE (avant déploiement)

| Ordre | Tâche | Fichiers |
|-------|-------|----------|
| 1 | Générer SECRET_KEY fort, DEBUG=False par défaut | `.env`, `config/settings.py` |
| 2 | Ajouter `@login_required` aux vues paiements | `payments/views.py` |
| 3 | Ajouter `@login_required` aux endpoints reçus | `payments/views.py` |
| 4 | Ajouter `@login_required` à l'API agents | `payments/views.py` |

## Phase 2 — HAUTE (avant déploiement)

| Ordre | Tâche | Fichiers |
|-------|-------|----------|
| 5 | Workflow reset password au lieu d'email en clair | `students/services/email.py` |
| 6 | Installer django-axes pour rate-limiting | `config/settings.py` |
| 7 | Protéger endpoint `/erreurs/*` par DEBUG | `core/urls.py` |
| 8 | Configurer sessions explicitement | `config/settings.py` |

## Phase 3 — MOYENNE + Propreté

| Ordre | Tâche |
|-------|-------|
| 9 | Nettoyer `dict(request.POST)` des logs |
| 10 | Renforcer validation fichiers |
| 11 | Revoir le catch-all 404 |
| 12 | Anonymiser les logs |
| 13 | Changer mot de passe Brevo + DB + SECRET_KEY |
| 14 | Nettoyer le `.env` des anciens credentials commentés |
