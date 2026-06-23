import fitz
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from formations.models import Filiere

from memoires.models import Memoire
from memoires.services.rendering import render_memoire_pages

User = get_user_model()

MEMOIRES_DEMO = [
    {
        "titre": "Prise en charge du paludisme grave chez l'enfant de moins de 5 ans au CHU Gabriel Touré",
        "auteurs": "Aïssata Diarra",
        "encadreur": "Dr. Seydou Bamba",
        "filiere": "Pédiatrie",
        "niveau": Memoire.Niveau.MASTER,
        "annee": 2024,
        "mots_cles": "paludisme, pédiatrie, urgences, Mali",
        "resume": (
            "<p>Cette étude évalue les pratiques de <strong>prise en charge du paludisme grave</strong> "
            "chez les enfants de moins de 5 ans admis au service de pédiatrie du CHU Gabriel Touré entre "
            "2022 et 2024.</p>"
            "<p>L'analyse de 180 dossiers montre un délai moyen de consultation de 48 heures après "
            "l'apparition des premiers symptômes, facteur aggravant identifié dans la majorité des "
            "complications observées. Des recommandations opérationnelles sont proposées pour réduire "
            "ce délai et améliorer le pronostic.</p>"
        ),
    },
    {
        "titre": "Évaluation de la prise en charge des hémorragies du post-partum dans les centres de santé de référence de Bamako",
        "auteurs": "Moussa Coulibaly",
        "encadreur": "Pr. Fatoumata Nafo",
        "filiere": "Sante maternelle et infantile",
        "niveau": Memoire.Niveau.MASTER,
        "annee": 2023,
        "mots_cles": "hémorragie, post-partum, sage-femme, obstétrique",
        "resume": (
            "<p>Les hémorragies du post-partum restent une cause majeure de mortalité maternelle au "
            "Mali. Ce mémoire analyse la qualité de la prise en charge dans trois centres de santé de "
            "référence du district de Bamako.</p>"
            "<p>Les résultats mettent en évidence des disparités importantes dans la disponibilité des "
            "produits sanguins et l'application des protocoles d'urgence obstétricale, et formulent des "
            "pistes d'amélioration concrètes.</p>"
        ),
    },
    {
        "titre": "Facteurs de risque de l'hypertension artérielle chez les adultes en milieu urbain à Bamako",
        "auteurs": "Fatoumata Keïta",
        "encadreur": "Dr. Ibrahima Diakité",
        "filiere": "Santé communautaire",
        "niveau": Memoire.Niveau.MASTER,
        "annee": 2025,
        "mots_cles": "hypertension, maladies chroniques, santé communautaire",
        "resume": (
            "<p>Une enquête transversale menée auprès de 320 adultes des communes I et IV de Bamako "
            "identifie les principaux facteurs de risque modifiables de l'hypertension artérielle : "
            "sédentarité, consommation excessive de sel et stress chronique.</p>"
            "<p>Le mémoire propose un plan de sensibilisation communautaire adapté au contexte urbain "
            "malien.</p>"
        ),
    },
    {
        "titre": "Étude de la résistance aux antibiotiques chez les souches d'Escherichia coli isolées dans les infections urinaires",
        "auteurs": "Ibrahim Sangaré",
        "encadreur": "Dr. Aly Guindo",
        "filiere": "Laboratoire et pharmacie",
        "niveau": Memoire.Niveau.MASTER,
        "annee": 2024,
        "mots_cles": "antibiorésistance, E. coli, infections urinaires, laboratoire",
        "resume": (
            "<p>L'antibiorésistance constitue une préoccupation croissante en santé publique. Cette "
            "étude analyse le profil de résistance de 95 souches d'<em>Escherichia coli</em> isolées "
            "d'infections urinaires communautaires à Bamako.</p>"
            "<p>Un taux de résistance élevé à l'amoxicilline et au cotrimoxazole est observé, justifiant "
            "une révision des protocoles d'antibiothérapie probabiliste.</p>"
        ),
    },
    {
        "titre": "Qualité de la prise en charge nutritionnelle des enfants malnutris sévères au Mali",
        "auteurs": "Mariam Touré",
        "encadreur": "Dr. Oumar Sissoko",
        "filiere": "Nutrition",
        "niveau": Memoire.Niveau.MASTER,
        "annee": 2025,
        "mots_cles": "malnutrition, nutrition infantile, prise en charge",
        "resume": (
            "<p>Ce travail évalue la conformité des pratiques de prise en charge de la malnutrition "
            "aiguë sévère aux protocoles nationaux dans quatre centres de récupération nutritionnelle.</p>"
            "<p>Les résultats soulignent l'importance du suivi post-hospitalisation pour limiter les "
            "rechutes, encore fréquentes dans l'échantillon étudié.</p>"
        ),
    },
    {
        "titre": "Connaissances, attitudes et pratiques des mères sur l'allaitement maternel exclusif à Bamako",
        "auteurs": "Aminata Sidibé",
        "encadreur": "Mme Kadidia Konaté",
        "filiere": "Puériculture",
        "niveau": Memoire.Niveau.LICENCE,
        "annee": 2024,
        "mots_cles": "allaitement maternel, puériculture, santé infantile",
        "resume": (
            "<p>Une enquête CAP (connaissances, attitudes, pratiques) menée auprès de 150 mères dans le "
            "district de Bamako révèle que si la majorité connaît les bénéfices de l'allaitement "
            "maternel exclusif, moins de la moitié le pratique jusqu'à 6 mois.</p>"
            "<p>Les obstacles socio-économiques identifiés orientent les recommandations du mémoire.</p>"
        ),
    },
    {
        "titre": "Prévalence du diabète de type 2 chez les patients consultant au centre de santé communautaire de Sikasso",
        "auteurs": "Boubacar Traoré",
        "encadreur": "Dr. Mahamadou Diarra",
        "filiere": "Santé communautaire",
        "niveau": Memoire.Niveau.LICENCE,
        "annee": 2023,
        "mots_cles": "diabète, maladies chroniques, Sikasso",
        "resume": (
            "<p>Cette étude descriptive estime la prévalence du diabète de type 2 parmi 210 patients "
            "consultant au CSCOM de Sikasso sur une période de six mois.</p>"
            "<p>Les résultats confirment une sous-détection préoccupante de la maladie en première ligne "
            "de soins.</p>"
        ),
    },
    {
        "titre": "Rôle de l'infirmier dans la prise en charge des plaies chroniques",
        "auteurs": "Kadiatou Camara",
        "encadreur": "M. Sékou Diallo",
        "filiere": "Soins infirmiers",
        "niveau": Memoire.Niveau.LICENCE,
        "annee": 2025,
        "mots_cles": "soins infirmiers, plaies chroniques, pansements",
        "resume": (
            "<p>Ce mémoire décrit les pratiques infirmières de soins des plaies chroniques (escarres, "
            "ulcères diabétiques) dans le service de chirurgie générale d'un hôpital régional.</p>"
            "<p>Il met en évidence un besoin de formation continue sur les nouvelles techniques de "
            "pansement.</p>"
        ),
    },
    {
        "titre": "Étude des pratiques d'hygiène hospitalière dans les services de chirurgie",
        "auteurs": "Drissa Konaté",
        "encadreur": "Mme Assitan Coulibaly",
        "filiere": "Soins infirmiers",
        "niveau": Memoire.Niveau.LICENCE,
        "annee": 2024,
        "mots_cles": "hygiène hospitalière, infections nosocomiales, chirurgie",
        "resume": (
            "<p>L'observation des pratiques d'hygiène (lavage des mains, asepsie du matériel) dans deux "
            "services de chirurgie révèle un taux de conformité de 62 % aux protocoles standards.</p>"
            "<p>Des actions correctives sont proposées pour réduire le risque d'infections "
            "nosocomiales.</p>"
        ),
    },
    {
        "titre": "Accouchement à domicile : déterminants et risques associés en zone rurale de Kayes",
        "auteurs": "Salimata Diallo",
        "encadreur": "Dr. Modibo Sangaré",
        "filiere": "Sante maternelle et infantile",
        "niveau": Memoire.Niveau.LICENCE,
        "annee": 2023,
        "mots_cles": "accouchement, zone rurale, santé maternelle, Kayes",
        "resume": (
            "<p>Dans la région de Kayes, une part importante des accouchements a encore lieu à domicile "
            "sans assistance qualifiée. Ce mémoire identifie les déterminants socio-culturels et "
            "économiques de ce choix.</p>"
            "<p>Il propose des pistes pour renforcer la fréquentation des structures de santé par les "
            "femmes enceintes en milieu rural.</p>"
        ),
    },
]


class Command(BaseCommand):
    help = "Cree 10 memoires de demonstration (5 Master, 5 Licence) avec un PDF provisoire, pour valider l'affichage du module avant depot des vrais fichiers."

    def _pdf_provisoire(self, titre):
        document = fitz.open()
        page = document.new_page(width=595, height=842)
        page.insert_textbox(
            fitz.Rect(60, 320, 535, 520),
            f"{titre}\n\nDocument provisoire.\nLe PDF definitif sera depose par l'administration.",
            fontsize=16,
            align=1,
        )
        data = document.tobytes()
        document.close()
        return data

    def handle(self, *args, **options):
        cree_par = User.objects.filter(is_superuser=True).order_by("id").first()
        crees, ignores = 0, 0

        for entree in MEMOIRES_DEMO:
            slug = slugify(entree["titre"])[:320]
            if Memoire.objects.filter(slug=slug).exists():
                ignores += 1
                continue

            try:
                filiere = Filiere.objects.get(name=entree["filiere"])
            except Filiere.DoesNotExist:
                self.stderr.write(self.style.WARNING(
                    f"Filiere '{entree['filiere']}' introuvable, memoire ignore : {entree['titre']}"
                ))
                continue

            memoire = Memoire.objects.create(
                titre=entree["titre"],
                slug=slug,
                auteurs=entree["auteurs"],
                encadreur=entree["encadreur"],
                filiere=filiere,
                niveau=entree["niveau"],
                annee=entree["annee"],
                resume=entree["resume"],
                mots_cles=entree["mots_cles"],
                statut=Memoire.Statut.BROUILLON,
                cree_par=cree_par,
            )
            memoire.fichier_source.save(
                "provisoire.pdf",
                ContentFile(self._pdf_provisoire(entree["titre"])),
                save=True,
            )
            render_memoire_pages(memoire)
            crees += 1
            self.stdout.write(f"  + {memoire.titre} ({memoire.get_niveau_display()})")

        self.stdout.write(self.style.SUCCESS(
            f"{crees} memoire(s) de demonstration cree(s), {ignores} deja present(s)."
        ))
        self.stdout.write(
            "Statut = Brouillon. Editez chaque memoire dans le Super Admin pour deposer "
            "le vrai PDF (les pages seront regenerees automatiquement) puis publiez-le."
        )
