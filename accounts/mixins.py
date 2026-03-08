"""
Mixins pour la gestion des permissions de dashboard.

Usage:
    class MyDashboardView(GroupRequiredMixin, View):
        group_required = ['admissions_managers', 'executive_director']
        # ou
        group_required = 'admissions_managers'
"""

from django.core.exceptions import PermissionDenied
from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import redirect


class GroupRequiredMixin(UserPassesTestMixin):
    """
    Mixin pour restreindre l'accès aux utilisateurs appartenant à certains groupes.

    Usage:
        class MonDashboard(GroupRequiredMixin, View):
            group_required = ['admissions_managers']

        # Ou pour un seul groupe:
        group_required = 'finance_agents'
    """

    group_required = None

    def test_func(self):
        """Test si l'utilisateur appartient au groupe requis"""
        if not self.request.user.is_authenticated:
            return False

        # Superuser a toujours accès
        if self.request.user.is_superuser:
            return True

        # Si pas de groupe requis, autoriser
        if not self.group_required:
            return True

        # Convertir en liste si chaîne unique
        required_groups = self.group_required
        if isinstance(required_groups, str):
            required_groups = [required_groups]

        # Vérifier l'appartenance au groupe
        user_groups = self.request.user.groups.values_list('name', flat=True)
        return any(group in user_groups for group in required_groups)

    def handle_no_permission(self):
        """Rediriger ou renvoyer une erreur"""
        if self.request.user.is_authenticated:
            # Rediriger vers une page d'accès refusé
            return redirect('core:access_denied')
        else:
            # Rediriger vers la page de connexion
            return redirect('login')


class AdmissionManagerMixin(GroupRequiredMixin):
    """Mixin spécifique pour les responsables admission"""
    group_required = 'admissions_managers'


class FinanceAgentMixin(GroupRequiredMixin):
    """Mixin spécifique pour les agents de paiement"""
    group_required = 'finance_agents'


class ExecutiveDirectorMixin(GroupRequiredMixin):
    """Mixin spécifique pour le directeur"""
    group_required = 'executive_director'


# =====================================================
# DÉCORATEURS POUR FONCTIONS-BASED VIEWS
# =====================================================

from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods


def group_required(groups):
    """
    Décorateur pour les views fonctions.

    Usage:
        @group_required(['admissions_managers', 'executive_director'])
        def my_view(request):
            ...
    """
    def decorator(view_func):
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')

            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            user_groups = request.user.groups.values_list('name', flat=True)

            if isinstance(groups, str):
                groups = [groups]

            if not any(g in user_groups for g in groups):
                return redirect('core:access_denied')

            return view_func(request, *args, **kwargs)

        return wrapped
    return decorator


# =====================================================
# HELPERS POUR TEMPLATES
# =====================================================

def has_group(user, group_name):
    """
    Filtre template pour vérifier l'appartenance à un groupe.

    Usage dans template:
        {% if request.user|has_group:'admissions_managers' %}
            <a href="/dashboard/admissions/">Dashboard Admissions</a>
        {% endif %}
    """
    return user.groups.filter(name=group_name).exists()


def get_user_group(user):
    """
    Retourne le premier groupe de l'utilisateur (pour affichage).
    """
    return user.groups.first()
