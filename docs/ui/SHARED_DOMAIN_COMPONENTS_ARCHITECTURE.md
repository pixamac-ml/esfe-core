# Architecture des Composants Métier Partagés — ESFE Core

**Date :** 26 juillet 2026  
**Branche :** `refactor/ui-core-foundation`

---

## 1. Vue d'ensemble

La bibliothèque de composants métier partagés est construite au-dessus de UI Core pour fournir des composants réutilisables dans tous les dashboards de la plateforme ESFE.

```
UI Core (27 primitives génériques)
    ↓
Composants Métier Partagés (17 composants)
    ↓
Dashboards (composent les deux couches)
    ↓
Backend Métier (source de vérité)
```

## 2. Principes d'architecture

### 2.1 Séparation des responsabilités

| Couche | Responsabilité | Exemples |
|---|---|---|
| **UI Core** | Primitives génériques | modal, drawer, toast, form_field, data_table |
| **Composants métier** | Logique d'affichage métier | profile_card, notification_bell, product_card |
| **Dashboards** | Composition et routage | manager_dashboard, director_dashboard |
| **Backend** | Données, permissions, workflow | views, services, models |

### 2.2 Règles non négociables

1. **Pas d'ORM** dans les composants métier
2. **Pas de permissions** dans les composants métier
3. **Pas de calculs métier** dans les composants métier
4. **Données préparées** par le backend uniquement
5. **Réutilisation UI Core** pour boutons, modals, drawers, toasts
6. **HTMX** pour les interactions serveur
7. **Alpine.js** pour l'état local
8. **Responsive** par défaut
9. **Accessible** par défaut

## 3. Structure des fichiers

```
ui/
├── components/
│   ├── ui_core/           # 27 primitives génériques
│   ├── account/           # 6 composants profil/compte
│   ├── notifications/     # 5 composants notifications
│   ├── student/           # 3 composants étudiants
│   ├── shop/              # 3 composants boutique
│   ├── dashboard/         # Composants dashboard existants
│   ├── academic/          # Composants académiques existants
│   └── ...
├── templates/
│   ├── ui_core/           # Templates UI Core
│   ├── account/           # Templates compte
│   ├── notifications/     # Templates notifications
│   ├── student/           # Templates étudiants
│   ├── shop/              # Templates boutique
│   └── ui/                # Templates catalogue
└── views.py               # Vues catalogue UI Core + Métier
```

## 4. Composants par domaine

### 4.1 Account (6 composants)

| Composant | Description | HTMX | Alpine |
|---|---|---|---|
| `account.profile_card` | Badge profil compact | — | — |
| `account.profile_dropdown` | Menu déroulant profil | — | ✓ |
| `account.profile_view` | Vue profil complète | — | — |
| `account.profile_editor` | Formulaire édition | ✓ | — |
| `account.security_settings` | Sécurité compte | ✓ | — |
| `account.preference_settings` | Préférences | ✓ | — |

### 4.2 Notifications (5 composants)

| Composant | Description | HTMX | Alpine |
|---|---|---|---|
| `notifications.bell` | Cloche avec compteur | ✓ | ✓ |
| `notifications.badge` | Badge compteur isolé | — | — |
| `notifications.item` | Ligne de notification | ✓ | — |
| `notifications.list` | Liste paginée | ✓ | — |
| `notifications.drawer` | Panneau latéral | ✓ | ✓ |

### 4.3 Student (3 composants)

| Composant | Description | HTMX | Alpine |
|---|---|---|---|
| `student.identity_card` | Carte identité étudiant | — | — |
| `student.status_card` | Statut académique | — | — |
| `student.progress_card` | Progression | — | — |

### 4.4 Shop (3 composants)

| Composant | Description | HTMX | Alpine |
|---|---|---|---|
| `shop.product_card` | Carte produit | ✓ | — |
| `shop.product_grid` | Grille responsive | — | — |
| `shop.product_detail_drawer` | Détail produit | ✓ | ✓ |

## 5. Catalogue

Accessible via `/ui/system/domains/` (protégé par `ui_system_access`).

Présente toutes les familles de composants avec:
- Aperçu
- Composants disponibles
- États
- Variantes
- API résumée

## 6. Dépendances

### Autorisées
- `django_components` — framework de composants
- `ui.components.ui_core.*` — primitives génériques
- `django.templatetags` — tags Django standard

### Interdites
- Imports de modèles métier (`accounts.models`, `students.models`, etc.)
- Accès ORM (`.objects`)
- Appels `can_access()`, `get_user_scope()`
- Calculs de permissions
