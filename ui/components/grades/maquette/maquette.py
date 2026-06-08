from django_components import component


@component.register("grades_maquette")
class GradesMaquette(component.Component):
    """
    Maquette de saisie des notes refondue en CSS Grid.

    Refactor du template historique `notes_grid.html` (qui utilisait un <table>).
    Conserve la même forme (2 niveaux d'header : UE / EC + 3 sous-colonnes Note |
    Note coef. | Crédits obtenus + colonne "Unité" synthétique) mais transposée
    fidèlement en CSS Grid avec :

    - Colonnes meta figées à gauche (N°, NOM, PRENOMS)
    - Colonnes résultats figées à droite (Moyenne, Pourcentage, Crédits)
    - Header sticky en haut
    - Color coding automatique par seuil (par coefficient)
    - Navigation clavier (Tab, Enter, flèches, copier-coller depuis Excel)
    - Validation 0-20 avec feedback temps réel

    Réutilise les sous-composants existants pour ne rien casser :
    - student_identity_column
    - ec_note_cell
    - semester_summary
    - notes_header
    - notes_actions_bar
    """

    template_name = "grades/maquette/maquette.html"

    def get_context_data(
        self,
        academic_class,
        semester,
        ues,
        rows,
        active_session_type,
        active_session_label,
        workflow_permissions,
        workflow_badge,
        publish_ready,
        first_enrollment,
        embedded_in_dashboard=False,
    ):
        # Calcul des compteurs pour la grille CSS dynamique
        total_ecs = sum(ue.ecs.count() for ue in ues)
        total_ues = len(ues)

        return {
            "academic_class": academic_class,
            "semester": semester,
            "ues": ues,
            "rows": rows,
            "active_session_type": active_session_type,
            "active_session_label": active_session_label,
            "workflow_permissions": workflow_permissions,
            "workflow_badge": workflow_badge,
            "publish_ready": publish_ready,
            "first_enrollment": first_enrollment,
            "embedded_in_dashboard": embedded_in_dashboard,
            "total_ecs": total_ecs,
            "total_ues": total_ues,
        }
