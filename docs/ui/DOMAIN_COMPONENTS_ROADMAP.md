# Roadmap des Composants par Domaine — ESFE Core

**Date :** 26 juillet 2026

---

## Matrice de décision

| Domaine | Composant | Statut | Raison |
|---|---|---|---|
| **Account** | profile_card | ✅ Implémenté | Duplication dans 4+ dashboards |
| | profile_dropdown | ✅ Implémenté | Pas de composant centralisé |
| | profile_view | ✅ Implémenté | Page complète non réutilisable |
| | profile_editor | ✅ Implémenté | Formulaire sans composant HTMX |
| | security_settings | ✅ Implémenté | Vue portal non réutilisable |
| | preference_settings | ✅ Implémenté | Vue complète non réutilisable |
| | status_badge | ⏳ Pendant migration | Besoin faible, les statuts sont dans profile_view |
| **Notifications** | bell | ✅ Implémenté | 6+ implémentations dupliquées |
| | badge | ✅ Implémenté | Compteur pas isolé |
| | item | ✅ Implémenté | Template existant non réutilisable |
| | list | ✅ Implémenté | Template existant non réutilisable |
| | drawer | ✅ Implémenté | Widget bell intégré, pas de drawer séparé |
| | center | 🔧 Existant | notification_center déjà complet |
| | detail | ⏳ Pendant migration | Utilisé dans le centre existant |
| | preferences | ❌ Non créé | Pas de backend de préférences par catégorie |
| **Student** | identity_card | ✅ Implémenté | Aucun composant partagé |
| | status_card | ✅ Implémenté | Workflow existant, pas de composant |
| | progress_card | ✅ Implémenté | Données disponibles, pas de composant |
| | attendance_summary | ⏳ Pendant migration | Besoin spécifique aux dashboards enseignants |
| | grade_summary | ⏳ Pendant migration | Notes gérées par les composants notes/ |
| | bulletin_card | ⏳ Pendant migration | PDF généré par reportlab |
| | schedule_card | ⏳ Pendant migration | Calendrier déjà dans calendar/ |
| **Shop** | product_card | ✅ Implémenté | HTML inline dans le catalogue |
| | product_grid | ✅ Implémenté | Grille inline |
| | product_detail_drawer | ✅ Implémenté | Modale inline |
| | cart_drawer | ❌ Non créé | Workflow panier non centralisé |
| | cart_item | ❌ Non créé | Idem |
| | order_card | ⏳ Pendant migration | Template existant suffisant |
| | order_timeline | ❌ Non créé | Pas de besoin démontré |
| **Communication** | — | ❌ Non applicable | App communication/ est un shell vide |
| **Academic** | — | ✅ Existants | Composants notes/, calendar/, formation_* déjà en place |
| **Finance** | — | ⏳ Pendant migration | Vues HTMX existantes, pas de besoin横断 démontré |
| **Admissions** | — | ✅ Existants | Tunnel admission déjà complet |
| **Inscriptions** | — | ✅ Existants | Modal inscription déjà en place |

## Légende

- ✅ **Implémenté maintenant** — Composant créé dans cette mission
- ⏳ **Pendant une migration** — Sera implémenté lors de la migration du dashboard concerné
- 🔧 **Existant** — Composant ou vue déjà en place, à conserver
- ❌ **Non créé** — Pas de besoin démontré ou backend inexistant
