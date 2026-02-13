from formations.models import (
    Cycle, Diploma, Filiere,
    Programme, ProgrammeYear, Fee
)


def run():
    print("🚀 Création des formations Master (modèle corrigé)")

    # -------------------------------------------------
    # BASE COMMUNE
    # -------------------------------------------------
    cycle, _ = Cycle.objects.get_or_create(
        name="Master",
        defaults={
            "description": "Cycle supérieur Master (Licence ou TSS + 2 ans)",
            "min_duration_years": 2,
            "max_duration_years": 2,
            "is_active": True,
        }
    )

    diploma, _ = Diploma.objects.get_or_create(
        name="Master en Sciences de la Santé",
        defaults={"level": "superieur"}
    )

    filiere, _ = Filiere.objects.get_or_create(
        name="Sciences de la Santé",
        defaults={
            "description": "Domaine des formations supérieures en santé",
            "is_active": True,
        }
    )

    # -------------------------------------------------
    # PROGRAMMES MASTER (SPÉCIALITÉS)
    # -------------------------------------------------
    programmes = [
        "Biologie Médicale",
        "Gynécologie Obstétrique",
        "Manager en Santé",
        "Biochimie",
        "Pédagogie en Santé",
        "Épidémiologie",
        "Santé Sexuelle et Reproductive",
        "Nutrition et Science Alimentaire",
        "Santé Environnementale",
        "Biotechnologie",
    ]

    for title in programmes:
        programme, created = Programme.objects.get_or_create(
            title=title,
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            defaults={
                "duration_years": 2,
                "short_description": f"Master professionnel en {title}",
                "description": (
                    f"Formation de niveau Master en {title}, "
                    "destinée aux titulaires d'une Licence ou TSS + 2 ans."
                ),
                "is_active": True,
                "is_featured": True,
            }
        )

        if not created:
            print(f"⏩ Programme déjà existant : {title}")
            continue

        # -------------------------
        # ANNÉE 1
        # -------------------------
        year1, _ = ProgrammeYear.objects.get_or_create(
            programme=programme,
            year_number=1
        )

        Fee.objects.get_or_create(
            programme_year=year1,
            label="Inscription",
            defaults={"amount": 410000, "due_month": "Septembre"}
        )
        Fee.objects.get_or_create(
            programme_year=year1,
            label="Tranche Janvier",
            defaults={"amount": 200000, "due_month": "Janvier"}
        )
        Fee.objects.get_or_create(
            programme_year=year1,
            label="Tranche Mars",
            defaults={"amount": 200000, "due_month": "Mars"}
        )

        # -------------------------
        # ANNÉE 2
        # -------------------------
        year2, _ = ProgrammeYear.objects.get_or_create(
            programme=programme,
            year_number=2
        )

        Fee.objects.get_or_create(
            programme_year=year2,
            label="Inscription",
            defaults={"amount": 600000, "due_month": "Septembre"}
        )
        Fee.objects.get_or_create(
            programme_year=year2,
            label="Tranche Janvier",
            defaults={"amount": 300000, "due_month": "Janvier"}
        )
        Fee.objects.get_or_create(
            programme_year=year2,
            label="Tranche Mars",
            defaults={"amount": 300000, "due_month": "Mars"}
        )

        print(f"✅ Programme créé : {title}")

    print("🎉 Création terminée sans erreur.")
