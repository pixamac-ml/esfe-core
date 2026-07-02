# Catalogue de la bibliothèque `ui` — mission de bétonnage enrichie
## Inventaire complet + contrat qualité, pour Claude Code

> **Ce document complète** `mission-betonnage-ui.md`. Le *comment* (recompiler, galerie, lots, points de contrôle, fluidité) y est déjà décrit. Ce document-ci définit le *quoi* : la liste complète des composants à construire/solidifier, et le niveau d'exigence.

> **Principe directeur — éviter de construire dans le vide.**
> - **Composants universels** (ce document) : utilisés par tous les dashboards → on les construit maintenant, complets et soignés.
> - **Composants métier** (ex. formulaire de paiement, fiche étudiant) : assemblés à partir des universels **au moment de migrer le dashboard concerné**, pas avant. On ne les devine pas.
> Le champ « montant » se construit maintenant ; le formulaire de paiement s'assemble en phase 2.

> **Rappel d'exécution :** un lot/famille à la fois → `watch:css` recompile → vérifier dans la galerie → commit. Avant de créer : vérifier qu'un équivalent n'existe pas. Une variante = un paramètre, pas un doublon.

---

## Le contrat qualité — TOUT composant doit le respecter
Une brique n'est « bétonnée » que si elle coche **tout** ceci :
- [ ] **Couleurs** : tokens CSS uniquement (`var(--school-primary)`, `var(--text)`, `var(--surface-*)`, `var(--success)`…). Zéro couleur en dur.
- [ ] **Icônes** : Lucide uniquement (`data-lucide`). Zéro FontAwesome.
- [ ] **Typo / casse** : échelle de tailles cohérente, `sentence case` (pas de Title Case partout).
- [ ] **États** prévus quand pertinent : normal, survol, focus, désactivé, **chargement**, **erreur**, **vide**.
- [ ] **Fluidité** : compatible HTMX (cible/swap propres) et Alpine (état local) ; un retour visuel en moins de 100 ms sur toute action.
- [ ] **Accessibilité** : libellé ou `aria-label`, focus visible, contraste suffisant.
- [ ] **Paramétrable** : variantes via paramètres (`variant`, `size`, `tone`…), jamais par copie.
- [ ] **Rendu vérifié** dans la galerie, dans ses différents états.

---

## L'inventaire à construire / solidifier

Priorités : **P1** = à faire d'abord (utilisé partout) · **P2** = ensuite · **P3** = utile, après les migrations.

### A. Primitives / atomes
- `button` — variantes (primary/secondary/ghost/danger), tailles, `icon`, **état chargement (spinner intégré)**, désactivé. **P1**
- `icon` — enrobe Lucide (taille, couleur token). **P1**
- `spinner` / `loader` — petit indicateur de chargement réutilisable. **P1**
- `skeleton` — placeholder de chargement (lignes, cartes). **P1**
- `badge` / `status_badge` — pastille sémantique (succès/alerte/danger/info). **P1** *(existe, à étendre)*
- `pill` / `tag` / `chip` — étiquette, éventuellement supprimable. **P2**
- `avatar` + `avatar_group` — initiales ou photo, tailles. **P2** *(avatar existe)*
- `label` — libellé cohérent. **P1** *(existe)*
- `tooltip` — infobulle (Alpine). **P2**
- `divider` — séparateur. **P3**
- `progress_bar` (linéaire) + `progress_ring` (circulaire). **P2** *(barre existe)*

### B. Champs de formulaire (briques universelles)
> Ce sont elles qui permettront d'assembler **tous** les formulaires (paiement, inscription, notes…) plus tard.
- `form_field` — enveloppe : libellé + contrôle + aide + **message d'erreur intégré**. **P1** *(existe, à fiabiliser)*
- `input` — texte, avec états erreur/désactivé. **P1**
- `textarea`. **P1**
- `select` — liste déroulante stylée. **P1**
- `combobox` — select recherchable (Alpine). **P2**
- `checkbox`, `radio_group`. **P1**
- `switch` / `toggle`. **P2**
- `amount_input` — montant formaté en devise (pour paiements/finances). **P1**
- `date_picker`. **P2**
- `file_upload` / `dropzone` — avec aperçu. **P2**
- `form_actions` — rangée submit/annuler cohérente. **P1**
- `form_section` / `fieldset` — regroupement titré. **P2**
> **Fluidité des formulaires** : validation HTMX inline (erreur affichée sous le champ sans recharger), bouton submit qui passe en état chargement, retour `toast` au succès.

### C. Cartes & conteneurs
- `dashboard_card` — carte de contenu générique. **P1** *(existe)*
- `metric_card` / `kpi_row` — chiffres clés + tendance réelle. **P1** *(existe)*
- `stat_card` — variante avec icône + tendance + lien (drill-down). **P2**
- `section_header` — titre + action (slot). **P1** *(existe)*
- `panel` / `surface` — bloc neutre réutilisable. **P2**

### D. Affichage de données
- `data_table` — **compléter** : tri HTMX, pagination HTMX, sélection, cellule éditable optimiste, état vide. **P1** *(partiel)*
- Cellules spécialisées (statut, montant, actions, avatar+nom) à utiliser dans `data_table`. **P2**
- `pagination` — contrôle réutilisable (HTMX). **P1**
- `filter_bar` / `search_bar` — filtres déclenchant du HTMX. **P2** *(search existe)*
- `empty_state`. **P1** *(existe)*
- `info_field` / `description_list` — paires libellé/valeur. **P2** *(existe)*
- `timeline` / `activity_feed` — fil d'activité. **P3**

### E. Retour & surcouches (overlays)
- `toast` — canal unique de succès/erreur après action. **P1** *(existe, à fiabiliser)*
- `alert` / `banner` — message inline (info/alerte/erreur). **P1**
- `modal` / `dialog` — fenêtre, contenu chargeable en HTMX. **P1**
- `confirm_dialog` — confirmation d'action sensible (suppression…). **P1**
- `drawer` — panneau latéral. **P2** *(existe)*
- `dropdown_menu` / `popover` — menu contextuel (Alpine). **P2**
- `loading_overlay` — voile de chargement sur une zone. **P3**

### F. Navigation
- `tabs` — onglets (Alpine). **P1** *(existe)*
- `breadcrumb` — fil d'ariane. **P2**
- `stepper` / `step_indicator` — étapes. **P3** *(existe en admission, à généraliser)*
- (Coquille unique de portail : sidebar/topbar — traitée au chantier d'unification des bases, pas ici.)

### G. Widgets dashboard
- `chart_card` — carte graphique. **⚠ Décision requise** : choisir **une** librairie de graphes (ex. une lib JS unique) et n'afficher que des **données réelles**. Aucun graphe factice. **P2**
- `calendar` / `schedule` — emploi du temps. **P3**
- `mini_stat` — micro-indicateur. **P3**

---

## Séquencement recommandé
1. **P1 d'abord**, dans cet ordre de familles : primitives (A) → champs de formulaire (B) → cartes (C) → données (D, dont compléter `data_table`) → retour/overlays (E) → navigation de base (F).
2. À chaque composant : construire → vérifier dans la galerie → documenter dans la galerie → commit.
3. **P2** ensuite, à mesure des besoins.
4. **P3** et les composants métier : pendant la phase 2 (migration des dashboards), ajoutés à `ui` au fil de l'eau.

## Point de décision à me remonter
- La **valeur canonique** des couleurs (réconciliation des deux bleus).
- La **librairie de graphes** retenue pour `chart_card`.
- Tout composant dont le besoin n'est pas clair : me le proposer avant de le construire.

---

## Ce que cette mission NE fait toujours PAS
Migrer les dashboards · supprimer les 988 FontAwesome · unifier les 23 bases · retirer AdminLTE. → Chantier 2, une fois la bibliothèque P1 construite, vérifiée dans la galerie et documentée.

---

*À verser sous `docs/ui/catalogue-bibliotheque-ui.md`.*
