"""
Fix for Class 4 (Nephrologie L1) - remplace 1 EC par 30 ECs generiques
"""
import os, sys
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from decimal import Decimal
from academics.models import AcademicClass, Semester, UE, EC
from mocukp.seed_ue_ec_moribabougou import create_generic_ue_ec

c = AcademicClass.objects.get(id=4)
old_count = EC.objects.filter(ue__semester__academic_class=c).count()

# Supprimer les anciens
for sem in Semester.objects.filter(academic_class=c):
    for ue in UE.objects.filter(semester=sem):
        ue.ecs.all().delete()
        ue.delete()

# Generer les nouveaux
total = create_generic_ue_ec(c, c.programme.title, c.level)
print(f"Class 4: {old_count} -> {total} ECs")
