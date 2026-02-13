from django.utils import timezone

def generate_matricule(student):
    """
    Exemple :
    ESFE-2026-MED-0001
    """
    year = timezone.now().year
    programme_code = student.inscription.candidature.programme.slug[:3].upper()
    return f"ESFE-{year}-{programme_code}-{student.pk:04d}"
