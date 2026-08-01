# Recette manuelle UI Core - Phase 1.75

Date : 26 juillet 2026  
Environnement : Chromium 151 headless, serveur Django isolé
`settings_test_local`, données et compte temporaires supprimés après recette.

## Résultats

| Vérification | Desktop 1440x900 | Tablette 900x1024 | Mobile 390x844 | Observation |
|---|---|---|---|---|
| Chargement `/ui/system/` | PASS | PASS | PASS | AppShell rendu sans erreur console |
| Absence navbar publique | PASS | PASS | PASS | zéro libellé public « Candidater » |
| Absence footer public | PASS | PASS | PASS | zéro footer vitrine |
| Sidebar | PASS | PASS | PASS | desktop 272 px, réduite 72 px; drawer mobile |
| Topbar | PASS | PASS | PASS | titre, contexte, actions et bouton mobile |
| Tabs | PASS | PASS | PASS | `aria-selected` actualisé |
| Dropdown | PASS | PASS | PASS | ouverture, clic extérieur/Échap |
| Command palette | PASS | PASS | PASS | Ctrl+K, recherche locale, Échap |
| Modal HTMX | PASS | PASS | PASS | fragment chargé, Échap, focus restitué |
| Drawer HTMX | PASS | PASS | PASS | fragment et tabs chargés, Échap |
| Confirmation HTMX | PASS | PASS | PASS | POST fictif, cible locale et toast |
| Toast | PASS | PASS | PASS | pile, fermeture et live region |
| Tableau | PASS | PASS | PASS | scroll contrôlé, tri et états |
| Recherche debounce | PASS | PASS | PASS | cible partielle, requêtes concurrentes synchronisées |
| Filtres | PASS | PASS | PASS | statut et densité sans navigation |
| Pagination | PASS | PASS | PASS | page 1/2 puis 2/2 |
| Formulaire HTMX | PASS | PASS | PASS | erreurs serveur puis succès local |
| Erreur simulée | PASS | PASS | PASS | HTTP 500 attendu converti en toast danger |
| Loading/indicateurs | PASS | PASS | PASS | table, formulaire, refresh et graphiques |
| Clavier | PASS | PASS | PASS | boutons réels, tabs, Ctrl+K, Escape |
| Retour du focus | PASS | PASS | PASS | vérifié sur la modal |
| Absence de reload complet | PASS | PASS | PASS | zéro navigation principale pendant les scénarios |
| Débordement horizontal page | PASS | PASS | PASS | aucun; la table scrolle dans son conteneur |
| Zoom 200 % | PASS | PASS | PASS | équivalent CSS 720 px vérifié sans débordement |
| Captures visuelles | PASS | PASS | PASS | `_audit/ui_core_phase1_75_*.png` |
| Lecteur d'écran réel | NON TESTÉ | NON TESTÉ | NON TESTÉ | audit spécialisé restant |

## Problèmes détectés et corrigés

1. La validation HTML native empêchait la démonstration des erreurs serveur :
   ajout de `novalidate` au formulaire fictif.
2. Des requêtes de recherche rapprochées pouvaient terminer après le remplacement
   de leur cible : ajout de `hx-sync="#ui-table-demo:replace"`.
3. Un `hx-indicator` situé dans une cible remplacée provoquait un `swapError` :
   indicateur rendu via l'état `htmx-request`, sans référence vers un nœud supprimé.

La seconde recette complète ne produit aucune erreur console ou JavaScript avant
l'erreur HTTP volontaire. L'erreur volontaire est annoncée par le toast prévu.

## Limites

- Aucun lecteur d'écran natif (NVDA/JAWS/VoiceOver) n'a été piloté.
- Les captures full-page vérifient la composition; une recette visuelle humaine
  supplémentaire restera utile lors de la migration du premier dashboard.
