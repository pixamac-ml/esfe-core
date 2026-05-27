# DOCUMENTATION COMPLÈTE — DASHBOARD RESPONSABLE MARKETING DIGITAL ESFE

# ÉCOLE DE SANTÉ FÉLIX HOUPHOUËT-BOIGNY (ESFE)

---

# OBJECTIF DU DOCUMENT

Ce document sert de documentation métier, technique, UX et architecturelle pour permettre à Codex de développer entièrement le dashboard du Responsable Marketing Digital dans ESFE Core.

Le document doit être considéré comme une référence principale.

Le but n’est pas simplement de créer un dashboard esthétique.

Le but est de construire un véritable centre de communication institutionnelle et marketing capable de gérer :

- la communication interne,
- les annonces,
- les campagnes,
- les événements,
- les notifications,
- les emails,
- les workflows de diffusion,
- les audiences,
- les prospects,
- les médias,
- les planifications,
- les campagnes WhatsApp et email,
- les communications multi-annexes.

---

# IMPORTANT

Le dashboard marketing est GLOBAL.

Contrairement à d’autres rôles :

- il n’est PAS limité à une annexe,
- il supervise toutes les annexes,
- il peut cibler une annexe spécifique,
- il peut cibler plusieurs annexes,
- il peut cibler l’ensemble du réseau ESFE.

---

# RÈGLE FONDAMENTALE

TOUT DOIT ÊTRE FILTRABLE PAR :

- annexe,
- formation,
- cycle,
- classe,
- rôle,
- audience,
- type utilisateur.

Cette règle est OBLIGATOIRE.

---

# STACK TECHNIQUE VALIDÉE

## Backend

- Django
- PostgreSQL
- Redis
- Django Channels
- Celery
- HTMX
- Alpine.js
- Tailwind CSS

---

# COMMUNICATION EXTERNE V1

## Solution retenue

Brevo.

Brevo servira pour :

- emails,
- campagnes emailing,
- gestion prospects,
- automatisations simples,
- WhatsApp plus tard,
- SMS plus tard.

---

# IA

AUCUNE IA EN V1.

Le système doit être intelligent par logique métier.

L’IA viendra dans les versions futures.

---

# OBJECTIF UX

Le dashboard doit ressembler à :

- un centre de pilotage,
- un centre marketing,
- un centre de communication,
- un centre de campagnes.

Le style doit être professionnel.

Inspirations possibles :

- Hubspot,
- Meta Business Suite,
- Notion,
- ClickUp,
- Monday,
- Linear.

---

# IMPORTANT — MAQUETTE

Codex doit utiliser la maquette existante présente dans :

```txt
Mockup/
```

Cette maquette a déjà servi :

- au dashboard DG,
- au dashboard secrétaire.

Le dashboard marketing doit conserver :

- la cohérence visuelle,
- la structure globale,
- la qualité UX,
- les animations,
- les composants.

MAIS il doit être totalement adapté au contexte marketing.

---

# STRUCTURE GLOBALE DU DASHBOARD

Le dashboard doit contenir les sections suivantes :

1. Dashboard principal
2. Communication interne
3. Campagnes externes
4. Bibliothèque média
5. Calendrier marketing
6. Prospects & audiences
7. Notifications & popup
8. Historique diffusion
9. Analytics V1
10. Paramètres marketing

---

# SECTION 1 — DASHBOARD PRINCIPAL

# OBJECTIF

Permettre au responsable marketing d’avoir une vue globale instantanée.

---

# KPI PRINCIPAUX

Le dashboard principal doit afficher :

- campagnes actives,
- annonces actives,
- emails envoyés,
- campagnes planifiées,
- popup actifs,
- prospects récents,
- taux ouverture email,
- annexes les plus actives,
- événements à venir,
- campagnes urgentes.

---

# WIDGETS

## Widget campagnes

Affiche :

- nom campagne,
- statut,
- annexe ciblée,
- date diffusion,
- progression.

---

## Widget calendrier

Affiche :

- campagnes à venir,
- événements,
- rappels,
- annonces programmées.

---

## Widget notifications urgentes

Affiche :

- annonces critiques,
- urgences DG,
- communications prioritaires.

---

## Widget activité récente

Affiche :

- annonces créées,
- emails envoyés,
- campagnes terminées,
- médias ajoutés.

---

# SECTION 2 — COMMUNICATION INTERNE

# OBJECTIF

Permettre au responsable marketing :

- de créer des annonces,
- de diffuser des notifications,
- de planifier,
- de gérer les popup,
- de cibler des audiences.

---

# TYPES D’ANNONCES

Le système doit gérer :

- événements,
- annonces générales,
- urgences,
- rappels,
- informations académiques,
- communications DG,
- suspension cours,
- campagnes internes.

---

# FORMULAIRE ANNONCE

Le formulaire doit contenir :

## Informations générales

- titre,
- type,
- priorité,
- statut,
- auteur,
- date début,
- date fin.

---

## Contenu

Utiliser un éditeur riche professionnel.

Le responsable marketing doit pouvoir :

- écrire,
- mettre en gras,
- insérer images,
- ajouter vidéos,
- ajouter liens,
- ajouter boutons,
- ajouter fichiers.

---

# IMPORTANT

Le responsable marketing crée les affiches en externe :

- Photoshop,
- Illustrator,
- Canva,
- Premiere Pro,
- After Effects.

Puis il importe les médias dans ESFE.

Le dashboard ne sert PAS à créer les affiches.

Le dashboard sert à :

- organiser,
- diffuser,
- planifier,
- réutiliser.

---

# CIBLAGE

L’annonce doit pouvoir cibler :

- une annexe,
- plusieurs annexes,
- tout ESFE,
- une formation,
- une classe,
- un cycle,
- un rôle.

---

# CANAUX DISPONIBLES

V1 :

- popup dashboard,
- notification dashboard,
- email.

V1.5 :

- WhatsApp,
- SMS.

---

# PLANIFICATION

Le responsable marketing doit pouvoir :

- envoyer immédiatement,
- planifier,
- programmer récurrence,
- définir expiration.

Celery doit gérer la planification.

---

# POPUP DASHBOARD

Le système doit pouvoir afficher un popup au chargement dashboard.

---

# Exemple

```txt
🎉 Journée Culturelle Jiribougou
30 juillet 2026

Concours • Défilé • Spectacles
```

---

# IMPORTANT

Les popup doivent être :

- responsive,
- rapides,
- animés,
- non bloquants sauf urgence.

---

# SECTION 3 — CAMPAGNES EXTERNES

# OBJECTIF

Permettre au responsable marketing de préparer et diffuser des campagnes externes.

---

# COMMUNICATION EXTERNE V1

V1 utilisera Brevo.

Le système doit :

- préparer les campagnes,
- segmenter les audiences,
- envoyer les emails,
- gérer les prospects,
- préparer WhatsApp plus tard.

---

# IMPORTANT

Le système ESFE n’est PAS un clone de Facebook Ads.

Le dashboard marketing est un orchestrateur.

Brevo est le moteur diffusion.

---

# CAMPAGNES DISPONIBLES

- campagne inscriptions,
- relance prospects,
- rappel événements,
- campagnes newsletters,
- campagnes promotions formations,
- campagnes journées portes ouvertes.

---

# FORMULAIRE CAMPAGNE

## Champs

- nom campagne,
- objectif,
- annexe ciblée,
- audience,
- canal,
- date début,
- date fin,
- budget prévisionnel,
- médias,
- contenu.

---

# AUDIENCES

Le système doit pouvoir récupérer :

- prospects,
- anciens leads,
- formulaires inscriptions,
- newsletter,
- anciens étudiants.

---

# SECTION 4 — BIBLIOTHÈQUE MÉDIA

# OBJECTIF

Centraliser tous les médias marketing.

---

# TYPES DE MÉDIAS

- affiches,
- vidéos,
- logos,
- PDF,
- reels,
- flyers,
- jingles.

---

# FONCTIONNALITÉS

- upload,
- recherche,
- tags,
- filtres,
- prévisualisation,
- archivage,
- réutilisation.

---

# SECTION 5 — CALENDRIER MARKETING

# OBJECTIF

Visualiser toutes les campagnes et événements.

---

# ÉLÉMENTS DU CALENDRIER

- campagnes,
- événements,
- popup programmés,
- emails programmés,
- urgences,
- rappels.

---

# UX

Le calendrier doit être :

- interactif,
- responsive,
- fluide,
- compatible drag-and-drop.

---

# SECTION 6 — PROSPECTS & AUDIENCES

# OBJECTIF

Permettre la gestion marketing des audiences.

---

# LEADS

Un prospect doit contenir :

- nom,
- email,
- téléphone,
- ville,
- annexe intéressée,
- formation intéressée,
- source.

---

# SOURCES LEADS

- site web,
- formulaire,
- newsletter,
- import CSV,
- événements,
- campagnes.

---

# SECTION 7 — NOTIFICATIONS TEMPS RÉEL

# OBJECTIF

Diffuser les notifications instantanément.

---

# STACK

- Redis,
- Django Channels,
- WebSocket.

---

# WORKFLOW

1. annonce créée,
2. Celery prépare,
3. Redis diffuse,
4. Channels push,
5. popup affiché.

---

# SECTION 8 — HISTORIQUE

Le système doit historiser :

- campagnes,
- notifications,
- emails,
- popup,
- erreurs diffusion,
- actions utilisateur.

---

# SECTION 9 — ANALYTICS V1

V1 reste simple.

---

# KPIs

- emails envoyés,
- taux ouverture,
- popup vus,
- campagnes actives,
- audiences ciblées.

---

# SECTION 10 — PARAMÈTRES

# OBJECTIF

Configurer le module marketing.

---

# PARAMÈTRES DISPONIBLES

- configuration Brevo,
- expéditeur email,
- templates,
- couleurs popup,
- durée popup,
- comportements notifications.

---

# MODÈLES DJANGO

# Announcement

Annonce institutionnelle.

---

# Campaign

Campagne marketing.

---

# CampaignAudience

Audience campagne.

---

# MarketingMedia

Médias marketing.

---

# ProspectLead

Prospect marketing.

---

# DispatchLog

Historique diffusion.

---

# ScheduledCampaign

Campagne programmée.

---

# SERVICES

# campaign_service.py

Responsable :

- campagnes,
- segmentation,
- audiences,
- planification.

---

# notification_service.py

Responsable :

- popup,
- dashboard,
- temps réel.

---

# brevo_service.py

Responsable :

- emails,
- campagnes,
- contacts,
- API Brevo.

---

# media_service.py

Responsable :

- upload,
- compression,
- archivage,
- optimisation.

---

# RÈGLES ARCHITECTURE ESFE

OBLIGATOIRE :

- logique métier dans services,
- selectors dédiés,
- vues fines,
- HTMX,
- composants réutilisables,
- filtrage annexe.

---

# INTERDICTIONS

❌ logique métier dans templates
❌ duplication notifications
❌ pages lourdes inutiles
❌ rechargements complets inutiles

---

# CAS CONCRET 1 — JOURNÉE CULTURELLE

## Situation

Jiribougou organise une journée culturelle.

---

# Workflow

Le responsable marketing crée :

- titre,
- affiche,
- popup,
- email,
- cible Jiribougou uniquement.

---

# Résultat

Seuls :

- étudiants Jiribougou,
- staff Jiribougou,

reçoivent la notification.

---

# CAS CONCRET 2 — RAMADAN

Le système diffuse :

- popup,
- dashboard,
- email.

---

# CAS CONCRET 3 — CAMPAGNE INSCRIPTIONS

Le système récupère les prospects.

Puis Brevo diffuse les emails.

---

# CAS CONCRET 4 — URGENCE DG

Popup critique.

Notification sonore.

Diffusion immédiate.

---

# UX GLOBALE

Le dashboard doit être :

- premium,
- fluide,
- rapide,
- responsive,
- orienté workflow,
- orienté productivité.

---

# COMPOSANTS UI ATTENDUS

- sidebar,
- cards,
- tables,
- timeline,
- popup,
- modals,
- filtres HTMX,
- badges,
- statistiques.

---

# PERFORMANCE

Le système doit être pensé pour :

- plusieurs annexes,
- milliers utilisateurs,
- temps réel,
- campagnes massives,
- notifications simultanées.

---

# OBJECTIF FINAL

Créer un véritable centre marketing institutionnel ESFE.

Le dashboard doit permettre :

- communication,
- planification,
- segmentation,
- diffusion,
- campagnes,
- pilotage,
- suivi.

---

# FIN DOCUMENT

