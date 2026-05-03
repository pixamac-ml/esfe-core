from django_components import component


@component.register("student_identity_column")
class StudentIdentityColumn(component.Component):
    template_name = "notes/student_identity_column.html"

    def get_context_data(self, row):
        return {"row": row}
