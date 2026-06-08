# Inscription vs Caisse — Pourquoi l'inscription n'est PAS une entrée d'argent

## 1. L'inscription est une créance, pas du cash

Quand un étudiant s'inscrit pour 500 000 FCFA, ça crée une dette (le `amount_due` dans `Inscription`). Tant qu'il n'a pas payé, **0 FCFA** dans la caisse. Pourtant l'inscription existe déjà dans le système.

## 2. Un paiement crée le cash

C'est `Payment.validate()` qui :
- marque `amount_paid` dans l'inscription
- **crée** un `BranchCashMovement` (mouvement caisse)

Si le paiement est juste "pending" (en attente), l'argent n'est pas encore dans la caisse.

## 3. Séparation des responsabilités

| Module | Rôle |
|--------|------|
| `Inscription` | Suivi pédagogique + créance |
| `Payment` | Transaction (pont entre dette et cash) |
| `BranchCashMovement` | Trésorerie réelle |

## 4. Exemple concret

1. Inscription 500 000 FCFA → `Inscription` créée, `amount_paid = 0`
2. Paiement 200 000 FCFA → `Payment` créé, status `pending`
3. Gestionnaire valide → `Payment.status = validated`, **+200 000 dans la caisse**
4. 2e versement 300 000 FCFA plus tard → même cycle

Si l'inscription créait directement une entrée en caisse, on devrait **inverser** la transaction si l'étudiant ne paye jamais. C'est le principe de la **comptabilité d'engagement** : on enregistre la créance au moment de l'inscription, et l'encaissement au moment du paiement.

## TL;DR

Inscription = **"ce qui est dû"**  
Caisse = **"ce qui est réellement encaissé"**

La distinction est un choix comptable sain — pas un bug.
