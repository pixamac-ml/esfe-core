from django.shortcuts import redirect

from portal.views.views import _position_required
@_position_required({"it_support"})
def it_portal_v2(request):
    """Keep the historical URL on the single certified IT dashboard."""
    return redirect("accounts_portal:portal_dashboard")
