
from django_components import component


@component.register("formation_learning_outcomes")
class FormationLearningOutcomes(component.Component):
    template_name = "formation_learning_outcomes/formation_learning_outcomes.html"

def get_context_data(self, learning_outcomes: str):

    items = []

    if learning_outcomes:
        items = [
        line.strip()
    for line in learning_outcomes.splitlines()
        if line.strip()
            ]

    return {
        "items": items
        }