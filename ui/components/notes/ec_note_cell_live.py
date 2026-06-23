from django_components import component


@component.register("ec_note_cell_live")
class ECNoteCellLive(component.Component):
    """
    Variante instantanee de `ec_note_cell` (dashboard informaticien uniquement).

    Saisie debattue (debounce) + recalcul Alpine cote client + sauvegarde
    serveur en arriere-plan sans remplacer le champ sous le curseur. Le
    composant `ec_note_cell` d'origine (utilise par l'ancienne grille
    `notes_grid.html`) n'est pas touche.
    """

    template_name = "notes/ec_note_cell_live.html"

    def get_context_data(self, row, ec_row, ue_id, session_type=None):
        return {"row": row, "ec_row": ec_row, "ue_id": ue_id, "session_type": session_type}
