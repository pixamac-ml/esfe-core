# Resume dashboard secretaire

Le dashboard secretaire existe deja et colle globalement au projet.

Fonctionnalites presentes :
- registre administratif ;
- rendez-vous ;
- visites ;
- reception de documents ;
- taches ;
- notifications ;
- recherche etudiant/classe ;
- actions HTMX avec modales.

La structure est bonne :
- `models`
- `selectors`
- `services`
- `views`
- `templates`
- permissions

Point positif :
Le dashboard principal est bien branche aux donnees via `get_secretary_dashboard_data(request.user)`.

Problemes a corriger :
1. Plusieurs vues/listes/HTMX n'envoient pas `request.user` aux selectors.
   Resultat possible : listes vides ou mauvais filtrage par annexe.

2. Les formulaires sont crees sans `user=request.user`.
   Pourtant ils sont prevus pour filtrer les etudiants/agents par annexe.

3. La redirection globale `/accounts/dashboard/` ne redirige pas encore vers le dashboard secretaire.
   L'acces existe via `/secretary/` ou via le portail.

Conclusion :
La base est bonne, mais il faut finaliser le raccord user/annexe dans les vues et formulaires, puis ajouter la redirection secretaire.
