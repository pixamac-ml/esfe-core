# Diagrammes d'architecture UI

## Public et portail

```text
base.html / PublicShell             ui/system_base.html / AppShell
|-- Navbar publique                |-- AppSidebar
|-- Contenu public                 |-- AppTopbar
`-- Footer public                  |-- Workspace
                                    `-- Overlays

             aucune inclusion ou navigation croisée implicite
```

## Vue générale

```text
+------------------------------------------------------------+
| BACKEND METIER                                             |
| modèles | services | permissions | annexe | calculs        |
+-----------------------------+------------------------------+
                              |
                              v
+------------------------------------------------------------+
| SERVICES DE PRESENTATION                                   |
| navigation | préparation KPI | statuts | contextes          |
+-----------------------------+------------------------------+
                              |
                              v
+------------------------------------------------------------+
| DASHBOARD METIER                                           |
| vue | template principal | sections métier                 |
+-----------------------------+------------------------------+
                              |
                              v
+------------------------------------------------------------+
| COMPOSANTS METIER                                          |
| notes | planning | paiements | inscriptions | documents     |
+-----------------------------+------------------------------+
                              | compose
                              v
+------------------------------------------------------------+
| UI CORE                                                    |
| layout | navigation | data_display | forms | feedback       |
| overlays                                                   |
+-----------------------------+------------------------------+
                              | compose
                              v
+------------------------------------------------------------+
| ATOMS / FORM CONTROLS                                      |
| button | icon | input | label | avatar | spinner            |
+------------------------------------------------------------+
```

## Dépendances

```text
Vue Django --------> Services métier
     |-------------> Services de présentation ----> accounts.access
     `-------------> Composants métier
                           |
                           v
                         UI Core --------> Atoms / contrôles

Interdit:
UI Core -X-> modèles / ORM / accounts.access / apps métier
Atoms   -X-> UI Core / composants métier / backend
```

## Cycle de rendu

```text
Requête HTTP
    |
middleware et politique d'accès
    |
vue + services métier (querysets filtrés par annexe)
    |
service de présentation (navigation et contrats UI)
    |
contexte prêt à afficher
    |
template dashboard
    |
composants métier -> UI Core -> atoms
    |
HTML accessible et responsive
    |
HTMX met à jour une zone métier / Alpine gère l'état local
```

## Composition d'un dashboard

```text
AppShell
|-- AppSidebar <- groupes autorisés préparés
|-- AppTopbar  <- contexte générique et actions
`-- Workspace
    |-- Breadcrumb
    |-- PageHeader
    |-- ContentGrid
    |   `-- StatCard x N
    |-- PageSection
    |   |-- Panel
    |   |   `-- Widget métier
    |   `-- DataTable / EmptyState
    `-- Modal / Drawer / Toast / Alert
```

## Migration

```text
Phase 1       inventaire + fondation additive
    |
Phase 1.5     domaines techniques + contrats + audits
    |
Phase 1.75    shell interne + catalogue interactif + HTMX + scripts
    |
Phase 2       Directeur des Études uniquement
    |
validation    métier + annexe + HTMX + visuel + accessibilité
    |
pilotes suivants, un dashboard à la fois
    |
adaptateurs -> zéro référence -> dépréciation -> suppression
```

## Pilote Directeur des Études

```text
/portal/dashboard/
        |
        v
portal_dashboard -> position + scope -> services métier filtrés par annexe
        |                                      |
        |                                      v
        `----------------> director_dashboard_presentation
                                      |
                                      v
portal/app_base.html -> ui_core.app_shell
                       |-- ui_core.app_sidebar <- navigation autorisée
                       |-- ui_core.app_topbar  <- contexte + notifications
                       `-- #director-workspace
                              |-- accueil UI Core
                              `-- 7 sections académiques conservées
                                      |
                                      v
                          HTMX innerHTML, sans remplacer le shell
```

Les contenus chargés dans `#director-modal-content` et
`#director-drawer-content` restent produits par les vues métier. Les composants
`ui_core.modal`, `ui_core.drawer` et `ui_core.confirm_dialog` fournissent uniquement
le comportement d'overlay commun.
