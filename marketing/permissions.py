from django.core.exceptions import PermissionDenied

from accounts.access import can_access


def user_can_access_marketing(user):
    return can_access(user, "view_dashboard", "marketing")


def marketing_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not user_can_access_marketing(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapper

