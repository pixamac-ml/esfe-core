# superadmin/views/utils.py
# Fonctions utilitaires, décorateurs, helpers transverses

from django.contrib import messages
from django.http import HttpResponse
from django.db.models.deletion import ProtectedError
from django.contrib.auth.decorators import user_passes_test
from .models import SuperadminCockpitPreference
from inscriptions.models import StatusHistory
from django.utils import timezone
from django.shortcuts import redirect

# Décorateur superuser_required
def superuser_required(user):
    return bool(user.is_authenticated and user.is_superuser)

# Handler pour les vues manquantes (placeholder)
def _missing_superadmin_view(name):
    @user_passes_test(superuser_required, login_url='/accounts/login/')
    def _view(request, *args, **kwargs):
        if request.headers.get('HX-Request'):
            return HttpResponse(status=204)
        messages.warning(
            request,
            f"La fonctionnalite '{name}' est temporairement indisponible.",
        )
        return redirect('superadmin:dashboard')
    _view.__name__ = name
    return _view

# Safe delete avec gestion ProtectedError
def _safe_delete(request, instance, *, success_message, protected_message, hx_redirect=None):
    try:
        instance.delete()
        messages.success(request, success_message)
    except ProtectedError:
        messages.error(request, protected_message)
    if request.headers.get('HX-Request') and hx_redirect:
        return HttpResponse(status=200, headers={'HX-Redirect': hx_redirect})
    return None

# Log d'historique d'inscription
def _log_inscription_history(inscription, previous_status, new_status, comment=''):
    StatusHistory.objects.create(
        inscription=inscription,
        previous_status=previous_status,
        new_status=new_status,
        comment=comment,
    )

# Changement de statut d'inscription
def _change_inscription_status(inscription, new_status, comment=''):
    previous_status = inscription.status
    inscription.status = new_status
    inscription.save(update_fields=['status'])
    # Le signal inscriptions.signals journalise deja les transitions de statut.
    if previous_status == new_status and comment:
        _log_inscription_history(inscription, previous_status, new_status, comment)

# Récupération ou création des préférences cockpit
def _get_cockpit_pref(user):
    pref, _ = SuperadminCockpitPreference.objects.get_or_create(user=user)
    return pref
