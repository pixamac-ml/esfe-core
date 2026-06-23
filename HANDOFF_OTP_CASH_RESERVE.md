# Handoff — Finalisation patchs OTP anti-fraude + fonds de roulement

Ce document explique où en est le travail et ce qu'il reste à faire pour le
terminer sur la machine locale (PyCharm), branche `claude/youthful-carson-w3ogkr`.

## Contexte

Deux fonctionnalités ont été développées dans une session Claude Code "sur le
web" (sandbox sans accès push direct à GitHub), puis transférées sur la
machine locale via des fichiers `.patch` :

1. **OTP anti-fraude** : workflow de confirmation par OTP avant de pouvoir
   modifier un paiement déjà finalisé (nouveaux modèles
   `SensitiveActionRequest`, `FinancialAuditLog`, service
   `accounts/services/sensitive_actions.py`, vue
   `payment_correct_confirm_otp`, UI dans `payment_modal.html`).
2. **Versement bancaire suggéré / fonds de roulement** : nouveau champ
   `Branch.cash_reserve_target`, calcul du montant suggéré à verser en
   banque (= caisse disponible - fonds de roulement) dans le dashboard
   gestionnaire et le formulaire de clôture mensuelle.

Les deux patchs ont été appliqués localement avec
`git apply --reject --whitespace=fix` (plus tolérant que `git am`, qui
échouait à cause de divergences avec d'autres modifications déjà présentes
sur la branche, faites par une autre session Claude).

## Etat actuel (déjà fait, à vérifier)

- [x] Patch 1 (OTP) appliqué proprement, commité avec le message :
      `feat(accounts): workflow OTP anti-fraude pour modification de paiements deja valides`
- [x] Patch 2 (fonds de roulement) appliqué — **un seul hunk rejeté** sur
      `accounts/templates/accounts/dashboard/partials/monthly_closure_form.html`
      (ligne de l'input caché `amount`, qui doit recevoir
      `id="transfer-amount-sync"` pour que le script JS de synchronisation
      fonctionne). Correction manuelle demandée :
      ```html
      <input type="hidden" id="transfer-amount-sync" name="amount" value="{{ closure_form.bank_transfer_amount.value|default:0 }}">
      ```
- [ ] **A confirmer par l'autre Claude** : vérifier qu'aucun fichier `.rej`
      ne subsiste (`git status` / recherche de fichiers `*.rej`), que la
      correction ci-dessus a bien été appliquée, puis committer avec :
      `feat(branches,accounts): versement bancaire suggere avec fonds de roulement`

## Point d'attention IMPORTANT — collision de migration Django

Une autre session Claude (celle qui tourne dans PyCharm) a créé et déjà
poussé sur `main` une migration :

```
accounts/migrations/0020_userpreference_internal_rules_accepted_at.py
```

Le patch OTP introduit, lui aussi numéroté `0020` :

```
accounts/migrations/0020_sensitiveactionrequest_financialauditlog_and_more.py
```

**Les deux ne peuvent pas coexister avec le même numéro.** Avant de lancer
`migrate`, il faut :

1. Vérifier si `claude/youthful-carson-w3ogkr` contient déjà la migration
   `0020_userpreference_internal_rules_accepted_at.py` (probablement oui, si
   la branche a été rebasée/mergée depuis `main` après le `99cb72e`).
2. Si les deux fichiers `0020_*` existent sur la branche :
   - Renommer le fichier le plus récent (celui du patch OTP) en
     `0021_sensitiveactionrequest_financialauditlog_and_more.py`.
   - Ouvrir ce fichier renommé et corriger la ligne `dependencies = [...]`
     pour qu'elle pointe vers `("accounts", "0020_userpreference_internal_rules_accepted_at")`
     au lieu de l'ancienne dépendance `0019_...` (ou ce qui était présent).
   - Vérifier avec `python manage.py makemigrations --check --dry-run`
     qu'il n'y a plus de conflit, puis `python manage.py showmigrations accounts`.
3. Faire de même si une collision similaire existe côté `branches`
   (migration `0003_branch_cash_reserve_target.py` — vérifier qu'il n'y a pas
   déjà un `0003` différent sur la branche).

## Etapes restantes pour terminer

1. Corriger le hunk rejeté (cf. ci-dessus) dans `monthly_closure_form.html`.
2. Résoudre la collision de migration `0020` (et vérifier `branches/0003`).
3. Lancer `python manage.py migrate` localement pour confirmer que tout
   s'applique sans erreur.
4. Committer les corrections restantes.
5. Pousser la branche :
   ```
   git push -u origin claude/youthful-carson-w3ogkr
   ```
6. Nettoyage : supprimer du dépôt les fichiers `.patch` utilisés pour le
   transfert (`0001feataccountsworkflowOTPantifraudepourmodifica.patch`,
   `0002featbranchesaccountsversementbancairesuggereav.patch`) — ils ne
   doivent pas rester versionnés dans l'historique final si possible
   (`git rm` puis commit, ou laisser tel quel si l'historique est déjà
   poussé et que ça ne pose pas de problème fonctionnel).
7. Une fois la branche poussée, ouvrir une Pull Request vers `main` (pas en
   brouillon si la fonctionnalité est jugée prête, sinon en draft) pour
   revue avant fusion.

## Fichiers concernés (résumé)

- `accounts/models.py`, `accounts/admin.py`, `accounts/urls.py`
- `accounts/services/sensitive_actions.py` (nouveau)
- `accounts/dashboards/htmx_paiements.py`
- `accounts/templates/accounts/dashboard/partials/payment_modal.html`
- `accounts/migrations/0020_sensitiveactionrequest_financialauditlog_and_more.py`
  (à renuméroter, cf. plus haut)
- `branches/models.py`, `branches/admin.py`
- `branches/migrations/0003_branch_cash_reserve_target.py` (vérifier collision)
- `accounts/dashboards/manager_dashboard.py`, `accounts/dashboards/htmx_depenses.py`
- `accounts/templates/accounts/dashboard/partials/monthly_closure_form.html`
- `AUDIT_GESTIONNAIRE.md` (journal de suivi, déjà mis à jour pour ces deux
  phases)
