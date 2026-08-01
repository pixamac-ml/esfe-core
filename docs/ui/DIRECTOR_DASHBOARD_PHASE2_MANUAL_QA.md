# Recette manuelle et visuelle - Dashboard Directeur Phase 2

Date : 26 juillet 2026  
Environnement : Chromium headless, Django `settings_test_local`, données QA isolées

## Matrice fonctionnelle

| Contrôle | Statut | Observation |
|---|---|---|
| Connexion et redirection | PASS | Arrivée sur `/portal/dashboard/` pour la position Directeur des Études |
| Dashboard initial | PASS | Un shell, une sidebar, une topbar et six KPI |
| Sidebar ouverte | PASS | Navigation complète à 1440 x 900 et 1024 x 768 |
| Sidebar réduite | PASS | Libellés masqués, icônes et infobulles conservées |
| Navigation mobile hors-canvas | PASS | Ouverture, fermeture et retour au contenu à 390 x 844 |
| Topbar | PASS | Contexte annexe, profil et cloche existante |
| Navigation des huit sections | PASS | Section active et URL synchronisées par `hx-push-url` |
| KPI | PASS | Liens partiels, valeurs nulles et valeurs zéro vérifiés |
| Planning | PASS | Section et drawer chargés sans remplacement du shell |
| Classes et programmes | PASS | Section, table et drawer existants conservés |
| Enseignants | PASS | Section, recherche et modal de création chargés |
| Évaluations et sessions | PASS | Deux sections distinctes chargées |
| Notes et bulletins | PASS | Workflows existants présents dans la section résultats |
| Alertes | PASS | Compteurs et états vides rendus depuis les données existantes |
| Filtres et recherche | PASS | Debounce 350 ms, `hx-sync`, reset et swap du workspace |
| Tableaux | PASS | Synthèse UI Core et tableaux métier scrollables |
| Pagination avec plusieurs pages | NON TESTÉ | Jeu QA insuffisant pour produire plusieurs pages |
| Modal | PASS | Contenu HTMX, focus, Escape et retour du focus |
| Drawer | PASS | Contenu HTMX, desktop et mobile |
| Confirmation | PASS | Interception `htmx:confirm` et une seule reprise de requête |
| Action destructive réelle | NON TESTÉ | Aucune donnée métier n'a été altérée pendant la recette |
| Toast | PASS | Région live et événement `ui:toast` vérifiés |
| Notifications | PASS | Compteur existant et lien vers le centre de notifications |
| Livraison WebSocket réelle | NON TESTÉ | Aucun événement distant n'a été émis pendant la recette |
| Absence de reload complet | PASS | 8 swaps, entrée Performance Navigation stable à 1 |
| Erreurs navigateur | PASS | Aucune erreur console/page et aucune réponse HTTP >= 400 |
| Isolation annexe | PASS | Couverture automatisée inter-annexes et données QA limitées à l'annexe |

## Responsive et reflow

| Taille | Statut | Observation |
|---|---|---|
| 1440 x 900 | PASS | Sidebar desktop, KPI, panels, table et overlays lisibles |
| 1024 x 768 | PASS | Composition compacte sans chevauchement |
| 900 x 1024 | PASS | Navigation mobile et panels empilés |
| 390 x 844 | PASS | Une colonne, drawer mobile, aucun débordement horizontal |
| Reflow équivalent 200 % (720 px CSS) | PASS | Aucun débordement horizontal ni contrôle inaccessible |

## Accessibilité

| Contrôle | Statut | Observation |
|---|---|---|
| Skip link et ordre des titres | PASS | Lien vers `#ui-core-main`, titre principal unique |
| Navigation clavier | PASS | Liens, boutons et champs atteignables |
| Focus visible | PASS | Anneau de focus UI Core |
| Escape, focus trap, retour du focus | PASS | Vérifiés sur modal et drawer |
| `aria-current` | PASS | Synchronisé après chaque swap |
| `aria-expanded` et `aria-controls` | PASS | Présents sur les contrôles de shell et overlays |
| `aria-live` | PASS | Chargement, toasts et notifications |
| Labels et contrôles natifs | PASS | Recherche, boutons et liens nommés |
| Couleur non exclusive | PASS | Icône ou libellé accompagne les tons sémantiques |
| Contraste visuel principal | PASS | Texte, shell et actions inspectés sur les quatre captures |
| Lecteur d'écran | NON TESTÉ | Aucun lecteur d'écran natif disponible dans cette recette |

## Comparaison avant / après

Les captures sont conservées dans :

- `_audit/director_dashboard_before/`
- `_audit/director_dashboard_after/`

Avant, la base publique injectait le consentement cookies, la sidebar desktop
restait visible sur mobile et réduisait le workspace à une bande étroite. Après,
le dashboard utilise une base interne, une navigation hors-canvas sur petit écran,
une grille KPI responsive et des cibles HTMX stables. Les quatre formats de
référence ne présentent plus de chevauchement ni de débordement horizontal.
