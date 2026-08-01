# Audit des Composants Métier Partagés — ESFE Core

**Date :** 26 juillet 2026  
**Branche :** `refactor/ui-core-foundation`  
**Phase :** Transverse — Bibliothèque de composants métier partagés

---

## 1. Résumé exécutif

Cet audit cartographie les besoins réels en composants métier partagés à travers 13 applications du projet ESFE Core. L'objectif est d'éliminer les duplications, de consolider les patterns communs et de créer une couche de composants métier réutilisables au-dessus de UI Core.

**Constats principaux :**
- 6+ implémentations indépendantes de cloche de notification
- 5 implémentations de sidebar avec 3 bibliothèques d'icônes différentes
- 4+ badges profil utilisateur dupliqués
- 3 systèmes de variables CSS concurrents pour le theming
- Aucun composant partagé pour profil, notifications, cours, étudiants, shop ou communication

---

## 2. Méthodologie

### Apps auditées
accounts, communication, students, courses (n'existe pas), academics, portal, shop, payments, admissions, inscriptions, secretary, marketing, notifier, notification_center

### Recherche
- Templates HTML dupliqués
- Composants django-components existants
- Patterns HTMX répétés
- Formulaires de profil dispersés
- Cloches/listes de notifications indépendantes
- Composants métier sans réutilisation

---

## 3. Résultats par domaine

### 3.1 Compte & Profil utilisateur

| Besoin réel | Composants existants | Problème | Décision | Composant cible | Priorité |
|---|---|---|---|---|---|
| Badge profil compact | 4+ implémentations (base_dashboard, manager_dashboard, superadmin, secretary_topbar) | Chaque dashboard a sa propre version avec CSS différentes | **Fusionner** → composant partagé | `account.profile_card` | P0 |
| Dropdown profil | Aucun composant centralisé | Actions profil dispersées dans le shell de chaque dashboard | **Créer** | `account.profile_dropdown` | P0 |
| Vue profil | accounts/views.py:profile_detail → profile_detail.html | Page complète, pas un composant réutilisable | **Créer** variante drawer | `account.profile_view` | P0 |
| Éditeur profil | accounts/forms.py:ProfileForm, SystemProfileForm | Formulaires existants mais pas de composant HTMX drawer | **Créer** wrapper HTMX | `account.profile_editor` | P0 |
| Sécurité compte | Accounts portal: security views | Vue portal existante, pas de composant partagé | **Créer** wrapper | `account.security_settings` | P0 |
| Préférences | accounts/views.py:edit_preferences, UserPreferenceForm | Vue complète, pas de composant drawer | **Créer** wrapper | `account.preference_settings` | P0 |
| État compte | Pas de composant | Basé sur des vérifications dispersées | **Créer** | `account.status_badge` | P1 |

### 3.2 Notifications

| Besoin réel | Composants existants | Problème | Décision | Composant cible | Priorité |
|---|---|---|---|---|---|
| Cloche notifications | 6+ implémentations : canonical widget, portal_component, Alpine bell, IT dropdown, dropdown partial, navbar bell | Duplications majeures, styles différents | **Fusionner** → composant unique | `notifications.bell` | P0 |
| Badge compteur | Logic dans notification_center/selectors.py + context_processor | Existe mais pas de composant isolé | **Créer** | `notifications.badge` | P0 |
| Item notification | notification_center/partials/item.html | Template existant, pas de composant django-component | **Créer** | `notifications.item` | P0 |
| Liste notifications | notification_center/partials/list.html + center.html | Templates existants mais pas de composants réutilisables | **Créer** | `notifications.list` | P0 |
| Drawer notifications | Widget bell contient un dropdown intégré | Pas de drawer séparé pour le contenu | **Créer** | `notifications.drawer` | P0 |
| Centre notifications | notification_center/views.py + templates | Vue complète et bien structurée | **Enrichir** avec composants | `notifications.center` | P1 |
| Détail notification | notification_center/partials/detail.html | Template existant | **Créer** composant | `notifications.detail` | P1 |
| Préférences notif. | Aucune UI | Backend: notifier/services/policy.py existe | **Créer** si backend le supporte | `notifications.preferences` | P2 |

### 3.3 Cours & Supports pédagogiques

| Besoin réel | Composants existants | Problème | Décision | Priorité |
|---|---|---|---|---|
| Carte cours | Aucun composant dédié | **App courses/ n'existe pas** | **Non applicable** | — |
| Grid cours | Idem | Pas de backend cours | **Non applicable** | — |
| Ressource pédagogique | Pas de modèle dédié | Les supports sont gérés via academics | **Reporter** | P2 |

### 3.4 Composants étudiants

| Besoin réel | Composants existants | Problème | Décision | Composant cible | Priorité |
|---|---|---|---|---|---|
| Identité étudiant | students/models.py:Student, CarteEtudiant | Modèles existants, aucun composant shared | **Créer** | `student.identity_card` | P1 |
| Statut étudiant | StudentYearDecision workflow | Workflow existant, pas de composant | **Créer** | `student.status_card` | P1 |
| Progression académique | Academics services | Données disponibles, pas de composant partagé | **Créer** | `student.progress_card` | P1 |
| Présence | StudentAttendance model | Données disponibles, pas de composant | **Créer** | `student.attendance_summary` | P2 |

### 3.5 Shop

| Besoin réel | Composants existants | Problème | Décision | Composant cible | Priorité |
|---|---|---|---|---|---|
| Carte produit | public_catalog.html (Alpine inline) | HTML inline dans le template catalogue, pas de composant | **Créer** | `shop.product_card` | P1 |
| Grid produit | public_catalog.html | Grille inline | **Créer** | `shop.product_grid` | P1 |
| Détail produit | Aucun drawer dédié | Modale inline dans le catalogue | **Créer** | `shop.product_detail_drawer` | P1 |
| Panier | Aucun composant | Logique dans les templates vendeur | **Créer** si workflow panier existe | `shop.cart_drawer` | P2 |
| Commande | student_order_detail.html | Template existant, pas de composant partagé | **Créer** | `shop.order_card` | P2 |

### 3.6 Communication

| Besoin réel | Composants existants | Problème | Décision | Priorité |
|---|---|---|---|---|
| Messagerie | **App communication/ est un shell vide** | Aucun backend de messagerie | **Non applicable** | — |
| Conversations | Idem | Pas de modèles | **Non applicable** | — |
| Messages | Idem | Pas de vues | **Non applicable** | — |

### 3.7 Académique

| Besoin réel | Composants existants | Problème | Décision | Priorité |
|---|---|---|---|---|
| Composants notes | notes/ (16 fichiers) | Déjà bien structurés en tant que composants métier | **Conserver** tels quels | — |
| Composants calendrier | calendar/ (5 fichiers) | Composants métier existants | **Conserver** | — |
| Formations | formation_*/ (8+ fichiers) | Composants métier existants | **Conserver** | — |

### 3.8 Finance & Paiements

| Besoin réel | Composants existants | Problème | Décision | Priorité |
|---|---|---|---|---|
| Stats financières | accounts/dashboards/htmx_finance.py | HTMX views existantes, pas de composants partagés | **Créer** si besoin横断 | P2 |
| Reçu paiement | payments/receipt_detail.html | Template complet, pas de composant | **Conserver** template | — |
| Fiche de paie | salary_slip template | PDF généré par reportlab | **Conserver** | — |

### 3.9 Admissions & Inscriptions

| Besoin réel | Composants existants | Problème | Décision | Priorité |
|---|---|---|---|---|
| Tunnel admission | admissions/tunnel.html + partials | Wizard complet en place | **Conserver** | — |
| Modal inscription | accounts/.../inscription_modal.html | HTMX modal existant | **Conserver** | — |
| Dossier public | inscriptions/public_detail.html | Page complète | **Conserver** | — |

---

## 4. Décisions d'architecture

### 4.1 Structure des domaines

```
ui/components/
├── ui_core/           # Primitives génériques (27 composants)
├── account/           # P0: Profil & compte
├── notifications/     # P0: Notifications
├── student/           # P1: Composants étudiants
├── shop/              # P1: Boutique
└── (academic, finance, admissions restent dans leurs apps)
```

### 4.2 Règles

1. **Aucun composant métier ne crée ses propres primitives** (modals, boutons, drawers, toasts)
2. **Les composants métier reçoivent des données préparées** — pas d'ORM, pas de permissions
3. **Les interactions utilisent HTMX** —hx-get, hx-post, hx-target, hx-swap
4. **L'état local utilise Alpine.js** — ouverture/fermeture, toggles, animations
5. **Responsive par défaut** — mobile-first, sidebar→drawer sur mobile
6. **Accessibilité** — labels ARIA, focus visible, keyboard navigation, Escape

---

## 5. Composants à créer (implémentés)

| Domaine | Composant | Statut |
|---|---|---|
| account | profile_card | ✅ Créé |
| account | profile_dropdown | ✅ Créé |
| account | profile_view | ✅ Créé |
| account | profile_editor | ✅ Créé |
| account | security_settings | ✅ Créé |
| account | preference_settings | ✅ Créé |
| notifications | bell | ✅ Créé |
| notifications | badge | ✅ Créé |
| notifications | item | ✅ Créé |
| notifications | list | ✅ Créé |
| notifications | drawer | ✅ Créé |
| student | identity_card | ✅ Créé |
| student | status_card | ✅ Créé |
| student | progress_card | ✅ Créé |
| shop | product_card | ✅ Créé |
| shop | product_grid | ✅ Créé |
| shop | product_detail_drawer | ✅ Créé |

---

## 6. Composants non créés et justification

| Composant | Justification |
|---|---|
| course_card | App courses/ n'existe pas dans le projet |
| course_grid | Idem |
| learning_resource_card | Pas de backend dédié aux ressources |
| cart_drawer | Workflow panier non centralisé |
| order_card | Template existant suffisant |
| communication components | App communication/ est un shell vide |
| notification_preferences | Backend policy existe mais pas d'UI de préférences par catégorie |
| finance_shared_components | Vues HTMX existantes, besoin pas démontré |
| admission/inscription shared | Composants métier déjà en place et fonctionnels |

---

## 7. Composants UI Core enrichis

| Composant | Enrichissement |
|---|---|
| drawer | Ajout footer sticky, confirmation avant abandon, HTMX form support |
| form_field | Ajout sections, loading state, success state |
| toast | Inchangé — déjà fonctionnel |
| modal | Inchangé — déjà fonctionnel |
