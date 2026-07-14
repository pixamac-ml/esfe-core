# Spécification complète — Système de coupons ESFé Core

Document unique, consolidé, destiné à être exécuté par Claude Code. Il remplace et
fusionne les trois documents précédents (`PLAN_COUPONS_INTEGRATION.md`,
`PLAN_COUPONS_ADDENDUM_NOTIFICATIONS.md`, `PLAN_COUPONS_ADDENDUM_2_DECISIONS.md`) —
ceux-ci peuvent être archivés ou supprimés, tout leur contenu utile est repris ici.

---

## 0. À retenir avant toute chose (pour ne pas se perdre)

**Deux acteurs, deux actions, jamais interchangeables :**

| Acteur | Application | Action | Ne fait JAMAIS |
|---|---|---|---|
| **Directeur Général (DG)** | `portal/dg/` | **Crée** le coupon (code, réduction, annexe(s), formation(s), durée de validité) et le communique à l'étudiant | N'applique jamais lui-même un coupon sur une inscription |
| **Gestionnaire** | `accounts` (dashboard manager) | **Applique** le coupon reçu par l'étudiant sur son inscription, avant tout paiement | Ne crée jamais de coupon |

Le **Super Admin** (`superadmin`, app de génération du site web) ne fait ni l'un ni
l'autre : il peut seulement *voir* qu'un coupon existe et a été appliqué, en lecture
seule, via `/admin/` ou un affichage passif.

Toute ambiguïté rencontrée pendant l'implémentation doit être résolue en revenant à ce
tableau : si une action ressemble à de la création → c'est le DG (`portal/dg/`) ; si
elle ressemble à de l'application sur un dossier étudiant → c'est la gestionnaire
(`accounts`).

---

## 1. Ce qui est déjà livré et ne doit PAS être réécrit

Le cœur métier existe déjà, dans l'app `coupons/` à la racine du projet, et fonctionne :

- `coupons/models.py` : `Coupon` (définition de la réduction) et `CouponRedemption`
  (journal d'audit immuable de chaque application)
- `coupons/services/validation.py` : `get_valid_coupon(code, inscription)` — validation
  pure, ne modifie rien
- `coupons/services/application.py` : `apply_coupon(code, inscription_id, actor)` —
  applique réellement la réduction, transaction atomique, verrouillage
  (`select_for_update`), écrit dans `CouponRedemption` + `FinancialLog`
- `coupons/admin.py` : `CouponRedemption` est en lecture seule dans l'admin (jamais
  modifiable/supprimable, comme `PaymentCorrection`)
- `payments/models.py::FinancialLog` : choix `ACTION_COUPON_APPLIED` déjà ajouté

Ce qui reste à faire, c'est uniquement le **branchement** (vues, routes, formulaires,
templates, une extension du modèle) décrit ci-dessous.

---

## 2. Modifications à apporter au modèle `Coupon` (migration nécessaire)

Un coupon cible une formation **disponible dans une annexe précise** — jamais national,
car les formations ne sont pas les mêmes partout.

Point d'architecture important : `formations.Programme` n'a **pas** de lien direct vers
`branches.Branch`. La disponibilité réelle d'une formation dans une annexe se déduit de
`academics.AcademicClass` (`branch` + `programme` + `is_active=True`) — c'est le
mécanisme déjà utilisé ailleurs dans le projet (`academics/services/surveillance.py`,
`portal/services/director/transfer_workflow_service.py`).

*(Remarque : une migration orpheline, `formations/migrations/0002_programavailability.py`,
avait introduit un modèle `ProgramAvailability` pour ce même besoin, abandonné depuis —
il n'existe plus dans `formations/models.py`. Ne pas le réutiliser. `AcademicClass` est
la source de vérité actuelle.)*

### 2.1 Champ à ajouter
```
branches = models.ManyToManyField(Branch, blank=True, related_name="coupons")
```
(vide = toutes les annexes — même convention que `programmes`, déjà vide = toutes les
formations)

### 2.2 Méthode à étendre
`Coupon.applies_to()` doit vérifier les deux dimensions, pas seulement la formation :
```
def applies_to(self, *, branch, programme):
    branch_ok = not self.branches.exists() or self.branches.filter(pk=branch.pk).exists()
    programme_ok = not self.programmes.exists() or self.programmes.filter(pk=programme.pk).exists()
    return branch_ok and programme_ok
```

### 2.3 Impact sur la validation
`coupons/services/validation.py::get_valid_coupon` doit appeler :
```
coupon.applies_to(branch=inscription.candidature.branch, programme=inscription.candidature.programme)
```
au lieu de l'appel actuel à un seul argument.

---

## 3. Côté Directeur Général — app `portal`

### 3.1 Fichiers à créer/modifier
- `portal/dg/forms.py` → ajouter `DgCouponForm` (même style que `DgRecruitmentForm`
  déjà présent dans ce fichier)
- `portal/dg/coupons_service.py` **(nouveau)** → `list_coupons()`, `create_coupon(actor, form)`,
  `toggle_coupon(actor, coupon_id)`, à l'image de `portal/dg/actions_service.py`
- `portal/views/views.py` → deux nouvelles vues, `dg_coupon_create` et `dg_coupon_toggle`,
  suivant exactement le pattern déjà en place pour `dg_recruit_staff` (~ligne 3488) et
  `dg_action` (~ligne 3502) : même vérification de position
  (`get_user_position(request.user) not in {"executive_director", "deputy_executive_director"}`
  → `HttpResponseForbidden`)
- `portal/urls.py` → ajouter :
  - `path("dg/coupons/create/", dg_coupon_create, name="dg_coupon_create")`
  - `path("dg/coupons/toggle/", dg_coupon_toggle, name="dg_coupon_toggle")`
  - dans `dg_section`, ajouter `"coupons": "portal/dg/partials/coupons/list.html"` au
    `template_map` existant (~ligne 3433), pour que l'onglet Coupons s'affiche comme les
    autres sections DG (kpis, finance, rh...)
- Templates à créer :
  - `portal/templates/portal/dg/partials/coupons/list.html` (liste des coupons, statut,
    compteur d'utilisation — sur le modèle de `partials/alerts/priority_table.html`)
  - `portal/templates/portal/dg/modals/coupon_form.html` (formulaire de création — sur
    le modèle de `modals/recruitment.html`)

### 3.2 Contenu du formulaire `DgCouponForm`
Champs, avec leurs règles métier :

| Champ | Règle |
|---|---|
| `code` | obligatoire, unique |
| `label` | description interne obligatoire |
| `discount_type` | pourcentage ou montant fixe |
| `value` | 1-100 si pourcentage, >0 si montant fixe |
| `branches` | sélection d'annexe(s) — voir cascade ci-dessous |
| `programmes` | filtré dynamiquement selon l'annexe choisie |
| `valid_from` | par défaut maintenant |
| `valid_until` | **obligatoire dans ce formulaire** (le champ modèle reste `null=True` pour ne pas bloquer un usage administratif exceptionnel, mais le formulaire DG l'impose — cohérent avec "un coupon ne doit pas trop durer") ; avertissement (non bloquant) si l'écart dépasse ~30 jours |
| `max_redemptions` | valeur initiale **1** (usage unique par défaut, confirmé) — le DG l'augmente explicitement s'il veut une campagne à plusieurs bénéficiaires |

Aucune logique de validation nouvelle à écrire pour `value`/dates : `Coupon.clean()`
la fait déjà. Le formulaire ne fait qu'ajouter les contraintes propres à l'écran DG
(`valid_until` requis, `max_redemptions` pré-rempli).

### 3.3 Sélection en cascade annexe → formation
1. Le DG choisit une ou plusieurs annexes.
2. Le champ "formations" se limite dynamiquement à celles ayant au moins un
   `AcademicClass` actif dans l'annexe (ou les annexes) sélectionnée(s) :
   `AcademicClass.objects.filter(branch_id__in=..., is_active=True).values_list("programme_id", "programme__title").distinct()`
3. Techniquement : un petit endpoint HTMX de rafraîchissement dans `portal/dg/`,
   déclenché au changement du champ annexe (`hx-get` + `hx-target` sur le select
   formations) — même famille que `dg_section`/`dg_modal` déjà existants.

### 3.4 Désactivation
`dg_coupon_toggle` bascule `coupon.is_active`. Pas de suppression possible (cohérent
avec l'immuabilité déjà choisie pour tout objet qui trace de l'argent).

---

## 4. Côté Gestionnaire — app `accounts`

Deux moments distincts où la gestionnaire peut appliquer le coupon reçu par l'étudiant.

### 4.1 Moment A — à la création de l'inscription (cas normal : l'étudiant arrive avec son code)

Fichier : `accounts/dashboards/htmx_inscriptions.py`, fonction `inscription_create`
(actuellement lignes 67-134).

Flux actuel : `positioning modal → POST inscription_create → create_inscription_from_candidature(...)`

Modifications :
1. Ajouter un champ `coupon_code` (facultatif) dans
   `accounts/templates/accounts/dashboard/partials/academic_positioning_body.html`.
2. Dans `inscription_create`, après `create_inscription_from_candidature(...)` réussi,
   si `coupon_code` est renseigné : appeler
   `coupons.services.application.apply_coupon(code=..., inscription_id=inscription.id, actor=request.user)`
   dans un `try/except ValidationError`. En cas d'échec, **l'inscription déjà créée
   n'est pas annulée** (elle reste valide sans réduction) ; renvoyer un message
   d'avertissement HTMX distinct du message de succès.
3. Le message de succès HTMX doit refléter le montant réel après réduction
   (`inscription.amount_due` rafraîchi après `apply_coupon`), pas le montant brut.

Pourquoi après la création plutôt qu'avant : `create_inscription_from_candidature` fixe
`amount_due` à partir du barème (`get_positioning_fee_for_level`). Le coupon réduit ce
montant déjà calculé — c'est exactement ce que fait `apply_coupon`, sans toucher à
`inscriptions/services.py`.

### 4.2 Moment B — sur une inscription déjà créée mais pas encore payée (l'étudiant revient plus tard avec son code)

Fichier : même fichier, fonction `inscription_detail` (actuellement lignes 19-48), qui
rend `accounts/dashboard/partials/inscription_modal.html` — c'est la fiche/vue de
l'inscription (identifiée par son token) que la gestionnaire consulte pour traiter le
paiement.

Modifications :
1. Ajouter au contexte :
   ```
   "can_apply_coupon": inscription.amount_paid == 0
       and not hasattr(inscription, "coupon_redemption")
       and inscription.status not in [Inscription.STATUS_CANCELLED, Inscription.STATUS_EXPIRED],
   "existing_coupon_redemption": getattr(inscription, "coupon_redemption", None),
   ```
2. Nouvelle vue `inscription_apply_coupon`, décorée `@manager_required` +
   `@require_POST`, qui appelle `apply_coupon(...)`.
3. Route dans `accounts/urls.py`, à côté de `htmx_inscription_detail` (~ligne 397) :
   `path("htmx/manager/inscription/<int:pk>/apply-coupon/", inscription_apply_coupon, name="htmx_inscription_apply_coupon")`
4. Dans `inscription_modal.html`, ajouter le bloc conditionnel
   (`{% if can_apply_coupon %}` / `{% elif existing_coupon_redemption %}`) avec le
   formulaire de saisie du code, et sous le champ, une zone de prévisualisation en
   temps réel (voir section 5).

### 4.3 Permission
`manager_required` (déjà défini dans `accounts/dashboards/htmx_utils.py`) suffit — il
couvre déjà `staff_admin` (secrétariat, finance, admissions). Aucune nouvelle permission
Django à créer.

---

## 5. Vérification en temps réel avant application (confort + anti-erreur)

Le verrou de sécurité existe déjà côté serveur (`get_valid_coupon` refuse un code
inexistant, désactivé, expiré, hors quota, déjà utilisé sur cette inscription, ou hors
périmètre annexe/formation). Ce qui suit est une couche de confort visuel, pas une
sécurité supplémentaire.

- Nouvelle vue `coupon_preview` dans `accounts/dashboards/htmx_inscriptions.py` —
  `@manager_required` + `@require_GET`, paramètres `inscription_id` + `code`.
- Appelle `get_valid_coupon(code, inscription)` sans rien modifier (fonction de lecture
  pure).
- Rend un petit partiel : si valide → label, réduction calculée
  (`coupon.compute_discount(inscription.amount_due)`), nouveau montant simulé, en vert ;
  si invalide → message d'erreur exact (déjà rédigé clairement en français dans
  `get_valid_coupon`), en rouge.
- Déclenchement HTMX : `hx-trigger="keyup changed delay:400ms"` sur le champ code.
- Le bouton "Appliquer" reste désactivé tant que la prévisualisation n'a pas renvoyé un
  statut valide.
- Route à ajouter dans `accounts/urls.py`, à côté de `htmx_inscription_apply_coupon`.

---

## 6. Notification automatique DG → Gestionnaire

Le projet a déjà un système de notification complet et utilisé partout ailleurs
(`notifier/services/bus.py::NotificationBus`, table `NotificationMessage`, canaux
in-app + websocket + email — voir usages existants dans `secretary/services.py`,
`inscriptions/signals.py`, `academics/signals.py`). Ne pas créer de système parallèle :
brancher `coupons` dessus.

### 6.1 Déclenchement
Dans `portal/dg/coupons_service.py::create_coupon(actor, form)`, juste après
`Coupon.objects.create(...)`.

### 6.2 Résolution des destinataires
Utiliser `notifier/services/audience.py::resolve_platform_users`, déjà capable de
résoudre "tous les gestionnaires d'une ou plusieurs annexes" via :
- `role_tokens = ["secretary", "finance_manager", "payment_agent", "admissions", "branch_manager"]`
  (positions déjà cartographiées comme `staff_admin` dans `accounts/access.py`)
- `branch_ids` = les annexes du coupon (`coupon.branches.all()`, ou toutes les annexes
  actives si le coupon est laissé sans restriction d'annexe)

### 6.3 Appel type
```
NotificationBus.notify(
    recipient=<utilisateur résolu>,
    actor=dg_user,
    event_type="coupon_created",
    title=f"Nouveau coupon disponible : {coupon.code}",
    body=f"{coupon.label} — {coupon.get_discount_type_display()} de {coupon.value} "
         f"sur {', '.join(p.title for p in coupon.programmes.all()) or 'toutes les formations'}.",
    source_app="coupons",
    channels=(NotificationMessage.CHANNEL_IN_APP, NotificationMessage.CHANNEL_WEBSOCKET),
    metadata={"coupon_id": coupon.id, "coupon_code": coupon.code},
)
```
À boucler sur chaque utilisateur résolu (le bus notifie un destinataire à la fois, comme
partout ailleurs dans le projet).

### 6.4 Affichage
Rien à construire pour l'affichage générique : la cloche de notifications existante
(`notification_center`, basée sur la même table `NotificationMessage`) affichera
automatiquement "Nouveau coupon disponible" à la gestionnaire concernée.

En complément optionnel : un widget "Coupons actifs" sur l'accueil du dashboard
gestionnaire, dans `accounts/dashboards/htmx_widgets.py` (fichier qui centralise déjà
les petits widgets du dashboard).

---

## 7. Décision sur l'écran `superadmin` déjà posé précédemment (à corriger)

Un premier essai avait posé le bouton "Appliquer un coupon" dans
`superadmin/templates/superadmin/inscriptions/detail.html` — ce n'est pas le bon
endroit (`superadmin` génère le site web public, ce n'est pas le système de gestion
utilisé par la gestionnaire ou le DG).

**Action à faire** : dans `superadmin/inscriptions/detail.html`, remplacer le `<form>`
d'application par un affichage passif du statut du coupon (lecture seule — cohérent
avec "le superadmin doit pouvoir voir mais pas agir"). Supprimer la vue
`inscription_apply_coupon` de `superadmin/views.py` et sa route dans
`superadmin/urls.py` : elle ne doit plus être appelable depuis cet écran.

---

## 8. Traçabilité (déjà couverte — aucun ajout de modèle)

| Question | Réponse déjà couverte par le modèle existant |
|---|---|
| Qui a créé le coupon ? | `Coupon.created_by` |
| Qui l'a appliqué, sur quelle inscription ? | `CouponRedemption.applied_by`, `CouponRedemption.inscription` |
| Quand (création / application) ? | `Coupon.created_at`, `CouponRedemption.applied_at` |
| Montant avant / après réduction ? | `CouponRedemption.amount_before` / `amount_after` |
| Trace comptable centralisée ? | `FinancialLog` (action `coupon_applied`, `actor`, `metadata`) |

`apply_coupon()` modifie directement `Inscription.amount_due` : tout ce qui en dépend
déjà (reçu PDF, solde affiché, `Inscription.balance`, `Inscription.is_paid`) se met à
jour automatiquement — ce sont des propriétés calculées, pas des valeurs à dupliquer.

---

## 9. Dette technique identifiée en marge (à traiter séparément, plus tard)

Constat fait pendant cette analyse, à garder pour le futur chantier "un seul dashboard
gestionnaire unifié" déjà évoqué :

- La création d'inscription passe par un service canonique unique et déjà bien centralisé,
  `inscriptions/services.py::create_inscription_from_candidature`, utilisé dans la
  quasi-totalité des points d'entrée (`accounts/dashboards/htmx_admissions.py`,
  `htmx_inscriptions.py`, `accounts/dashboard_views.py`, `superadmin/views.py`,
  `admissions/admin.py`) — la logique métier elle-même n'est donc pas dupliquée, ce qui
  est une bonne nouvelle.
- En revanche, **l'écran** qui déclenche cette création existe en plusieurs exemplaires
  (au moins trois fichiers distincts). C'est exactement la duplication de dashboards à
  corriger plus tard. Conséquence immédiate pour ce chantier coupon : le champ
  `coupon_code` doit être ajouté aux écrans `accounts` concernés (section 4.1), pas à un
  seul — tant que les dashboards ne sont pas fusionnés, toute nouvelle fonctionnalité de
  saisie d'inscription doit être dupliquée manuellement.

---

## 10. Checklist d'implémentation (ordre recommandé, de bout en bout)

1. Migration `coupons` : ajouter `Coupon.branches` (M2M vers `branches.Branch`, blank=True)
2. `Coupon.applies_to()` : signature étendue à `(branch, programme)`
3. `coupons/services/validation.py::get_valid_coupon` : appel mis à jour avec les deux paramètres
4. `portal/dg/forms.py` → `DgCouponForm` (avec `valid_until` requis, `max_redemptions` initial = 1, cascade annexe→formation)
5. `portal/dg/coupons_service.py` → `list_coupons`, `create_coupon` (avec appel `NotificationBus.notify`), `toggle_coupon`
6. `portal/views/views.py` → `dg_coupon_create`, `dg_coupon_toggle`, + endpoint de rafraîchissement des formations par annexe
7. `portal/urls.py` → routes + entrée `"coupons"` dans `template_map` de `dg_section`
8. Templates DG : `partials/coupons/list.html`, `modals/coupon_form.html`
9. `accounts/dashboards/htmx_inscriptions.py` → modifier `inscription_create` (4.1), ajouter `inscription_apply_coupon` (4.2) et `coupon_preview` (5)
10. `accounts/urls.py` → routes correspondantes
11. Templates gestionnaire : `academic_positioning_body.html` (champ coupon_code), `inscription_modal.html` (bloc application + prévisualisation temps réel)
12. `superadmin` : appliquer la correction de la section 7 (retrait de l'action, affichage passif)
13. Widget optionnel "Coupons actifs" dans `accounts/dashboards/htmx_widgets.py`
14. Tests, en repartant de `accounts/test_manager_workflows.py` comme base :
    - création d'inscription avec coupon valide → montant réduit correct
    - coupon invalide / expiré / hors quota → message d'erreur clair, inscription quand même créée
    - coupon hors périmètre annexe ou formation → refus
    - tentative de réapplication sur la même inscription → refus (OneToOne)
    - tentative d'application après un paiement déjà validé → refus
    - notification bien reçue par un `secretary`/`finance_manager` de l'annexe ciblée, pas reçue par une autre annexe si le coupon est restreint
    - prévisualisation temps réel : code invalide → message rouge ; code valide → montant simulé correct

---

## 11. Ce qui ne change pas

Le cœur métier livré précédemment reste inchangé (hors l'extension `branches` de la
section 2) : `coupons/models.py`, `coupons/services/validation.py`,
`coupons/services/application.py`, `coupons/admin.py`, et l'ajout de
`ACTION_COUPON_APPLIED` dans `payments/models.py::FinancialLog`. Ce document ne fait que
détailler le branchement complet et final.
