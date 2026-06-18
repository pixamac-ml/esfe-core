"""
Suppression iterative des branches demo.
DEMO(13), TRESULT(15), TDEBT(17)
"""
import os, sys, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from django.db import transaction
from django.db.models.deletion import ProtectedError
from branches.models import Branch

DEMO_IDS = [13, 15, 17]

def delete_with_retry(obj, depth=0):
    """Tente de supprimer obj. Si bloque par PROTECT, supprime d'abord les objets bloquants."""
    prefix = "  " * depth
    try:
        model_name = obj.__class__.__name__
        try:
            name = str(obj)
        except Exception:
            name = f"pk={obj.pk}"
        obj.delete()
        if depth <= 2:
            print(f"{prefix}Supprime {model_name}: {name}")
        return True
    except ProtectedError as e:
        for protected_obj in e.protected_objects:
            delete_with_retry(protected_obj, depth + 1)
        # Reessayer
        model_name = obj.__class__.__name__
        obj.delete()
        if depth <= 2:
            print(f"{prefix}Supprime (retry) {model_name}: pk={obj.pk}")
        return True

def run():
    branches = Branch.objects.filter(id__in=DEMO_IDS)
    if not branches.exists():
        print("Aucune branche demo trouvee.")
        return
    print(f"Branches: {[(b.id, b.name) for b in branches]}")

    with transaction.atomic():
        for b in branches:
            print(f"\n--- {b.name} ---")
            delete_with_retry(b)

    print("\n=== TERMINE ===")

if __name__ == "__main__":
    run()
