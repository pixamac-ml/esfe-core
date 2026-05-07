# Communication Channel Governance

Reference metier centralisee pour limiter le bruit, clarifier les responsabilites des canaux et garder les workflows coherents.

## Regles

- `notification_in_app`: notification dashboard persistante, utile a relire plus tard.
- `websocket`: signal temps reel UI uniquement, reserve aux cas interactifs ou urgents.
- `email_transactional`: communication externe orientee utilisateur final.
- `finance_alert`: alerte interne finance/gestionnaire a priorite haute.
- `system_alert`: alerte critique staff/admin.
- `email_marketing`: campagnes uniquement, jamais dans les workflows metier critiques.

## Matrice

| Evenement | Cible | Canaux autorises | Priorite | Realtime |
| --- | --- | --- | --- | --- |
| `FIRST_PAYMENT_VALIDATED` | Etudiant | `email_transactional` + `notification_in_app` | `high` | `silent` |
| `FIRST_PAYMENT_VALIDATED` | Gestionnaire / finance | `finance_alert` via `notification_in_app` | `high` | `silent` |
| `FIRST_PAYMENT_VALIDATED` | Superadmin | log seulement | n/a | none |
| `ACCOUNT_CREATED` | Etudiant | `email_transactional` | `high` | none |
| `RECEIPT_GENERATED` | Etudiant | `email_transactional` | `normal` | none |
| `CANDIDATE_ACCEPTED` | Candidat | `email_transactional` + `notification_in_app` | `high` | none |
| `CANDIDATE_REJECTED` | Candidat | `email_transactional` + `notification_in_app` | `high` | none |
| `MISSING_DOCUMENTS` | Candidat | `email_transactional` + `notification_in_app` | `high` | none |
| `INSCRIPTION_*` | Candidat / etudiant | `email_transactional` + `notification_in_app` | `normal` a `high` | none |
| `COMMUNITY_NEW_ANSWER` | Membre concerne | `notification_in_app` + `websocket` | `high` | useful |
| `COMMUNITY_UPVOTE` | Auteur contenu | `notification_in_app` | `low` | none |

## Notes de reduction du bruit

- Eviter `websocket` quand un `in_app` suffit et que l'information n'est pas urgente.
- Eviter plusieurs notifications dashboard pour un meme workflow lineaire.
- Favoriser un email premium unique par etape utilisateur plutot que plusieurs confirmations redondantes.
- Utiliser la priorite pour distinguer badge critique et simple information.
