# Recette Manuelle — Composants Métier Partagés

**Date :** 26 juillet 2026  
**Environnement :** settings_test_local, SQLite, données QA

---

## 1. Compte & Profil

| # | Test | Résultat |
|---|---|---|
| 1 | Carte profil affiche avatar, nom, rôle, annexe, statut | PASS |
| 2 | Carte profil compact masque les détails secondaires | PASS |
| 3 | Statut actif affiche point vert | PASS |
| 4 | Statut suspendu affiche point rouge | PASS |
| 5 | Dropdown profil s'ouvre/ferme au clic | PASS |
| 6 | Dropdown affiche : Mon profil, Modifier, Sécurité, Préférences, Déconnexion | PASS |
| 7 | Dropdown se ferme avec Escape | PASS |
| 8 | Dropdown se ferme au clic extérieur | PASS |
| 9 | Vue profil affiche identité complète | PASS |
| 10 | Vue profil affiche contacts (email, téléphone) | PASS |
| 11 | Vue profil affiche métadonnées (date création, dernière connexion) | PASS |
| 12 | Éditeur profil affiche formulaire HTMX | PASS |
| 13 | Éditeur profil affiche erreurs serveur inline | PASS |
| 14 | Éditeur profil affiche état loading | PASS |
| 15 | Sécurité affiche formulaire changement mot de passe | PASS |
| 16 | Préférences affiche formulaire de préférences | PASS |

## 2. Notifications

| # | Test | Résultat |
|---|---|---|
| 17 | Cloche affiche compteur quand > 0 | PASS |
| 18 | Cloche affiche "99+" quand > 99 | PASS |
| 19 | Cloche sans notifications: pas de badge | PASS |
| 20 | Badge compteur affiche le nombre exact | PASS |
| 21 | Badge compteur affiche "99+" au-delà de max | PASS |
| 22 | Item notification affiche titre, résumé, date | PASS |
| 23 | Item non lu a un fond coloré | PASS |
| 24 | Item haute priorité affiche icône rouge | PASS |
| 25 | Liste vide affiche "Aucune notification" | PASS |
| 26 | Liste en chargement affiche skeleton | PASS |
| 27 | Drawer notifications s'ouvre/ferme | PASS |
| 28 | Drawer notifications affiche Escape handler | PASS |
| 29 | Drawer notifications affiche focus trap | PASS |

## 3. Étudiants

| # | Test | Résultat |
|---|---|---|
| 30 | Carte identité affiche photo, nom, matricule, classe | PASS |
| 31 | Carte identité sans photo affiche initiales | PASS |
| 32 | Carte identité inactive affiche point rouge | PASS |
| 33 | Carte statut promu affiche badge vert | PASS |
| 34 | Carte statut redoublant affiche badge orange | PASS |
| 35 | Carte progression affiche barres | PASS |
| 36 | Carte progression vide affiche sans erreur | PASS |

## 4. Shop

| # | Test | Résultat |
|---|---|---|
| 37 | Carte produit affiche image, nom, prix, stock | PASS |
| 38 | Carte produit indisponible affiche overlay | PASS |
| 39 | Carte produit en rupture affiche "Rupture de stock" | PASS |
| 40 | Carte produit avec réduction affiche prix barré | PASS |
| 41 | Grille produit vide affiche état vide | PASS |
| 42 | Grille produit en chargement affiche skeletons | PASS |
| 43 | Drawer détail produit s'ouvre/ferme | PASS |
| 44 | Drawer détail affiche variantes | PASS |
| 45 | Drawer détail affiche bouton "Ajouter au panier" | PASS |

## 5. Responsive

| # | Test | Résultat |
|---|---|---|
| 46 | Desktop (1440px) : tous les composants rendent correctement | PASS |
| 47 | Tablette (900px) : grille s'adapte | PASS |
| 48 | Mobile (390px) : composants empilés | PASS |
| 49 | Drawer passe en plein écran sur mobile | PASS |

## 6. Accessibilité

| # | Test | Résultat |
|---|---|---|
| 50 | Tous les boutons ont type="button" | PASS |
| 51 | Labels ARIA présents sur les overlays | PASS |
| 52 | Focus trap fonctionne dans les drawers | PASS |
| 53 | Escape ferme les overlays | PASS |
| 54 | Focus retourne à l'élément déclencheur | PASS |
| 55 | Contraste suffisant sur tous les composants | PASS |

## 7. Catalogue

| # | Test | Résultat |
|---|---|---|
| 56 | /ui/system/domains/ affiche le catalogue | PASS |
| 57 | Catalogue affiche 4 familles | PASS |
| 58 | Catalogue affiche 17 composants | PASS |
| 59 | Catalogue protégé par authentification | PASS |
| 60 | Catalogue protégé par rôle superuser en production | PASS |

## 8. Tests

| # | Test | Résultat |
|---|---|---|
| 61 | 104/104 tests UI passent | PASS |
| 62 | python manage.py check : 0 erreurs | PASS |
| 63 | npm run build:css : succès | PASS |
| 64 | Aucune régression UI Core | PASS |
| 65 | Aucun import ORM dans les composants métier | PASS |
| 66 | Aucune permission métier dans les composants génériques | PASS |

---

**Verdict :** 66/66 PASS — RECETTE VALIDÉE
