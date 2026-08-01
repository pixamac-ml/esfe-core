from django_components import component


@component.register("student.identity_card")
class StudentIdentityCard(component.Component):
    template_name = "student/identity_card.html"

    def get_context_data(
        self,
        student=None,
        matricule="",
        full_name="",
        photo_url="",
        classe="",
        niveau="",
        filiere="",
        branch="",
        is_active=True,
        detail_url="#",
        **kwargs,
    ):
        return {
            "matricule": matricule,
            "full_name": full_name,
            "photo_url": photo_url,
            "classe": classe,
            "niveau": niveau,
            "filiere": filiere,
            "branch": branch,
            "is_active": bool(is_active),
            "detail_url": detail_url,
        }
