from django_components import component


@component.register("ec_note_cell")
class ECNoteCell(component.Component):
    template_name = "notes/ec_note_cell.html"

    def get_context_data(self, row, ec_row):
        return {"row": row, "ec_row": ec_row}
