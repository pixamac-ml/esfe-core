# Cahier des charges — Carte étudiant & authentification par carte
**Projet : ESFé Core** · École de Santé Félix Houphouët-Boigny — Annexe Bamako Moribabougou
**Destinataire : Claude Code** · Stack : Django, HTMX/AJAX, JavaScript, WebRTC, Tailwind CSS

---

## 0. Contexte et objectif

ESFé Core est une plateforme Django de gestion académique (architecture modulaire). Ce document spécifie trois chantiers liés, à implémenter dans l'ordre indiqué en section 6 :

1. **Génération de cartes étudiants** professionnelles (recto/verso), à partir de la maquette HTML fournie (`carte_etudiant_esfe_v2.html`).
2. **Authentification au login par scan de la carte** (QR + code PIN), en *complément* du formulaire de connexion existant — jamais en remplacement.
3. **Portail de vérification** de l'authenticité d'une carte (saisie d'un code ou scan → fiche étudiant + statut de validité).

> **Principe directeur, valable partout dans ce document :** *identifier n'est pas authentifier.* Le QR et le code peuvent dire **qui** un étudiant prétend être ; ils ne doivent **jamais**, à eux seuls, **prouver** que c'est bien lui. Toute connexion exige un second facteur (le PIN).

La maquette fournie définit le rendu visuel attendu. Ce cahier des charges porte sur la logique métier, la sécurité et l'intégration Django. Claude Code est libre de proposer des simplifications d'implémentation **tant que les exigences de sécurité des sections 2, 3.4 et 4.4 sont respectées** — celles-ci ne sont pas négociables.

---

## 1. La carte étudiant (génération)

### 1.1 Gabarit
- Format **CR80** : 85,6 × 54 mm, recto + verso.
- Base : le fichier `carte_etudiant_esfe_v2.html` (déjà validé visuellement) à convertir en **template Django**.
- L'emblème de l'école est intégré dans la maquette (pastille blanche dans l'en-tête).

### 1.2 Champs et variables
Seules les **coordonnées de l'établissement** sont fixes. Tout le reste vient de la base :

| Élément carte | Source |
|---|---|
| Nom complet | `etudiant.nom` |
| Photo | `etudiant.photo` |
| Matricule (format `ESFE-00000`) | `etudiant.matricule` |
| Date de naissance | `etudiant.date_naissance` |
| Formation | `etudiant.formation` |
| Classe / niveau | `etudiant.classe` |
| Groupe sanguin | `etudiant.groupe_sanguin` (voir 1.6) |
| Année académique | `carte.annee` |
| Date d'expiration | `carte.date_expiration` |
| QR | généré (voir 1.4 et section 2) |
| Code de vérification (verso) | généré (voir section 2) |

Coordonnées fixes (verso) : `universite@univ-fhb-mali.org` · BP 00223 · Rn27, face de la pharmacie Diamanatigui — Bamako Moribabougou · Contact annexe : 77 04 44 81.

### 1.3 Génération PDF (impression)
- Utiliser **WeasyPrint** (rendu déterministe côté serveur), pas une capture navigateur.
- **Polices hébergées en local** (`static/fonts/`) et déclarées en `@font-face`. WeasyPrint gère mal les `@import` Google Fonts distants : sans polices locales, le rendu serveur diffère de l'aperçu. Polices : Archivo, Inter, JetBrains Mono.
- Conserver `@page { size: 85.6mm 54mm; margin: 0; }`.
- **Ajouter au CSS d'impression** : `print-color-adjust: exact; -webkit-print-color-adjust: exact;` — sinon les navigateurs suppriment les fonds (bandeau marine, guilloché) à l'impression. **Point critique de production.**

### 1.4 Génération du QR
- Côté serveur avec `qrcode` + `Pillow`, injecté en **data-URI base64** dans le template (aucun appel à une API externe : fiabilité + vie privée).
- **Contenu du QR** : voir section 2 (URL de vérification contenant un token signé). Ne jamais encoder d'identifiants en clair.
- Niveau de correction d'erreur recommandé : `ERROR_CORRECT_M` (lisible même légèrement abîmé).

### 1.5 Filigrane guilloché
- Garder l'opacité à **4–6 %**, traits ≥ 0,7 px à taille réelle.
- **Test d'impression obligatoire** sur l'imprimante PVC cible avant production en série (risque de moiré sur motifs fins). Si problème : alléger ou réserver au recto.

### 1.6 Contrôle de la photo
À l'upload, refuser les images non conformes (photos d'animaux, paysages, etc.) :
- Vérifier le **ratio portrait** et la **présence d'un visage** (par ex. détection légère côté serveur).
- En cas d'échec : message clair « Photo non conforme. Présentez-vous à l'informaticien pour une photo d'identité. »
- Ne pas bloquer le reste de la fiche pour autant ; la photo peut rester à compléter.

### 1.7 Nouveau champ : groupe sanguin
Ce champ **n'existe pas encore** ; les étudiants déjà en base ne l'ont pas. À ajouter sans casser l'existant :

```python
class GroupeSanguin(models.TextChoices):
    A_PLUS = "A+", "A+";  A_MOINS = "A-", "A−"
    B_PLUS = "B+", "B+";  B_MOINS = "B-", "B−"
    AB_PLUS = "AB+", "AB+";  AB_MOINS = "AB-", "AB−"
    O_PLUS = "O+", "O+";  O_MOINS = "O-", "O−"

# Sur le modèle Etudiant :
groupe_sanguin = models.CharField(
    max_length=3, choices=GroupeSanguin.choices, blank=True, default=""
)
```
- **`blank=True` + `default=""`**, jamais `null=True` sur un CharField (convention Django). Les étudiants existants ne plantent pas : valeur vide.
- Une seule migration, sans risque (champ facultatif).
- Ajouter le `Select` au formulaire de création/édition (non obligatoire pour l'instant ; à rendre obligatoire pour les *nouvelles* inscriptions si souhaité).
- **Sur la carte** : si vide → afficher « Non renseigné » et **masquer la pastille rouge**.
- **Donnée de santé** : tant que le groupe n'est pas vérifié par un document à l'inscription, conserver la mention « déclaré » sur la carte. Ne jamais l'afficher sur le portail de vérification public (section 3).

---

## 2. Socle de sécurité — ce que le QR et le code encodent (LE POINT FONDATEUR)

C'est la base commune au login et au portail de vérification. À implémenter en premier après le champ groupe sanguin.

### 2.1 Token signé (HMAC)
- **Charge utile (payload)** : `matricule | annee_academique | code_annexe`.
  Ne **pas** y mettre le statut (révoqué/expiré) : le statut change dans le temps et se vérifie en base.
- **Signature** : `HMAC-SHA256(payload, CARD_SIGNING_KEY)`.
- **Format token** (façon JWT simplifié) : `v1.<payload_b64url>.<signature_b64url>`. Le préfixe `v1` permet une **rotation de clé** future.

```python
import hmac, hashlib, base64
from django.conf import settings

def _b64(b): return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

def signer_carte(matricule, annee, annexe):
    payload = f"{matricule}|{annee}|{annexe}".encode()
    sig = hmac.new(settings.CARD_SIGNING_KEY.encode(), payload, hashlib.sha256).digest()
    return f"v1.{_b64(payload)}.{_b64(sig)}"
```

### 2.2 Clé secrète
- Utiliser une **clé dédiée** `CARD_SIGNING_KEY`, en variable d'environnement, **distincte de `SECRET_KEY`** Django (séparation des usages, rotation indépendante).
- Ne jamais la committer ; la charger via l'environnement / un gestionnaire de secrets.

### 2.3 Ce que le QR encode
- Le QR encode une **URL de vérification** : `https://<domaine>/carte/v/<token>`.
- Avantage : n'importe quelle app caméra (téléphone d'un agent) ouvre directement la page de vérification ; et la page de login peut extraire le `<token>` de l'URL pour le login étudiant. **Un seul token, deux usages.**

### 2.4 Code de vérification lisible (verso)
- **Dérivé du même HMAC** : prendre les premiers octets de la signature, encoder en base32/hex, formater en groupes lisibles → ex. `3F9A-7C21-D8E4`.
- Avantages : non devinable (dépend de `CARD_SIGNING_KEY`), cohérent avec le token, vérifiable côté serveur (on recalcule et on compare).
- **Limite assumée** : tronqué = moins d'entropie. Il sert à la **vérification d'authenticité avec rate limiting** (section 3), **pas** à l'authentification forte. À documenter clairement dans le code.

### 2.5 Statut, expiration, révocation
Modèle `CarteEtudiant` (voir section 5) avec un champ `statut` : `active` / `revoquee` / `perdue` / `expiree`, et `date_expiration`.
**Une carte est valide si et seulement si :** signature HMAC correcte **ET** `statut == active` **ET** `date_expiration >= today`. Les trois conditions, toujours.

---

## 3. Portail de vérification (le plus simple — à faire après le socle)

### 3.1 Objectif
Permettre à un tiers (agent à l'entrée, administration, hôpital de stage) de confirmer qu'une carte est authentique et en cours de validité — **sans scanner**, ou avec un simple scan caméra.

### 3.2 Flux
- **Saisie manuelle** du code de vérification, **ou** scan du QR (ouvre l'URL `/carte/v/<token>`).
- Le serveur vérifie (signature + statut + expiration) puis affiche une **fiche** : photo, nom, matricule, formation, classe, statut (Actif / Suspendu / Diplômé), validité.
- Si invalide/expirée/révoquée : message explicite (« Carte non valide pour cette annexe », « Carte expirée », etc.).

### 3.3 Données affichées
Photo, nom, matricule, formation, classe, statut, validité. **Jamais** de données sensibles : pas de date de naissance complète si évitable, **pas de groupe sanguin**, pas de coordonnées personnelles.

### 3.4 Sécurité (non négociable)
- **Rate limiting fort** sur la saisie de code (anti-énumération : empêcher de balayer matricules/codes).
- Ne **jamais** exposer de liste ni d'API de recherche en masse.
- **Journaliser** les vérifications (qui, quand, quel code).
- Réponses minimales : valide/invalide + champs strictement nécessaires.

---

## 4. Authentification au login par scan (le plus complexe — en dernier)

### 4.1 UX
- Le formulaire de connexion **classique reste inchangé**.
- Ajouter un **bouton de bascule** « Se connecter avec ma carte » qui déplie le mode scan (idéalement via HTMX, sans recharger la page).

### 4.2 Caméra navigateur
- Accès caméra via **`getUserMedia` (WebRTC)** — déjà maîtrisé sur le projet (visioconférence).
- **HTTPS obligatoire** : `getUserMedia` est bloqué en HTTP (prévoir un certificat même en dev).
- Décodage QR côté client : librairie **`qr-scanner` (nimiq, basée sur jsQR)** ou l'API native **`BarcodeDetector`** (Chrome/Edge).

### 4.3 Flux complet
1. L'étudiant clique « Se connecter avec ma carte » → la caméra s'ouvre, message « Rapprochez votre carte de la caméra ».
2. Décodage du QR → extraction du `token` depuis l'URL.
3. `POST` du token au serveur (protégé **CSRF**).
4. Le serveur vérifie **signature + statut + expiration** (section 2.5).
   - Si **invalide** → refus immédiat : « Votre carte n'est pas valide. Munissez-vous d'une carte en cours de validité. » Pas d'accès.
   - Si **valide** → afficher le champ **PIN**.
5. L'étudiant saisit son **PIN** → vérification → ouverture de la **session Django** standard, redirection dashboard.

### 4.4 Sécurité (non négociable)
- **Le QR seul ne connecte jamais.** Le PIN est le second facteur obligatoire (possession de la carte + connaissance du PIN).
- **PIN stocké haché** avec le hasher Django (`make_password` / `check_password`), jamais en clair, jamais dans le QR.
- **Rate limiting + verrouillage temporaire** après N tentatives de PIN échouées.
- Carte perdue → passer son statut à `perdue`/`revoquee` en base : elle cesse immédiatement de fonctionner (login *et* vérification).
- Aucune donnée d'authentification transmise en clair côté client.

### 4.5 À décider (proposer une option)
- **Définition initiale du PIN** : attribué par l'administration à l'émission, ou défini par l'étudiant à la première connexion via un autre canal ? À trancher avec l'équipe.

---

## 5. Modèles de données (récapitulatif)

```python
class Etudiant(models.Model):
    # ... champs existants ...
    groupe_sanguin = models.CharField(
        max_length=3, choices=GroupeSanguin.choices, blank=True, default=""
    )
    pin_hash = models.CharField(max_length=128, blank=True, default="")  # PIN haché

class CarteEtudiant(models.Model):
    etudiant = models.ForeignKey(Etudiant, on_delete=models.CASCADE, related_name="cartes")
    annee = models.CharField(max_length=9)            # ex. "2026-2027"
    code_annexe = models.CharField(max_length=20)     # ex. "BKO-MORIBA"
    date_emission = models.DateField(auto_now_add=True)
    date_expiration = models.DateField()
    statut = models.CharField(max_length=10, default="active")  # active/revoquee/perdue/expiree
    token_version = models.CharField(max_length=4, default="v1")
```
> `pin_hash` peut aussi vivre dans un modèle séparé si tu veux découpler l'authentification. À l'appréciation de Claude Code.

---

## 6. Ordre d'implémentation recommandé

1. **Champ groupe sanguin** (modèle + migration + formulaire + affichage carte). Petit, sans risque.
2. **Socle de sécurité** (utilitaires `signer_carte` / `verifier_token` / génération du code lisible + clé dédiée). Fondation des étapes 4 et 5.
3. **Génération de la carte** (template Django depuis la maquette + QR + PDF WeasyPrint + polices locales + `print-color-adjust`).
4. **Portail de vérification** (lecture seule + rate limiting).
5. **Scan au login** (caméra + vérification + PIN + session).

---

## 7. Exigences transverses (rappel)

- Code Django propre, respect des conventions (pas de `null=True` sur CharField, `TextChoices`, migrations atomiques).
- Pas de hacks ni de solutions temporaires ; architecture évolutive.
- Sécurité d'abord : signature HMAC, clé dédiée, PIN haché, rate limiting, CSRF, HTTPS, statut/révocation.
- Le QR/code n'expose jamais d'identifiants en clair ni de données sensibles.
- Avant toute modification de modèle, vérifier l'impact sur les données existantes.

---

## 8. Suggestions d'amélioration — Claude Code

> Ces suggestions sont complémentaires au cahier des charges. Elles n'altèrent aucune exigence de sécurité.

### 8.1 PIN : définition à la première connexion par l'étudiant

**Recommandation** : l'étudiant définit lui-même son PIN lors de la remise de carte, via un lien à usage unique (token OTP, 15 min de validité) envoyé par email ou SMS. L'administration n'a jamais accès au PIN en clair — elle peut seulement le réinitialiser (nouveau lien).

**Pourquoi** : c'est plus sûr qu'un PIN attribué (risque de fuite côté admin) et plus simple que deux flux séparés. Le lien de définition peut aussi servir au cas "PIN oublié".

**Implémentation minimale** :
```python
# Nouveau modèle (simple, pas de dépendance externe)
class PinSetupToken(models.Model):
    etudiant = models.ForeignKey(Student, on_delete=models.CASCADE)
    token = models.CharField(max_length=64, unique=True)  # secrets.token_urlsafe(32)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
```
Vue publique `/carte/pin/setup/<token>/` : affiche formulaire PIN + confirmation, invalide le token après usage.

---

### 8.2 `VerificationLog` — purge automatique RGPD

Le log contient des IPs (donnée personnelle). Prévoir une tâche de purge :
```python
# À lancer via cron ou manage.py command
VerificationLog.objects.filter(
    created_at__lt=timezone.now() - timedelta(days=90)
).delete()
```
Ou ajouter un champ `anonymized_at` pour supprimer l'IP tout en conservant les statistiques.

---

### 8.3 Vue admin de gestion des cartes

Ajouter dans `students/admin.py` :
```python
@admin.register(CarteEtudiant)
class CarteEtudiantAdmin(admin.ModelAdmin):
    list_display = ["etudiant", "annee", "statut", "date_expiration", "is_valide"]
    list_filter = ["statut", "annee"]
    actions = ["revoquer_cartes"]

    @admin.action(description="Révoquer les cartes sélectionnées")
    def revoquer_cartes(self, request, queryset):
        queryset.update(statut="revoquee")
```
Permet à l'informaticien de gérer les cartes perdues/révoquées sans passer par le shell.

---

### 8.4 Détection de visage à l'upload photo

Le cahier des charges section 1.6 mentionne la détection côté serveur. Pour rester léger sans ML :
- Utiliser `opencv-python-headless` + `haarcascade_frontalface_default.xml` (CPU only, ~200ms).
- En cas d'indisponibilité de la librairie, dégrader silencieusement (accepter la photo, logger un avertissement) — la conformité reste à la charge du secrétariat.
- **Ne jamais bloquer l'inscription** pour cette raison : `blank=True` sur `photo`, formulaire enregistré même sans photo valide.

---

### 8.5 Polices locales WeasyPrint — procédure de déploiement

Les polices Archivo, Inter et JetBrains Mono doivent être téléchargées et déposées dans `static/fonts/` avant la mise en production :

```bash
# Télécharger depuis Google Fonts (CDN officiel, licence OFL)
# Archivo : https://fonts.google.com/specimen/Archivo
# JetBrains Mono : https://www.jetbrains.com/legalforms/mono/
mkdir -p static/fonts/
# Ensuite : python manage.py collectstatic
```

En développement, le template carte se dégrade gracieusement sur `Arial / Courier New` (déclarés en fallback dans le CSS).

---

### 8.6 Impression PVC — point critique

Avant toute impression en série, tester impérativement sur l'imprimante PVC cible (Zebra ZXP, Fargo, etc.) :
1. **Couleurs** : vérifier que `print-color-adjust: exact` est bien respecté par le driver.
2. **Moiré guilloché** : si visible, augmenter l'opacité à 6 % ou réduire la densité des chemins SVG.
3. **Résolution QR** : imprimer à ≥ 300 DPI ; le QR doit être lisible à 15 cm avec un téléphone standard.
4. **Lamination** : après lamination, re-tester le scan QR (certains films réduisent la lisibilité).

---

### 8.7 Rotation de clé `CARD_SIGNING_KEY`

Quand la clé doit changer (compromission, rotation annuelle) :
1. Générer une nouvelle clé, ajouter `CARD_SIGNING_KEY_V2` dans `.env`.
2. Modifier `signer_carte` pour émettre en `v2`, et `verifier_token` pour accepter `v1` ET `v2` pendant la période de transition.
3. Régénérer toutes les cartes actives (script `manage.py regenerer_cartes`).
4. Supprimer `CARD_SIGNING_KEY_V1` une fois toutes les cartes v1 expirées.

Le préfixe `v1` dans le token a précisément été conçu pour rendre cette opération non destructive.

---

### 8.8 Roadmap suggérée post-présentation

| Priorité | Fonctionnalité | Effort |
|---|---|---|
| 🔴 Immédiat | Générer `CARD_SIGNING_KEY` dans `.env` prod | 5 min |
| 🔴 Immédiat | Télécharger polices locales dans `static/fonts/` | 15 min |
| 🔴 Immédiat | Ajouter `CarteEtudiantAdmin` dans admin Django | 20 min |
| 🟠 Court terme | Flux définition PIN étudiant (section 8.1) | 2h |
| 🟠 Court terme | Vue informaticien : émettre/révoquer une carte | 3h |
| 🟡 Moyen terme | Détection de visage à l'upload (section 8.4) | 4h |
| 🟡 Moyen terme | Purge RGPD automatique des VerificationLog | 1h |
| 🟢 Long terme | jsQR en fallback pour navigateurs sans BarcodeDetector | 2h |
| 🟢 Long terme | Application mobile de vérification (PWA) | — |
