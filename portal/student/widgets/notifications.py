from communication.selectors import get_user_notifications


def get_notifications_widget(user):
    student = getattr(user, "student_profile", None)
    if student is None:
        return {
            "items": [],
            "empty_message": "Aucune notification pour le moment.",
        }

    items = [
        item.title
        for item in get_user_notifications(user, limit=4)
    ]

    return {
        "items": items,
        "empty_message": "Aucune notification pour le moment.",
    }
