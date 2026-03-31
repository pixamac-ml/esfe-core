# core/seed_legal.py

from django.db import transaction
from core.models import (
    Institution,
    LegalPage,
    LegalSection,
    LegalSidebarBlock
)


@transaction.atomic
def run():

    print("=== Initialisation du module juridique ===")

    # ==========================================================
    # INSTITUTION
    # ==========================================================

    institution = Institution.objects.first() or Institution()
    institution.name = "Ecole Superieure de Formation et d'Excellence"
    institution.short_name = "ESFE"
    institution.address = "Bamako"
    institution.city = "Bamako"
    institution.country = "Mali"
    institution.phone = "+223 XX XX XX XX"
    institution.email = "contact@esfe.edu.ml"
    institution.legal_status = "Etablissement prive d'enseignement superieur"
    institution.approval_number = "AGR-2026-001"
    institution.hosting_provider = "Infrastructure securisee"
    institution.hosting_location = "Hebergement professionnel protege"
    institution.is_active = True
    institution.save()

    print("Institution synchronisée.")

    # ==========================================================
    # FONCTION GÉNÉRIQUE POUR PAGE
    # ==========================================================

    def create_or_update_page(page_type, title, introduction, sections, sidebar):

        page, created = LegalPage.objects.update_or_create(
            page_type=page_type,
            defaults={
                "title": title,
                "introduction": introduction,
                "version": "1.0",
                "status": "published",
            }
        )

        print(f"Page '{title}' synchronisée.")

        # Supprime anciennes sections pour éviter doublons
        page.sections.all().delete()
        page.sidebar_blocks.all().delete()

        # Recrée sections
        for index, section in enumerate(sections, start=1):
            LegalSection.objects.create(
                page=page,
                title=section["title"],
                content=section["content"],
                order=index,
            )

        # Recrée sidebar
        for index, block in enumerate(sidebar, start=1):
            LegalSidebarBlock.objects.create(
                page=page,
                title=block["title"],
                content=block["content"],
                order=index,
            )

    # ==========================================================
    # MENTIONS LÉGALES
    # ==========================================================

    create_or_update_page(
        page_type="legal",
        title="Mentions légales",
        introduction="""
        Les presentes mentions legales precisent l'identite de l'editeur,
        les conditions d'hebergement, les regles de propriete intellectuelle
        et les modalites d'utilisation des contenus publies sur la plateforme ESFE.
        """,
        sections=[
            {
                "title": "Identification de l’établissement",
                "content": """
                L'Ecole Superieure de Formation et d'Excellence (ESFE)
                est un etablissement d'enseignement superieur prive,
                base a Bamako, Mali, et exerce ses activites dans le respect
                des textes nationaux applicables a l'enseignement superieur.
                """
            },
            {
                "title": "Direction de la publication",
                "content": """
                La direction de la publication est assuree par la Direction Generale
                de l'institution, responsable de la coherence editoriale,
                de l'exactitude des informations publiees et de la conformite legale
                des contenus institutionnels.
                """
            },
            {
                "title": "Hebergement et infrastructure",
                "content": """
                La plateforme est hebergee sur une infrastructure professionnelle
                securisee, avec mesures de disponibilite, de sauvegarde et de protection
                contre les acces non autorises.
                """
            },
            {
                "title": "Propriete intellectuelle",
                "content": """
                L'ensemble des contenus (textes, visuels, chartes, supports,
                elements graphiques et documents) est protege.
                Toute reproduction, diffusion ou adaptation sans autorisation
                prealable est interdite, sauf cas prevus par la loi.
                """
            },
            {
                "title": "Responsabilité",
                "content": """
                ESFE s'efforce d'assurer l'exactitude et la mise a jour reguliere
                des informations diffusees. Toutefois, l'institution ne peut garantir
                l'absence totale d'erreurs ou d'interruptions temporaires de service.
                """
            },
            {
                "title": "Droit applicable et juridiction",
                "content": """
                Les presentes mentions legales sont regies par le droit malien.
                En cas de litige, et sous reserve d'une resolution amiable,
                competence est attribuee aux juridictions territorialement competentes.
                """
            },
        ],
        sidebar=[
            {
                "title": "Contact institutionnel",
                "content": "contact@esfe.edu.ml<br>+223 XX XX XX XX<br>Bamako, Mali"
            },
            {
                "title": "Référence administrative",
                "content": "Numéro d’agrément : AGR-2026-001"
            },
            {
                "title": "Publication",
                "content": "Version 1.0<br>Document institutionnel officiel"
            },
        ]
    )

    # ==========================================================
    # POLITIQUE DE CONFIDENTIALITÉ
    # ==========================================================

    create_or_update_page(
        page_type="privacy",
        title="Politique de confidentialité",
        introduction="""
        Cette politique explique comment ESFE collecte, utilise,
        conserve et protege les donnees personnelles des candidats,
        etudiants, parents, partenaires et visiteurs de la plateforme.
        """,
        sections=[
            {
                "title": "Données collectées",
                "content": """
                Selon les services utilises, ESFE peut collecter:
                donnees d'identite, coordonnees, informations academiques,
                pieces administratives, historiques de candidature et informations
                liees aux paiements et echanges de support.
                """
            },
            {
                "title": "Finalites des traitements",
                "content": """
                Les donnees sont traitees pour:
                gestion des candidatures et inscriptions,
                suivi pedagogique,
                obligations administratives et reglementaires,
                communication institutionnelle et support usager.
                """
            },
            {
                "title": "Base legale et conservation",
                "content": """
                Les traitements reposent sur l'execution de services,
                les obligations legales applicables et, lorsque necessaire,
                le consentement de la personne concernee.
                Les donnees sont conservees pendant la duree strictement necessaire
                a chaque finalite, puis archivees ou supprimees selon la politique interne.
                """
            },
            {
                "title": "Confidentialite et securite",
                "content": """
                ESFE applique des mesures techniques et organisationnelles appropriees:
                controle d'acces, journalisation, sauvegardes,
                cloisonnement des donnees et pratiques de securisation des comptes.
                """
            },
            {
                "title": "Partage des donnees",
                "content": """
                Les donnees ne sont partagees qu'avec des personnes habilitees
                ou des prestataires techniques impliques dans l'exploitation du service,
                dans le respect d'obligations de confidentialite.
                """
            },
            {
                "title": "Droits des personnes",
                "content": """
                Toute personne concernee peut demander l'acces,
                la rectification, la limitation ou la suppression de ses donnees,
                sous reserve des obligations legales de conservation.
                Les demandes sont traitees via le contact officiel de l'etablissement.
                """
            },
        ],
        sidebar=[
            {
                "title": "Contact données",
                "content": "contact@esfe.edu.ml"
            },
            {
                "title": "Canal de demande",
                "content": "Objet conseille: Protection des donnees"
            },
            {
                "title": "Mise a jour",
                "content": "Politique revisee periodiquement selon les evolutions legales."
            }
        ]
    )

    # ==========================================================
    # CONDITIONS D'UTILISATION
    # ==========================================================

    create_or_update_page(
        page_type="terms",
        title="Conditions d'utilisation",
        introduction="""
        Les presentes conditions d'utilisation encadrent l'acces,
        la navigation et l'usage des services numeriques de ESFE,
        y compris les espaces d'information, de candidature et de suivi.
        """,
        sections=[
            {
                "title": "Objet",
                "content": """
                Les presentes conditions definissent les regles applicables
                a toute consultation et utilisation de la plateforme institutionnelle.
                """
            },
            {
                "title": "Accès au service",
                "content": """
                Le service est accessible en continu, sauf operations de maintenance,
                incidents techniques, mesures de securite ou cas de force majeure.
                """
            },
            {
                "title": "Compte utilisateur et securite",
                "content": """
                L'utilisateur est responsable de la confidentialite de ses identifiants.
                Toute activite realisee via son compte est presumee emaner de lui,
                sauf preuve d'un acces frauduleux signale sans delai.
                """
            },
            {
                "title": "Engagements de l'utilisateur",
                "content": """
                L'utilisateur s'engage a fournir des informations exactes,
                a respecter les lois et a ne pas perturber le bon fonctionnement du service.
                Sont notamment prohibes: usurpation, tentative d'intrusion,
                diffusion de contenus illicites ou atteinte aux droits d'autrui.
                """
            },
            {
                "title": "Responsabilité",
                "content": """
                L'institution met en oeuvre les moyens raisonnables pour
                garantir la fiabilité des contenus, sans garantie d'absence d'erreur.
                ESFE ne saurait etre tenue responsable des dommages indirects
                lies a l'usage du service ou a une indisponibilite temporaire.
                """
            },
            {
                "title": "Modification des conditions",
                "content": """
                ESFE peut mettre a jour les presentes conditions a tout moment.
                La version en vigueur est celle publiee sur la presente page.
                """
            },
        ],
        sidebar=[
            {
                "title": "Signalement",
                "content": "Pour toute anomalie, contactez: contact@esfe.edu.ml"
            },
            {
                "title": "Bonnes pratiques",
                "content": "Ne partagez jamais vos identifiants."
            },
            {
                "title": "Version",
                "content": "Version 1.0 - Conditions applicables au portail ESFE"
            }
        ]
    )

    print("=== Seed juridique terminé avec succès ===")
