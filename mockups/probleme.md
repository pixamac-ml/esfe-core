# Mission Claude Code — Dashboard Informaticien : instantanéité + icônes

## Contexte
Le dashboard de l'informaticien d'annexe (espace `it_*` : `portal/views/it_workflows.py`, services `informaticien_workflows.py` / `it_dashboard_service.py`, templates `templates/portal/informaticien/`) est déjà branché et fonctionne. Stack : **Django + HTMX + Alpine.js + Cotton + Tailwind**.

Deux problèmes d'expérience utilisateur sont à corriger, **sans changer le design, la structure des écrans, le workflow des notes, ni les règles métier** (calcul des moyennes, compensation par UE, crédits sur 30, décisions). On ne touche qu'à la **réactivité** et aux **icônes**.

---

## Problème 1 — Tout passe par un spinner : rien n'est instantané (priorité haute)

Symptôme : à **chaque** interaction (saisir une note dans la grille, cliquer une section), un loader/spinner se déclenche et bloque visuellement avant que le contenu n'apparaisse. La saisie d'une note ne se répercute pas instantanément : on tape `10`, et il faut attendre un tour de spinner avant que ça « prenne ». C'est valable sur la grille de notes **et** sur le changement de section.

### 1A. Grille de notes — saisie strictement instantanée
- Les valeurs **dérivées** (Note × coeff, crédits obtenus, Moyenne d'UE, Note coef. d'UE, crédits d'UE, Moyenne générale, %, Crédits /30, Observation) doivent être **recalculées côté client en Alpine**, instantanément à la frappe. **Zéro aller-retour réseau pour l'affichage.** Quand l'utilisateur tape `10`, la cellule affiche `10` immédiatement et tous les totaux se mettent à jour dans la même frame.
- La **persistance serveur** se fait **en arrière-plan**, sans bloquer :
  - `hx-trigger="input changed delay:600ms"` (debounce) sur la cellule, pas à chaque touche.
  - `hx-sync="closest tr:replace"` (ou équivalent) pour coalescer/annuler les requêtes empilées sur la même ligne.
  - `hx-swap="none"` côté cellule : le serveur **ne réinjecte pas** l'input pendant que l'utilisateur écrit (jamais de remplacement du champ sous le curseur).
  - **Pas de `hx-indicator` global** sur ces requêtes : remplacer le spinner par un petit statut discret non bloquant (« Enregistré ✓ » / « … » en coin de cellule ou de ligne), via `hx-indicator` ciblé sur ce micro-élément uniquement.
  - Ne **jamais** désactiver l'input pendant l'enregistrement (pas de `hx-disabled-elt` sur le champ).
- **Source de vérité** : le serveur reste autoritaire. Au **save/publish**, le serveur recalcule et peut renvoyer les totaux faisant foi via **swaps OOB** (`hx-swap-oob`) ciblés (ligne de l'étudiant, pied de tableau), sans recharger toute la grille. Le calcul client est **uniquement pour l'affichage immédiat**, pas pour la décision finale.
- Critère d'acceptation : taper une note → valeur + tous les calculs mis à jour instantanément, **aucun spinner**, **focus et position du curseur conservés**, enregistrement silencieux en arrière-plan.

### 1B. Navigation entre sections / workspaces
- Supprimer le **spinner bloquant systématique** sur chaque `hx-get` de section. Le remplacer par :
  - soit une **fine barre de progression en haut** (style « topbar loader ») qui n'apparaît **que si la requête dépasse ~300 ms** (délai d'indicateur),
  - soit aucun indicateur pour les requêtes rapides.
- Conserver l'historique : `hx-push-url="true"` + gestion `hx-history`, et **préserver le scroll** (ne pas tout réinitialiser à chaque swap).
- Éviter de re-télécharger ce qui ne change pas : garder en DOM les workspaces déjà chargés et basculer l'affichage (re-entrer dans une section déjà visitée doit être **instantané**), ou mettre en cache HTMX là où c'est sûr.
- **Réduire la latence serveur** (c'est souvent ça qui « fait tourner le spinner ») : auditer les `build_*_context` et les vues `it_*` pour les requêtes **N+1**, ajouter `select_related` / `prefetch_related` / annotations agrégées, afin que les fragments reviennent en quelques dizaines de ms.
- Critère d'acceptation : cliquer une section paraît instantané ; un indicateur n'apparaît que si la réponse est réellement lente.

### 1C. Configuration HTMX globale
- Localiser l'**indicateur global** actuel (probablement une classe `.htmx-request` qui affiche un spinner sur `body`/`main` ou un overlay) et le **désactiver/cibler** au lieu de le déclencher partout.
- Régler `htmx.config` : un **délai d'indicateur** (pour que les requêtes courtes ne fassent jamais clignoter de spinner), `defaultSwapStyle`, timeout raisonnable.
- Vérifier qu'aucun `hx-indicator` n'est posé trop haut dans l'arbre (héritage qui retombe sur tous les enfants).

---

## Problème 2 — Icônes des boutons
- Auditer **tous** les boutons/actions du dashboard. Tout bouton d'action en **texte seul** ayant un équivalent iconographique clair reçoit une icône **lucide** cohérente (même style, même taille, icône à gauche du texte) :
  - Publier → `send` · Exporter → `download` · Importer → `upload-cloud` · Réinitialiser MDP → `key-round` · Bloquer → `lock` / Débloquer → `unlock` · Désactiver → `user-x` / Réactiver → `user-check` · Générer carte → `badge-check` · Nouveau ticket → `plus` · Recalculer → `calculator`, etc. (adapter au libellé réel).
- **Point critique** : après chaque swap HTMX, **réinitialiser les icônes** (`lucide.createIcons()` sur `htmx:afterSwap` **et** `htmx:afterSettle`) — sinon les icônes des fragments injectés ne s'affichent pas.
- Accessibilité : `aria-label` sur les boutons **icône seule**.
- Ne pas surcharger : icône seulement quand elle clarifie l'action ; garder le texte sur les actions importantes.

---

## Contraintes (à respecter strictement)
- **Ne pas modifier** : le design visuel, la mise en page, la structure des 13 modules, le workflow des notes (`empty → … → final_published`), ni les règles de calcul (moyennes pondérées par coefficient, compensation par UE, crédits /30 et leur proportionnalité, décision Admis/Non admis).
- **Sécurité** : le calcul client est purement cosmétique/immédiat ; le serveur reste la source de vérité et conserve **tout le contrôle d'accès côté serveur** (permissions `it_support` + scope annexe). Ne déplace aucune logique sensible vers le client.
- Pas de régression : pas d'erreurs console, pas de double-soumission, pas de perte de saisie en cas de navigation rapide.

## Définition de « terminé » (checklist de validation)
1. Saisir une note dans la grille : la valeur et **tous** les calculs s'actualisent **instantanément**, sans spinner, curseur conservé ; l'enregistrement part en arrière-plan (vérifiable dans l'onglet réseau) et un statut discret confirme.
2. Changer plusieurs fois de note rapidement : pas de requêtes empilées (debounce + `hx-sync`), pas de valeurs qui « sautent ».
3. Naviguer entre sections : ressenti instantané ; indicateur uniquement si > ~300 ms ; URL et historique fonctionnels ; scroll préservé.
4. Revenir sur une section déjà ouverte : immédiat.
5. Toutes les icônes pertinentes présentes et **persistantes après les swaps HTMX**.
6. Aucune requête N+1 sur les vues `it_*` les plus fréquentes (vérifier avec Django Debug Toolbar ou `assertNumQueries`).

Commence par : (a) localiser l'indicateur global et les attributs `hx-*` de la grille de notes, (b) me proposer le plan de modif fichier par fichier **avant** d'appliquer, puis (c) implémenter section par section en validant la checklist.