from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from portal.permissions import role_required

from .services import get_student_dashboard_shell
from .widgets.profile import get_profile_widget
from .widgets.academics import get_academics_widget
from .widgets.finance import get_finance_widget
from .widgets.notifications import get_notifications_widget


@login_required
@role_required("student")
def dashboard(request):
    context = get_student_dashboard_shell(request.user)
    return render(request, "portal/student/dashboard.html", context)


@login_required
@role_required("student")
def profile_partial(request):
    context = get_profile_widget(request.user)
    return render(request, "portal/student/partials/profile.html", context)


@login_required
@role_required("student")
def academics_partial(request):
    context = get_academics_widget(request.user)
    return render(request, "portal/student/partials/academics.html", context)


@login_required
@role_required("student")
def finance_partial(request):
    context = get_finance_widget(request.user)
    return render(request, "portal/student/partials/finance.html", context)


@login_required
@role_required("student")
def notifications_partial(request):
    context = get_notifications_widget(request.user)
    return render(request, "portal/student/partials/notifications.html", context)
