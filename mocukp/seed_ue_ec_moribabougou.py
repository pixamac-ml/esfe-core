"""
Script d'ajout des UE/EC aux classes vides de Moribabougou.

Strategie :
1. Copier les UE/EC d'une classe de reference vers les classes du MEME programme ET MEME niveau
2. Pour les classes sans reference dans leur programme/niveau, creer des UE/EC generiques
"""
import os, sys
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from decimal import Decimal
from django.db import transaction
from branches.models import Branch
from academics.models import AcademicClass, Semester, UE, EC

B_MORI_ID = 2

# Reference classes (qui ont deja des UE/EC completes)
REFERENCE_CLASSES = {
    (13, "L1"): 2,   # Programme 13 (Bio Med Licence) L1 → Class 2
    (25, "M1"): 3,   # Programme 25 (Bio Med Master) M1 → Class 3
    (47, "M1"): 1,   # Programme 47 (Eco Sante) M1 → Class 1
}

# Programmes sans reference - on utilisera un template generique
GENERIC_TEMPLATE_UE_EC = [
    # Semestre 1
    {
        "ues": [
            {"code": "UE101", "title": "Fondamentaux 1", "ecs": [
                {"title": "Introduction", "credit": "2.00", "coef": "1.00"},
                {"title": "Concepts de base", "credit": "2.00", "coef": "1.00"},
                {"title": "Pratiques essentielles", "credit": "2.00", "coef": "1.00"},
            ]},
            {"code": "UE102", "title": "Methodologie", "ecs": [
                {"title": "Methodes d'etude", "credit": "2.00", "coef": "1.00"},
                {"title": "Analyse et synthese", "credit": "2.00", "coef": "1.00"},
                {"title": "Applications pratiques", "credit": "2.00", "coef": "1.00"},
            ]},
            {"code": "UE103", "title": "Environnement professionnel", "ecs": [
                {"title": "Cadre institutionnel", "credit": "2.00", "coef": "1.00"},
                {"title": "Reglementation", "credit": "2.00", "coef": "1.00"},
                {"title": "Ethique et deontologie", "credit": "2.00", "coef": "1.00"},
            ]},
            {"code": "UE104", "title": "Outils transverses", "ecs": [
                {"title": "Informatique", "credit": "2.00", "coef": "1.00"},
                {"title": "Communication", "credit": "2.00", "coef": "1.00"},
                {"title": "Langues", "credit": "2.00", "coef": "1.00"},
            ]},
            {"code": "UE105", "title": "Stage d'initiation", "ecs": [
                {"title": "Observation", "credit": "2.00", "coef": "1.00"},
                {"title": "Rapport de stage", "credit": "2.00", "coef": "1.00"},
                {"title": "Soutenance", "credit": "2.00", "coef": "1.00"},
            ]},
        ]
    },
    # Semestre 2
    {
        "ues": [
            {"code": "UE201", "title": "Fondamentaux 2", "ecs": [
                {"title": "Approfondissement", "credit": "2.00", "coef": "1.00"},
                {"title": "Etudes de cas", "credit": "2.00", "coef": "1.00"},
                {"title": "Ateliers pratiques", "credit": "2.00", "coef": "1.00"},
            ]},
            {"code": "UE202", "title": "Recherche appliquee", "ecs": [
                {"title": "Methodologie de recherche", "credit": "2.00", "coef": "1.00"},
                {"title": "Analyse de donnees", "credit": "2.00", "coef": "1.00"},
                {"title": "Projet tutorat", "credit": "2.00", "coef": "1.00"},
            ]},
            {"code": "UE203", "title": "Gestion et qualite", "ecs": [
                {"title": "Gestion de projet", "credit": "2.00", "coef": "1.00"},
                {"title": "Demarche qualite", "credit": "2.00", "coef": "1.00"},
                {"title": "Evaluation", "credit": "2.00", "coef": "1.00"},
            ]},
            {"code": "UE204", "title": "Professionnalisation", "ecs": [
                {"title": "Insertion professionnelle", "credit": "2.00", "coef": "1.00"},
                {"title": "Techniques de recherche", "credit": "2.00", "coef": "1.00"},
                {"title": "Projet personnel", "credit": "2.00", "coef": "1.00"},
            ]},
            {"code": "UE205", "title": "Stage pratique", "ecs": [
                {"title": "Stage encadre", "credit": "2.00", "coef": "1.00"},
                {"title": "Carnet de stage", "credit": "2.00", "coef": "1.00"},
                {"title": "Rapport final", "credit": "2.00", "coef": "1.00"},
            ]},
        ]
    },
]


def copy_ue_ec(source_class_id, target_class):
    """Copie les UE/EC d'une classe source vers une classe cible."""
    source_sems = Semester.objects.filter(academic_class_id=source_class_id).order_by('number')
    target_sems = Semester.objects.filter(academic_class=target_class).order_by('number')

    if source_sems.count() != target_sems.count():
        print(f"  ERREUR: nombre de semestres different ({source_sems.count()} vs {target_sems.count()})")
        return 0

    total_ecs = 0
    for src_sem, tgt_sem in zip(source_sems, target_sems):
        for src_ue in UE.objects.filter(semester=src_sem).order_by('code'):
            new_ue = UE.objects.create(
                semester=tgt_sem,
                code=src_ue.code,
                title=src_ue.title,
            )
            for src_ec in EC.objects.filter(ue=src_ue):
                EC.objects.create(
                    ue=new_ue,
                    title=src_ec.title,
                    credit_required=src_ec.credit_required,
                    coefficient=src_ec.coefficient,
                )
                total_ecs += 1
    return total_ecs


def create_generic_ue_ec(target_class, programme_title, level):
    """Cree des UE/EC generiques pour une classe."""
    total_ecs = 0
    sems = Semester.objects.filter(academic_class=target_class).order_by('number')

    for sem_idx, sem in enumerate(sems):
        template_sem = GENERIC_TEMPLATE_UE_EC[sem_idx]
        for ue_data in template_sem["ues"]:
            code = ue_data["code"]
            title = f"{programme_title} - {ue_data['title']}"
            if len(title) > 255:
                title = title[:255]
            new_ue = UE.objects.create(
                semester=sem,
                code=code,
                title=title,
            )
            for ec_data in ue_data["ecs"]:
                ec_title = f"{programme_title} - {ec_data['title']}"
                if len(ec_title) > 255:
                    ec_title = ec_title[:255]
                EC.objects.create(
                    ue=new_ue,
                    title=ec_title,
                    credit_required=Decimal(ec_data["credit"]),
                    coefficient=Decimal(ec_data["coef"]),
                )
                total_ecs += 1
    return total_ecs


def run():
    branch = Branch.objects.get(id=B_MORI_ID)
    print(f"=== Ajout UE/EC pour {branch.name} ===\n")

    empty_classes = AcademicClass.objects.filter(branch=branch).order_by('programme_id', 'level')

    total_copied = 0
    total_generated = 0

    for c in empty_classes:
        existing_ecs = EC.objects.filter(ue__semester__academic_class=c).count()
        if existing_ecs > 0:
            continue  # deja configuree

        key = (c.programme_id, c.level)
        prog_title = c.programme.title

        if key in REFERENCE_CLASSES:
            ref_id = REFERENCE_CLASSES[key]
            if c.id == ref_id:
                continue  # la classe de reference elle-meme
            ecs = copy_ue_ec(ref_id, c)
            total_copied += ecs
            print(f"  COPIER: Class {c.id} ({prog_title} {c.level}) <- Class {ref_id} ({ecs} ECs)")
        else:
            ecs = create_generic_ue_ec(c, prog_title, c.level)
            total_generated += ecs
            print(f"  GENERER: Class {c.id} ({prog_title} {c.level}) ({ecs} ECs)")

    print(f"\n=== RESULTAT: {total_copied} ECs copie(s), {total_generated} ECs generes ===")


if __name__ == "__main__":
    run()
