def get_profile_widget(user):
    if not user.is_authenticated:
        return {
            "full_name": "",
            "email": "",
            "phone": "",
            "matricule": "Non disponible",
            "formation": "Non disponible",
            "classroom": "Non disponible",
            "annexe": "Non disponible",
            "photo_url": None,
        }
    full_name = user.get_full_name() or getattr(user, "username", "")
    context = {
        "full_name": full_name,
        "email": getattr(user, "email", ""),
        "phone": "",
        "matricule": "Non disponible",
        "formation": "Non disponible",
        "classroom": "Non disponible",
        "annexe": "Non disponible",
        "photo_url": None,
    }
    try:
        # Préparer pour brancher le modèle Student plus tard
        pass
    except AttributeError:
        pass
    return context

