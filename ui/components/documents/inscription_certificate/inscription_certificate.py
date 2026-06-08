from django_components import component


@component.register("esfe_inscription_certificate")
class InscriptionCertificate(component.Component):
    template_name = "documents/inscription_certificate/inscription_certificate.html"

    def get_context_data(
        self,
        certificate_number="",
        date="",
        student_name="",
        student_matricule="",
        student_birth="",
        student_phone="",
        programme="",
        level="",
        academic_year="",
        branch_name="",
        inscription_date="",
        director_name="",
        **kwargs,
    ):
        return {
            "title": "ATTESTATION D'INSCRIPTION",
            "certificate_number": certificate_number,
            "date": date,
            "student_name": student_name,
            "student_matricule": student_matricule,
            "student_birth": student_birth,
            "student_phone": student_phone,
            "programme": programme,
            "level": level,
            "academic_year": academic_year,
            "branch_name": branch_name,
            "inscription_date": inscription_date,
            "director_name": director_name,
            **kwargs,
        }
