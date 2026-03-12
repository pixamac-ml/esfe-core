from django_components import component
import json


@component.register("faq")
class FAQ(component.Component):
    template_name = "home/faq/faq.html"

    def get_context_data(self, **kwargs):
        # Questions fréquentes - à personnaliser
        faqs = kwargs.get('faqs', [
            {
                "question": "Quelles sont les conditions d'admission à l'ESFE ?",
                "answer": "Pour intégrer l'ESFE, vous devez être titulaire du Baccalauréat (toutes séries) ou d'un diplôme équivalent. Les candidatures sont évaluées sur dossier, suivi d'un entretien de motivation. Les inscriptions sont ouvertes de juin à octobre de chaque année."
            },
            {
                "question": "Les diplômes de l'ESFE sont-ils reconnus par l'État ?",
                "answer": "Oui, tous nos diplômes sont reconnus par l'État malien et validés par le Ministère de l'Enseignement Supérieur. Ils permettent l'accès aux concours de la fonction publique et sont reconnus par les établissements de santé nationaux et internationaux."
            },
            {
                "question": "Quelle est la durée des formations ?",
                "answer": "La durée varie selon le programme choisi : les formations de niveau Licence durent 3 ans, les BTS 2 ans, et les formations continues de 6 mois à 1 an. Chaque formation inclut des stages pratiques obligatoires en milieu hospitalier."
            },
            {
                "question": "Y a-t-il des possibilités de stage pratique ?",
                "answer": "Absolument ! L'ESFE dispose de conventions avec les principaux établissements de santé du Mali (CHU Gabriel Touré, CHU Point G, hôpitaux régionaux). Les stages représentent 40% de la formation et garantissent une expérience terrain concrète."
            },
            {
                "question": "Quels sont les frais de scolarité ?",
                "answer": "Les frais varient selon la formation choisie. Nous proposons des facilités de paiement échelonné et des bourses d'excellence pour les étudiants méritants. Contactez notre service admission pour un devis personnalisé."
            },
            {
                "question": "L'ESFE propose-t-elle des formations à distance ?",
                "answer": "Certains modules théoriques peuvent être suivis en ligne via notre plateforme e-learning. Cependant, les formations en santé nécessitent une présence obligatoire pour les travaux pratiques et les stages cliniques."
            },
        ])

        return {
            "faqs": faqs,
            "faqs_json": json.dumps(faqs),
            "section_title": kwargs.get('title', "Questions Fréquentes"),
            "section_subtitle": kwargs.get('subtitle', "Trouvez rapidement les réponses à vos interrogations"),
        }