# superadmin/views/dashboard.py
# Dashboard principal, widgets, préférences cockpit, quick actions, notifications

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q, Exists, OuterRef, Sum, Count, F, Value, IntegerField, Min

from formations.models import Programme, Cycle
from admissions.models import Candidature
from core.models import ContactMessage, Notification
from inscriptions.models import Inscription
from payments.models import Payment, CashPaymentSession
from students.models import Student
from blog.models import Article, Comment
from news.models import News, Event
from community.models import Category as CommunityCategory, Topic, Answer
from branches.models import Branch
from accounts.models import Profile
from superadmin.views.utils import superuser_required, _get_cockpit_pref
from .models import SuperadminCockpitPreference

# ============================================
# DASHBOARD
# ============================================

@user_passes_test(superuser_required, login_url='/accounts/login/')
def dashboard(request):
    """Dashboard principal avec statistiques"""
    pref = _get_cockpit_pref(request.user)
    period = request.GET.get('period') or pref.dashboard_period
    if period not in dict(SuperadminCockpitPreference.PERIOD_CHOICES):
        period = SuperadminCockpitPreference.PERIOD_7D
    if pref.dashboard_period != period:
        pref.dashboard_period = period
        pref.save(update_fields=['dashboard_period', 'updated_at'])
    today = timezone.localdate()
    # ...existing code for period bounds, context, stats, trends, etc...
    # (À compléter avec le reste du code dashboard depuis views.py)
    return render(request, 'superadmin/dashboard.html', {})

# ...ajouter ici les autres vues du dashboard (widgets, préférences, quick actions, notifications)...
