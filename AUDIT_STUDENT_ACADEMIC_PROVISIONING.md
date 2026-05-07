# Audit Student Academic Provisioning

Date: 2026-05-07

## Scope

Analyse des apps demandees:

- `formations/`
- `academics/`
- `admissions/`
- `inscriptions/`
- `students/`
- `payments/`
- `portal/`

Constat de perimetre:

- l'app `academic/` n'existe pas; le perimetre reel est `academics/`
- l'app `users/` n'existe pas; les responsabilites utilisateur/profil sont dans `accounts/`
- l'app `dashboard/` n'existe pas; les dashboards sont portes principalement par `portal/`

## 1. Structure academique actuelle reelle

La structure academique explicite existe deja et elle est relativement propre:

- `formations.Cycle` porte le macro-niveau de cursus: Licence, Master, etc.
- `formations.Programme` porte la formation metier, rattachee a `Cycle`, `Filiere` et `Diploma`
- `admissions.Candidature` porte deja:
  - `programme`
  - `branch`
  - `academic_year` en `CharField`
  - `entry_year` en `PositiveSmallIntegerField`
- `inscriptions.Inscription` porte la relation administrative unique vers la candidature
- `academics.AcademicYear` est la reference academique normalisee des annees
- `academics.AcademicClass` est la brique operationnelle centrale:
  - `programme`
  - `branch`
  - `academic_year`
  - `level` ex. `L1`, `L2`, `L3`, `M1`, `M2`
  - `study_level` ex. `LICENCE`, `MASTER`
- `academics.AcademicEnrollment` est deja le pont officiel entre administratif et academique
- `Semester -> UE -> EC` depend deja directement de `AcademicClass`

Conclusion:

- le systeme n'est pas vide
- la structure cible existe deja presque entierement
- la vraie cle manquante est la fiabilisation de l'affectation automatique vers `AcademicEnrollment`

## 2. Relations deja existantes

### Formation / cycle / niveau

- un etudiant est lie implicitement a sa formation via `Student.inscription.candidature.programme`
- le cycle est derive implicitement via `programme.cycle`
- le niveau n'est pas stocke sur `Student`; il est derive de:
  - `Candidature.entry_year`
  - mapping applicatif `ENTRY_YEAR_TO_LEVEL`
  - puis resolu en `AcademicClass.level`

### Classe / annee academique

- l'etudiant est lie a sa classe et a son annee uniquement via `AcademicEnrollment`
- `AcademicEnrollment` porte deja:
  - `programme`
  - `branch`
  - `academic_year`
  - `academic_class`
  - `student`
  - `inscription`

### Dashboards

- les dashboards etudiants utilisent `get_student_academic_snapshot()`
- les dashboards staff filtrent massivement via `AcademicEnrollment.academic_class`
- dans la pratique, la classe est deja la cle de partition principale de presque tous les usages

## 3. Logique automatique deja existante

### Apres candidature validee

- la candidature acceptee autorise la creation de `Inscription`
- `Candidature` porte deja les donnees necessaires a une future affectation academique:
  - programme
  - branch
  - academic_year
  - entry_year

### Apres inscription validee

- `Inscription.update_financial_state()` fait evoluer les statuts administratifs
- `inscriptions.signals` peut tenter `create_student_after_first_payment(instance)` quand le statut devient `active`
- donc une logique automatique existe deja, mais elle n'est pas l'entree principale du provisioning

### Apres premier paiement valide

- c'est deja le point d'entree metier principal
- `payments.Payment.save()`:
  - met a jour l'etat financier
  - genere le recu PDF
  - declenche `_post_commit_actions()`
- `_post_commit_actions()` appelle `students.services.create_student_after_first_payment`
- `create_student_after_first_payment()` appelle `academics.services.enrollment_service.assign_student_academic_enrollment`

Conclusion:

- la logique automatique existe deja
- elle est deja branchee au bon evenement metier: premier paiement valide
- le point fragile n'est pas l'absence de pipeline, mais la resolution incomplete de la classe academique

## 4. Logique implicite detectee

Le systeme utilise deja la logique implicite suivante:

1. `entry_year` sur candidature represente l'annee d'etude
2. `ENTRY_YEAR_TO_LEVEL` transforme cette annee en niveau academique:
   - `1 -> L1`
   - `2 -> L2`
   - `3 -> L3`
   - `4 -> M1`
   - `5 -> M2`
3. le moteur cherche ensuite une unique `AcademicClass` par:
   - programme
   - branch
   - academic_year
   - level
4. si une seule classe existe, l'affectation academique est creee automatiquement

Autrement dit:

- le systeme considere deja qu'une classe joue le role de niveau contextualise
- il n'y a pas aujourd'hui besoin de dupliquer `level` sur `Student`

## 5. Comment les dashboards filtrent actuellement les donnees

Les dashboards filtrent deja par classe academique, pas par `Student.level` autonome.

Patterns observes:

- `portal.student.widgets.academics.get_student_academic_snapshot()`
  - derive `academic_level` depuis `academic_class.level`
- dashboard etudiant:
  - les cours sont filtres par `enrollment.academic_class`
  - le timetable est derive de la classe
  - le contexte global de dashboard depend de `AcademicEnrollment`
- dashboards direction/surveillant:
  - selection de classe via `AcademicClass`
  - listing des etudiants via `user__academic_enrollments__academic_class`
  - resultats / notes / attendance / schedule / lesson logs tous filtres par `AcademicClass`

Conclusion:

- operationnellement, la classe est deja l'objet pivot
- si l'affectation de classe rate, les dashboards perdent leur contextualisation

## 6. Dependance des UE/EC et semestres aux niveaux

La dependance n'est pas abstraite; elle est concretement portee par `AcademicClass`.

- `Semester` appartient a `AcademicClass`
- `UE` appartient a `Semester`
- `EC` appartient a `UE`
- `ECGrade` verifie que l'EC correspond bien a la classe de l'inscription academique
- `AcademicScheduleEvent`, `LessonLog`, `WeeklyScheduleSlot` verifient tous la coherence de classe

Conclusion:

- les UE/EC/semestres ne dependent pas d'un champ `level` autonome
- ils dependent deja d'une classe academique unique
- donc, oui: la classe joue deja de fait le role de niveau operationnel

## 7. Incoherences detectees

### Incoherence 1: annee academique legacy en string vs reference normalisee

- `Candidature.academic_year` est un `CharField`
- `AcademicEnrollment.academic_year` pointe vers `AcademicYear`
- le code de `AcademicEnrollment.clean()` desactive explicitement le controle de coherence car le legacy est encore en string

Impact:

- l'affectation automatique peut echouer si `AcademicYear.name` ne correspond pas exactement a la string de candidature

### Incoherence 2: mapping `entry_year -> level` code en dur

- `ENTRY_YEAR_TO_LEVEL` est une logique metier implicite et statique
- elle suppose:
  - 1-3 = Licence
  - 4-5 = Master

Impact:

- fragile si certains programmes ont une duree atypique
- fragile pour des cycles non standard

### Incoherence 3: `entry_year` est ambigu

- semantiquement, `entry_year` peut vouloir dire:
  - annee d'entree dans le programme
  - niveau academique cible
- dans le code actuel, il est traite comme cle de resolution du niveau

Impact:

- possible dette metier si un candidat entre en passerelle ou redouble

### Incoherence 4: `Student` ne porte pas d'etat academique direct

- ce n'est pas forcement un bug
- mais cela signifie que tout repose sur l'existence de `AcademicEnrollment`

Impact:

- si l'enrollment n'est pas cree, le compte etudiant existe mais le contexte academique reste vide

### Incoherence 5: plusieurs points d'entree tentent la meme liaison

- `Payment._post_commit_actions()`
- `inscriptions.signals` sur passage a `active`

Impact:

- aujourd'hui c'est rendu idempotent
- mais il existe une redondance de tentative, pas une source unique parfaitement explicite

### Incoherence 6: fallback metier trop permissif

- si aucune classe n'est trouvee, le provisioning principal ne casse pas
- c'est bien pour la robustesse
- mais le systeme laisse alors un etudiant provisionne sans contexte academique

Impact:

- experience etudiante partiellement active
- dette operationnelle ensuite sur les dashboards et notes

## 8. Elements manquants

Les briques manquantes ne sont pas des tables majeures; elles sont surtout de gouvernance et de stabilisation.

Il manque:

- une definition officielle de la relation:
  - `entry_year`
  - `cycle`
  - `level`
  - `academic_class`
- une source de verite explicite pour resoudre le niveau, au lieu d'un mapping en dur
- une normalisation definitive de `academic_year`
- une regle metier pour les cas non triviaux:
  - reorientation
  - passerelle
  - redoublement
  - reprise
- une surface d'audit/monitoring pour les cas:
  - `manual_required_missing_data`
  - `manual_required_no_class`
  - `manual_required_ambiguous`

## 9. Proposition d'architecture academique propre

### Principe directeur

Ne pas dupliquer `niveau` partout.

Le bon modele cible est:

- `Candidature` porte l'intention academique d'entree
- `AcademicClass` porte l'instance pedagogique reelle
- `AcademicEnrollment` porte l'affectation academique effective
- `Student` reste une identite etudiante, pas le conteneur principal de structure pedagogique

### Architecture recommandee

1. Garder `AcademicEnrollment` comme pivot officiel unique du contexte academique
2. Considerer `AcademicClass` comme unite operationnelle complete:
   - programme
   - cycle implicite via programme
   - niveau via `level`
   - annee academique
   - branch
3. Formaliser une couche de resolution academique, par exemple:
   - `resolve_target_academic_context(candidature)`
   - qui retourne:
     - programme
     - cycle
     - resolved_level
     - academic_year
     - academic_class
4. Remplacer progressivement le mapping brut `ENTRY_YEAR_TO_LEVEL` par une politique de resolution plus declarative
5. Normaliser a terme `Candidature.academic_year` vers une vraie reference `AcademicYear`

### Ce qu'il ne faut pas faire

- ne pas ajouter un champ `level` arbitraire sur `Student`
- ne pas dupliquer `programme`, `cycle`, `class`, `year` a plusieurs endroits sans source unique
- ne pas inventer un second pivot parallele a `AcademicEnrollment`

## 10. Proposition de workflow automatique final

Workflow recommande:

1. `FIRST_PAYMENT_VALIDATED`
2. creation ou recuperation du `User`
3. creation ou recuperation du `Student`
4. resolution academique cible a partir de la candidature:
   - programme
   - branch
   - academic_year
   - entry_year
   - cycle
   - resolved_level
5. recherche de la `AcademicClass` unique compatible
6. creation de `AcademicEnrollment`
7. activation du dashboard contextualise
8. emission de logs metier si affectation academique impossible

En sortie, l'etudiant doit etre automatiquement lie a:

- sa formation
- son cycle
- son niveau
- sa classe
- son annee academique
- son dashboard contextualise

Sans intervention humaine seulement si:

- `AcademicYear` existe
- la classe cible existe
- la classe est unique pour `(programme, branch, academic_year, level)`

Sinon:

- ne pas casser le provisioning principal
- mais remonter un statut de remediation explicite

## 11. Impact sur dashboards

Impact positif attendu une fois le provisioning fiabilise:

- dashboard etudiant contextualise immediatement
- liste de cours disponible sans delai
- timetable exploitable des la creation du compte
- attendance et supervision strictement scellees a la bonne classe
- workflows resultats et bulletins sans rattrapage manuel

Point de vigilance:

- aujourd'hui, les dashboards supposent qu'un `AcademicEnrollment` existe deja
- toute industrialisation doit donc traiter l'affectation academique comme partie du provisioning critique

## 12. Impact sur provisioning etudiant

Le provisioning actuel fait deja 80% du travail:

- compte utilisateur
- profil role student
- matricule
- appel idempotent vers la liaison academique

Le vrai gap est:

- la fiabilite de resolution de l'affectation academique

Donc la future industrialisation doit prioriser:

- la couche de resolution
- la normalisation de l'annee academique
- la gestion des cas ambigus

Pas une refonte complete du modele

## 13. Impact sur resultats / UE / EC / semestres

Tout le moteur de notes et reporting est deja aligne sur `AcademicClass` et `AcademicEnrollment`.

Donc:

- si `AcademicEnrollment` est cree correctement, le moteur resultats suit naturellement
- si `AcademicEnrollment` manque, tout le reste se degrade:
  - notes
  - bulletins
  - ranking
  - timetable
  - attendance
  - contenus EC

Conclusion forte:

- le provisioning academique n'est pas un sujet annexe
- c'est la cle d'entree unique de tout le runtime pedagogique

## 14. Recommandation finale

Le systeme actuel contient deja la bonne architecture de fond.

La prochaine phase ne doit pas reconstruire le domaine, mais:

1. officialiser `AcademicEnrollment` comme source de verite academique
2. industrialiser la resolution `candidature -> level -> academic_class`
3. normaliser `academic_year`
4. traiter les echecs de resolution comme des cas metier supervisables
5. conserver `AcademicClass` comme pivot operationnel du niveau

## Decision d'architecture proposee

Decision recommande:

- `classe = niveau academique contextualise`
- `AcademicEnrollment = liaison academique officielle`
- `entry_year = signal d'entree a convertir`
- `Student` ne devient pas un duplicat du contexte academique

En clair:

- ne pas ajouter de nouveaux champs structurels massifs maintenant
- renforcer la resolution et l'orchestration
- puis industrialiser le `STUDENT ACADEMIC PROVISIONING SYSTEM` sur cette base
