from django_components import component


@component.register("student.status_card")
class StudentStatusCard(component.Component):
    template_name = "student/status_card.html"

    def get_context_data(
        self,
        status="",
        status_label="",
        status_tone="neutral",
        promotion="",
        decision_date="",
        validation_academic="",
        validation_finance="",
        **kwargs,
    ):
        tone_map = {
            "promoted": "success",
            "repeated": "warning",
            "transferred": "info",
            "pending": "warning",
            "rejected": "danger",
        }
        return {
            "status": status,
            "status_label": status_label or status,
            "status_tone": tone_map.get(status, status_tone),
            "promotion": promotion,
            "decision_date": decision_date,
            "validation_academic": validation_academic,
            "validation_finance": validation_finance,
        }
