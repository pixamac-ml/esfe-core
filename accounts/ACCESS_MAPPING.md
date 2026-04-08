# Access Mapping (Compatibilité)

Ce document décrit la couche de compatibilité introduite dans `accounts/access.py`.

## Objectif

- centraliser la logique d'accès sans casser l'existant
- conserver les groupes Django, `profile.role` et les dashboards actuels
- normaliser les rôles pour les futures extensions ERP
- fournir un `scope` annexe unique pour les nouvelles vues

## API centrale exposée

- `get_user_profile_role(user)` → rôle brut issu de `profile.role`
- `get_user_role(user)` → rôle canonique normalisé
- `get_user_groups(user)` → groupes + alias legacy compatibles
- `get_user_annexe(user)` → annexe active détectée
- `get_user_position(user)` → position métier dérivée si inférable
- `get_user_scope(user)` → dictionnaire de contexte d'accès
- `can_access(user, action, resource)` → décision d'autorisation centralisée

## Rôles canoniques

- `student`
- `teacher`
- `staff_admin`
- `directeur_etudes`
- `super_admin`

## Mapping `profile.role` -> rôle canonique

- `superadmin` -> `super_admin`
- `executive` -> `directeur_etudes`
- `admissions` -> `staff_admin`
- `finance` -> `staff_admin`
- `teacher` -> `teacher`
- `student` -> `student`

## Mapping groupes -> rôle canonique

- `admissions_managers` -> `staff_admin`
- `admissions` -> `staff_admin` *(alias legacy)*
- `finance_agents` -> `staff_admin`
- `finance` -> `staff_admin` *(alias legacy)*
- `gestionnaire` -> `staff_admin`
- `manager` -> `staff_admin` *(alias legacy)*
- `executive_director` -> `directeur_etudes`
- `executive` -> `directeur_etudes` *(alias legacy)*

## Expansion de compatibilité des groupes

`get_user_groups(user)` retourne les groupes réels **et** les alias de compatibilité suivants :

- cluster admissions : `admissions_managers` <-> `admissions`
- cluster finance : `finance_agents` <-> `finance`
- cluster executive : `executive_director` <-> `executive`
- cluster manager : `gestionnaire` <-> `manager`

Cela permet de ne pas casser les anciens helpers qui testent encore des noms courts comme `admissions`, `finance` ou `executive`.

## Détection d'annexe

`get_user_annexe(user)` applique l'ordre suivant :

1. `profile.branch`
2. `PaymentAgent.branch`
3. `Branch.manager`

Cas particulier :

- `superuser` -> pas d'annexe imposée (`None`), car accès global

## Scope unifié

`get_user_scope(user)` retourne :

- `branch` / `annexe` : annexe détectée
- `is_global` : `True` si superuser, `profile.role in {executive, superadmin}` ou groupe `executive_director`
- `role` : rôle canonique
- `profile_role` : rôle brut
- `groups` : groupes expansés de compatibilité
- `position` : `super_admin`, `branch_manager`, `payment_agent`, `executive_director` ou `None`

## Règles actuelles `can_access(...)`

### `("view_dashboard", "admissions")`

- groupes compatibles : `admissions_managers`, `admissions`
- rôles profil : `admissions`
- accès global autorisé : oui

### `("view_dashboard", "finance")`

- groupes compatibles : `finance_agents`, `finance`
- rôles profil : `finance`
- accès global autorisé : oui

### `("view_dashboard", "executive")`

- groupes compatibles : `executive_director`, `executive`
- rôles profil : `executive`, `superadmin`
- rôles canoniques : `directeur_etudes`, `super_admin`
- accès global autorisé : oui

### `("view_dashboard", "manager")`

- groupes compatibles : `gestionnaire`, `manager`
- accès global autorisé : non

## Journalisation

La couche centrale journalise :

- le rôle détecté
- les groupes détectés
- la position détectée
- le scope détecté
- les accès accordés / refusés

## Intégration progressive

- les dashboards existants restent inchangés dans leur comportement
- `accounts/dashboards/permissions.py` et `accounts/dashboards/helpers.py` délèguent déjà vers la couche centrale
- `accounts/mixins.py` délègue désormais aussi vers les groupes normalisés
- les nouvelles vues doivent utiliser `can_access(...)` et `get_user_scope(...)`

