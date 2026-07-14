from django.utils.http import url_has_allowed_host_and_scheme


ACTION_URL_KEYS = (
    "action_url",
    "dashboard_url",
    "receipt_url",
    "detail_url",
    "login_url",
)


def get_safe_action_url(message, request=None):
    """Retourne uniquement un lien relatif ou appartenant à l'hôte courant."""
    containers = [getattr(message, "metadata", None)]
    event = getattr(message, "event", None)
    if event is not None:
        containers.extend([getattr(event, "payload", None), getattr(event, "metadata", None)])

    for container in containers:
        if not isinstance(container, dict):
            continue
        for key in ACTION_URL_KEYS:
            candidate = container.get(key)
            if not isinstance(candidate, str):
                continue
            candidate = candidate.strip()
            if candidate.startswith("/") and not candidate.startswith("//"):
                return candidate
            if request and url_has_allowed_host_and_scheme(
                candidate,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return candidate
    return ""
