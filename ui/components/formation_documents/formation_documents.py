from django_components import component


@component.register("formation_documents")
class FormationDocuments(component.Component):
    template_name = "formation_documents/formation_documents.html"

    def get_context_data(self, required_documents):
        return {
            "required_documents": required_documents,
        }
