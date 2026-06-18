# ESFé Core — Cahier des améliorations validées par le DG

> **Statut :** Volet **Site web** finalisé et prêt pour implémentation. Volet **Système de gestion** à compléter (entretien à venir).
> **Auteur :** Mohamed Aly Camara
> **Dernière mise à jour :** 18 juin 2026
> **Destinataire :** implémentation directe (Claude Code).
> **Cadre qualité :** Django propre et modulaire, production-ready, sécurisé, performant. **Aucun hack ni solution temporaire.**

---

## 0. Règles d'implémentation (à respecter pour tout le document)

- **Cohérence avant tout.** S'aligner sur l'existant d'ESFé Core : même design system, mêmes composants UI, mêmes conventions de nommage, même structure modulaire (une app Django par domaine). Ne rien introduire qui casse l'harmonie visuelle ou architecturale déjà en place.
- **Conception 100 % maison.** Pas de plateforme externe de référence à copier. On conçoit nos propres écrans, alignés sur le style ESFé Core.
- **Pas de hack.** Code Django idiomatique, migrations propres, séparation claire vues/templates/modèles, validation côté serveur.
- **Sécurité et performance** traitées dès la conception, pas après coup.

### Décisions transversales actées

| Sujet | Décision |
|---|---|
| Stockage des fichiers uploadés | **Stockage objet externe compatible S3** (découplé de l'hébergement), via `django-storages`. Fournisseur = variable d'environnement, jamais codé en dur. |
| Accès aux fichiers de mémoires | **Bucket privé** + **URLs signées à durée de vie courte**, générées côté serveur. Aucun accès public direct. |
| Téléchargement des mémoires | **❌ Interdit, totalement.** Pas de bouton, pas de lien, pas de demande de téléchargement. **Lecture en ligne uniquement.** |
| Indicateur de popularité | **Nombre de vues** (objectif, non manipulable). ❌ Pas d'étoiles / notation. |

---

## 1. Page d'accueil — Identité de l'établissement

> **Nom officiel :** **École de Santé Félix Houphouët-Boigny Mali**
> (« Mali » directement à la fin, sans « du ». Graphie « Houphouët-Boigny » à confirmer si l'école l'écrit autrement.)

### Objectif
Inscrire le nom complet de l'établissement (pas de sigle) et présenter les annexes sous le nom.

### Implémentation attendue
- Le `<h1>` du hero affiche **« École de Santé Félix Houphouët-Boigny Mali »**, écrit intégralement (bon pour le SEO et la crédibilité).
- **Conserver le défilement des annexes déjà en place**, en le **repositionnant sous le nom** (et non à côté).
- Rendre ce défilement **pausable** au survol / au focus (accessibilité WCAG : tout mouvement doit pouvoir s'arrêter).
- La liste des annexes reste **dynamique** (gérée en base / admin, pas codée en dur).

### Critères d'acceptation
- [ ] Nom complet visible et correct dans le `<h1>`.
- [ ] Annexes affichées sous le nom.
- [ ] Défilement pausable.
- [ ] Annexes alimentées dynamiquement.

---

## 2. Espace Mémoires — nouvelle application Django

> Module à part entière (app `memoires`) : dépôt côté Super Admin → publication automatique côté public. **Consultation en ligne seule, jamais de téléchargement.**

### 2.1 Objectif
Permettre la consultation en ligne des mémoires (Licence, Master, …), proprement présentés et stylisés, sans possibilité de téléchargement ni de copie facile.

### 2.2 Modèle `Memoire`
- `titre`
- `auteur(s)`
- `encadreur`
- `filiere` / `departement`
- `niveau` (Licence / Master / …)
- `annee`
- `resume` (abstract — texte riche)
- `mots_cles`
- `fichier_source` (PDF d'origine — stockage privé externe, jamais servi directement)
- `pages_images` (images des pages pré-générées à l'upload — support du visionneur)
- `est_mis_en_avant` (booléen — épinglage éditorial)
- `statut` (brouillon / publié)
- `nombre_vues` (compteur)
- `date_depot`, `date_publication`

> ❌ **Pas de modèle de demande de téléchargement.** Cette fonctionnalité est explicitement écartée.

### 2.3 Écrans
**Page liste (publique)**
- Affiche par mémoire : titre, auteur, filière/niveau, année, **résumé**, nombre de vues.
- Section **« Mis en avant »** (mémoires épinglés) et/ou **« Les plus consultés »**.
- Recherche / filtres (par filière, niveau, année). Pagination.

**Page détail / lecture (publique)**
- Affiche les métadonnées + le **résumé en vrai texte HTML** (sélectionnable, bon pour le SEO et l'accessibilité).
- **Visionneur en ligne du corps du mémoire**, bien designé et stylisé, cohérent avec ESFé Core :
  - rendu **page par page en images** (pas de couche texte → rien à copier),
  - navigation fluide (page suivante/précédente, miniatures éventuelles),
  - **aucun bouton de téléchargement**, aucun lien vers le fichier source.
- Incrémente `nombre_vues` à l'ouverture (avec déduplication raisonnable pour éviter le gonflage).

### 2.4 Distinction résumé / corps
| Élément | Format | Raison |
|---|---|---|
| **Résumé (abstract)** | Texte HTML sélectionnable, indexable | Public, fait pour être lu/trouvé → SEO + accessibilité |
| **Corps du mémoire** | Images de pages (sans texte) | Empêche la copie + permet le filigrane |

### 2.5 Sécurité — non négociable
- **Validation stricte des uploads** : contrôle du **type MIME réel** (pas l'extension seule), **taille maximale**, rejet de tout fichier non conforme.
- **Bucket privé** : aucun fichier en accès public direct.
- **URLs signées** courtes, générées côté serveur à chaque consultation.
- **Filigrane** à l'identité de l'utilisateur connecté sur les pages affichées → traçabilité.
- **Anti-copie** : `user-select: none`, blocage `copy` / `contextmenu`, **et surtout** corps rendu en images (aucun texte sélectionnable à la source).

> **⚠️ Honnêteté technique (à dire au DG) :** aucun blocage navigateur n'est inviolable à 100 % (capture d'écran + OCR, etc.). La stratégie **dissuade fortement** et rend tout contenu **traçable** (filigrane). Ce n'est pas une serrure incassable, et il ne faut pas la présenter comme telle.

### 2.6 Performance & accessibilité
- **Pré-générer les images de pages à l'upload** (côté serveur), pas de rendu lourd à la volée côté client.
- **Lazy loading** page par page dans le visionneur ; **pagination** sur la liste.
- ⚠️ Arbitrage assumé : un corps en images n'est pas lisible par lecteur d'écran ni indexable — le résumé HTML compense partiellement la découvrabilité.

### 2.7 Critères d'acceptation
- [ ] App `memoires` créée, cohérente avec la structure modulaire existante.
- [ ] Dépôt depuis le Super Admin → publication sur le site public.
- [ ] Liste avec résumé, vues, mise en avant, recherche/filtres, pagination.
- [ ] Visionneur en ligne stylisé, page par page, **sans téléchargement**.
- [ ] Bucket privé + URLs signées + filigrane + validation des uploads.
- [ ] Compteur de vues fonctionnel.

---

## 3. Pages légales — Mentions légales, Confidentialité, Cookies

### Objectif
Mettre en place des pages légales sérieuses et une gestion des cookies conforme.

### Implémentation attendue
- Pages **éditables depuis l'administration** (le texte juridique évolue → pas de redéploiement à chaque correction).
- **Bannière de consentement réellement conforme** : les cookies **non essentiels** (analytics, etc.) ne sont **pas déposés avant** le consentement. (Erreur courante : afficher la bannière mais déposer les cookies quand même → non conforme.)
- **Ancrage juridique malien** : se référer au cadre malien de protection des données à caractère personnel et à l'autorité compétente, pas à un simple copier-coller du RGPD européen.

### À fournir par Mohamed
- Coordonnées légales de l'éditeur / hébergeur.
- Liste réelle des cookies / traceurs utilisés.

### Critères d'acceptation
- [ ] Pages mentions légales, confidentialité, cookies éditables en admin.
- [ ] Cookies non essentiels bloqués tant que pas de consentement.

---

## 4. Architecture technique transversale (stockage)

- **`django-storages`** sur un fournisseur **compatible S3** ; coder contre l'API S3 → fournisseur interchangeable via configuration.
- **Buckets privés** + accès par **URLs signées** côté serveur.
- Privilégier un fournisseur avec **CDN / edge mondial** ou **région européenne** (latence réduite vers le Mali).
- **Décision fournisseur : en cours.** Contrainte = mode de paiement accessible depuis le Mali. Note : l'object storage est facturé à l'usage ; le paiement annuel à capacité fixe n'existe qu'en « reserved capacity » grands volumes (surdimensionné). Alternative possible : « storage box » à prix fixe facturable à l'année. À trancher séparément.

---

## 5. Backlog priorisé

| Priorité | Tâche | Effort | Impact |
|---|---|---|---|
| 🔴 Haute | App `memoires` : modèle, admin Super Admin, upload sécurisé, stockage S3 privé | Élevé | Élevé |
| 🔴 Haute | Visionneur en ligne (images page par page + filigrane + URLs signées + anti-copie) | Élevé | Élevé |
| 🟠 Moyenne | Page d'accueil : nom complet + annexes sous le nom (dynamiques, pausables) | Faible | Moyen |
| 🟠 Moyenne | Liste mémoires : recherche/filtres, vues, mise en avant, pagination | Moyen | Moyen |
| 🟡 Normale | Pages légales éditables + bannière cookies conforme | Moyen | Conformité |

---

## 6. À fournir par Mohamed (non bloquant pour démarrer)

1. Confirmation de la graphie exacte du nom si l'école l'écrit différemment.
2. Coordonnées légales de l'éditeur + liste des cookies réellement utilisés.
3. Fournisseur de stockage retenu (selon paiement accessible depuis le Mali).

---

## 7. Système de gestion — À COMPLÉTER

> Réservé aux améliorations du DG sur le **système de gestion académique** (étudiants/enseignants, LMD, notes, finances, messagerie, bibliothèque, visioconférence, assistant IA…).
> À détailler au prochain échange, avec la même grille : objectif → implémentation → sécurité/perf → critères d'acceptation.
