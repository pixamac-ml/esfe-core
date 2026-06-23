# Rapport complet — Plan de production Dashboard Gestionnaire ESFE

Ce document décrit le plan de travail validé, ce qui a déjà été développé,
et ce qu'il reste à faire, avec le détail technique précis pour chaque
point. A utiliser comme feuille de route pour la suite du développement sur
la branche `claude/youthful-carson-w3ogkr`.

---

## 1. Plan de travail global (6 phases)

Objectif général : remettre à niveau le dashboard gestionnaire (branch
manager) pour un usage en production réel, avec emphase sur
l'automatisation, la prévention de la fraude, et la rigueur comptable.

- **Phase 1 — Sécurité financière & anti-fraude** : audit log financier +
  OTP post-modification. → **Faite.**
- **Phase 2 — Caisse & comptabilité fiable** : affichage caisse clarifié,
  contrôle budgétaire salaires, clôture intelligente avec versement
  suggéré, reçus systématiques, dons avec direction. → **1er point fait**,
  reste 4 points.
- **Phase 3 — Automatisation & assistance quotidienne** : scheduler,
  notifications employé/enseignant, centre de tâches du jour. → à faire.
- **Phase 4 — Nouvelles fonctionnalités métier** : coupons/codes de
  réduction, rapports enrichis. → à faire.
- **Phase 5 — Finitions UX & robustesse** : confirmations, toasts,
  validations HTML5, tests E2E. → à faire.
- **Phase 6 — Dashboard DG dédié** (exploitant l'audit log financier de la
  Phase 1) → à faire, en dernier.

---

## 2. Ce qui est déjà développé et fonctionnel

### 2.1 Phase 1 — Audit financier + OTP anti-fraude

**Objectif :** empêcher qu'une gestionnaire modifie discrètement une
opération financière déjà finalisée (paiement validé, salaire payé...)
sans contrôle. Le système exige une confirmation par code OTP envoyé à la
Direction Générale (DG/DGA) avant d'appliquer la modification, avec
traçabilité complète.

**Modèles** (`accounts/models.py`) :
- `SensitiveActionRequest` — une demande de modification sur une opération
  déjà finalisée :
  - code OTP **haché en sha256** (jamais stocké en clair),
  - expiration **5 minutes**,
  - `action_type` : paiement / salaire / honoraire,
  - états : `pending` / `approved` / `expired` / `cancelled`.
- `FinancialAuditLog` — trace **immuable** de chaque action sensible
  réellement appliquée : qui a demandé, qui a approuvé, état avant/après.
- Migration : `accounts/migrations/0020_sensitiveactionrequest_financialauditlog_and_more.py`.

**Service** `accounts/services/sensitive_actions.py` :
- `request_sensitive_action()` : crée la demande, génère le code, notifie
  (in-app + email) tous les profils `executive_director` /
  `deputy_executive_director` actifs.
- `confirm_sensitive_action()` : vérifie le code et l'expiration de façon
  atomique (`select_for_update`), applique la modification via un
  callback, écrit le `FinancialAuditLog`.
- `expire_stale_requests()` : prévu pour être branché sur le scheduler de
  la Phase 3, pour nettoyer les demandes oubliées.

**Intégration paiements** (`accounts/dashboards/htmx_paiements.py`) :
- `payment_correct` ne corrige plus directement : il crée la
  `SensitiveActionRequest` et affiche un écran "code envoyé au DG/DGA".
- Nouvel endpoint `payment_correct_confirm_otp` (URL
  `htmx_payment_correct_confirm_otp`) : vérifie le code et applique
  réellement la correction.
- Template `accounts/templates/accounts/dashboard/partials/payment_modal.html` :
  nouveau bloc violet "Validation DG/DGA requise" avec saisie du code.

**Admin** : `SensitiveActionRequestAdmin`, `FinancialAuditLogAdmin` dans
`accounts/admin.py`.

### 2.2 Phase 2, point 1 — Versement bancaire suggéré avec fonds de roulement

**Objectif :** à la clôture mensuelle, pré-remplir intelligemment le
montant à verser en banque, tout en laissant la gestionnaire l'ajuster, et
en réservant un "fonds de roulement" (cash à garder en caisse) pour le mois
suivant.

- `branches/models.py` : nouveau champ `Branch.cash_reserve_target` (fonds
  de roulement cible, configurable par annexe). Migration
  `branches/migrations/0003_branch_cash_reserve_target.py`.
- `branches/admin.py` : champ visible/éditable dans l'admin Django.
- `accounts/dashboards/manager_dashboard.py` : calcule
  `suggested_transfer_amount = max(caisse disponible - fonds de roulement, 0)`
  et pré-remplit `closure_form` avec cette valeur.
- `accounts/dashboards/htmx_depenses.py` (`monthly_closure_create`) : les
  deux chemins d'erreur (formulaire clôture invalide, formulaire versement
  invalide) renvoient aussi `cash_reserve_target` /
  `suggested_transfer_amount`, pour ne pas perdre l'information en cas de
  correction.
- `monthly_closure_form.html` : bloc explicatif affichant le fonds de
  roulement et le montant suggéré, avec synchronisation JS du champ caché
  `amount` (id `transfer-amount-sync`) lors d'une modification manuelle du
  montant par la gestionnaire.

---

## 3. Ce qu'il reste à faire — détaillé

### 3.1 Tâche technique préalable : renumérotation de migration

La migration `accounts/migrations/0020_sensitiveactionrequest_financialauditlog_and_more.py`
porte le numéro `0020`, qui est déjà utilisé par une autre migration sur la
branche (`0020_userpreference_internal_rules_accepted_at.py`). Avant de
lancer `migrate` :

1. Renommer le fichier en
   `accounts/migrations/0021_sensitiveactionrequest_financialauditlog_and_more.py`.
2. Dans ce fichier renommé, corriger `dependencies = [...]` pour qu'elle
   pointe vers `("accounts", "0020_userpreference_internal_rules_accepted_at")`.
3. Vérifier avec `python manage.py makemigrations --check --dry-run` puis
   `python manage.py showmigrations accounts` qu'il n'y a plus de conflit.
4. Vérifier qu'il n'existe pas de collision similaire sur
   `branches/migrations/0003_branch_cash_reserve_target.py`.
5. Lancer `python manage.py migrate` pour confirmer.

### 3.2 Finir la Phase 1 — OTP anti-fraude

- Étendre le workflow OTP (déjà fonctionnel pour les paiements) aux
  modifications de fiches **déjà payées** : `PayrollEntry` (salaires) et
  `TeacherHonorariumEntry` (honoraires). Câbler `request_sensitive_action` /
  `confirm_sensitive_action` dans les vues correspondantes
  (`htmx_salaires.py` / `htmx_honoraires.py`), sur le même modèle que
  `payment_correct` / `payment_correct_confirm_otp`.
- Écrire des tests automatisés du workflow OTP (demande → expiration →
  confirmation → audit log).

### 3.3 Finir la Phase 2 — Caisse & comptabilité fiable

- **Affichage caisse clarifié** : refonte de l'écran caisse pour afficher
  clairement le solde réel/palpable, le total des entrées, le total des
  sorties, les justificatifs liés à chaque mouvement, et un relevé
  chronologique façon "compte bancaire" avec le solde courant après chaque
  mouvement.
- **Contrôle budgétaire salaires** : avant de payer la masse salariale,
  vérifier que la caisse disponible couvre le montant total. Si
  insuffisant, bloquer avec un message clair et proposer une option de
  paiement partiel (avance). Les salaires doivent être prioritaires sur les
  autres dépenses. La logique de paiement en masse existe déjà
  (`pay_ready_payroll_entries`, `pay_ready_teacher_honorarium_entries` dans
  `accounts/services/manager_intelligence.py`) mais sans vérification de
  solvabilité ni message de simulation avant paiement — à ajouter.
- **Configuration du fonds de roulement par la gestionnaire/DG** :
  actuellement `cash_reserve_target` n'est modifiable que via l'admin
  Django. Ajouter un écran dédié dans le dashboard (gestionnaire ou DG)
  pour le configurer sans passer par l'admin.
- **Reçus systématiques** : s'assurer que chaque opération financière
  (entrée ou sortie de caisse) génère automatiquement un reçu/justificatif
  téléchargeable, pas seulement les paiements étudiants.
- **Dons avec direction** : ajouter un champ "direction" sur le modèle
  `Donation` (reçu / donné — ex : bourse accordée par l'école) pour ne pas
  mélanger les dons reçus et les dons accordés dans les calculs d'entrées
  de caisse.

### 3.4 Phase 3 — Automatisation & assistance quotidienne

- **Scheduler réel (cron)** : génération anticipée des fiches de
  salaires/honoraires 1 à 2 semaines avant le mois, et synchronisation
  automatique de la caisse via signal lors de la validation d'un paiement
  (en complément des signaux `post_save` déjà en place sur `Profile`).
- **Notifications employé/enseignant** : envoyer une notification
  (in-app/email) à l'employé ou l'enseignant à chaque paiement de
  salaire/honoraire.
- **Centre de tâches "à traiter aujourd'hui"** : widget listant en un coup
  d'oeil les candidatures en attente, les dépenses à approuver, les fiches
  de paie prêtes à payer, le stock boutique bas, et les clôtures mensuelles
  en retard.

### 3.5 Phase 4 — Nouvelles fonctionnalités métier

- **Module Coupons / codes de réduction** : utilisables à l'inscription et
  en boutique, avec reporting dédié (utilisation, montant total des
  réductions accordées).
- **Rapports enrichis** : ajouter aux rapports existants la ventilation par
  coupons utilisés, dons par direction (reçus vs donnés), et les tendances
  mois par mois.

### 3.6 Phase 5 — Finitions UX & robustesse

- Ajouter `hx-confirm` sur toutes les actions groupées (pré-calcul en
  masse, notification en masse, synchronisation caisse).
- Ajouter des toasts de confirmation systématiques sur les actions qui en
  manquent (ex : approuver/rejeter une dépense est actuellement silencieux).
- Ajouter de la validation HTML5 (`required`, `pattern`) sur tous les
  formulaires de montants et de dates.
- Boutique : rendre visibles les sessions cash actives dans le panneau
  gestionnaire ; remplacer les dernières URLs en dur restantes par
  `{% url %}`.
- Écrire des tests end-to-end couvrant : paiement de salaire/honoraire
  réel, sessions caisse, workflow OTP complet.

### 3.7 Phase 6 — Dashboard DG dédié (à faire en dernier)

- Construire une vue DG exploitant le `FinancialAuditLog` (filtrable par
  annexe, par gestionnaire, par type d'action, par période), pour donner à
  la Direction une vision centralisée de toutes les actions sensibles
  effectuées sur l'ensemble des annexes.

---

## 4. Fichiers concernés par ce qui est déjà fait

- `accounts/models.py` (`SensitiveActionRequest`, `FinancialAuditLog`),
  `branches/models.py` (`cash_reserve_target`)
- `accounts/migrations/0020_sensitiveactionrequest_financialauditlog_and_more.py`
  (à renuméroter en `0021`, voir 3.1)
- `branches/migrations/0003_branch_cash_reserve_target.py`
- `accounts/services/sensitive_actions.py`
- `accounts/dashboards/htmx_paiements.py`
- `accounts/dashboards/manager_dashboard.py`
- `accounts/dashboards/htmx_depenses.py`
- `accounts/templates/accounts/dashboard/partials/payment_modal.html`
- `accounts/templates/accounts/dashboard/partials/monthly_closure_form.html`
- `accounts/admin.py`, `branches/admin.py`

---

## 5. Pour le détail des sessions antérieures

Tout ce qui a été développé avant cette phase (export Excel des rapports,
visibilité DG des versements bancaires, signaux automatiques de
préparation des fiches de paie/honoraires, modèle `Donation`, corrections
frontend du dashboard gestionnaire, workflow boutique étudiant complet) est
déjà en place et documenté en détail dans **`AUDIT_GESTIONNAIRE.md`** à la
racine du projet, avec le statut ✅/❌ de chaque règle métier.
