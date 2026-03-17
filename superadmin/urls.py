# superadmin/urls.py

from django.urls import path
from . import views

app_name = "superadmin"

urlpatterns = [

    # ============================================================================
    # DASHBOARD
    # ============================================================================
    path('', views.dashboard, name='dashboard'),

    # ============================================================================
    # FORMATIONS
    # ============================================================================
    path('formations/', views.formation_list, name='formation_list'),
    path('formations/create/', views.formation_create, name='formation_create'),
    path('formations/<int:pk>/', views.formation_detail, name='formation_detail'),
    path('formations/<int:pk>/edit/', views.formation_edit, name='formation_edit'),
    path('formations/<int:pk>/delete/', views.formation_delete, name='formation_delete'),
    path('formations/<int:pk>/toggle/', views.toggle_formation, name='formation_toggle'),

    # ============================================================================
    # CYCLES
    # ============================================================================
    path('cycles/', views.cycle_list, name='cycle_list'),
    path('cycles/create/', views.cycle_create, name='cycle_create'),
    path('cycles/<int:pk>/edit/', views.cycle_edit, name='cycle_edit'),
    path('cycles/<int:pk>/delete/', views.cycle_delete, name='cycle_delete'),

    # ============================================================================
    # FILIERES
    # ============================================================================
    path('filieres/', views.filiere_list, name='filiere_list'),
    path('filieres/create/', views.filiere_create, name='filiere_create'),
    path('filieres/<int:pk>/edit/', views.filiere_edit, name='filiere_edit'),
    path('filieres/<int:pk>/delete/', views.filiere_delete, name='filiere_delete'),

    # ============================================================================
    # DIPLOMAS
    # ============================================================================
    path('diplomas/', views.diploma_list, name='diploma_list'),
    path('diplomas/create/', views.diploma_create, name='diploma_create'),
    path('diplomas/<int:pk>/edit/', views.diploma_edit, name='diploma_edit'),
    path('diplomas/<int:pk>/delete/', views.diploma_delete, name='diploma_delete'),

    # ============================================================================
    # CANDIDATURES / ADMISSIONS
    # ============================================================================
    path('candidatures/', views.candidature_list, name='candidature_list'),
    path('admissions/', views.candidature_list, name='admission_list'),  # ALIAS
    path('candidatures/<int:pk>/', views.candidature_detail, name='candidature_detail'),
    path('candidatures/<int:pk>/status/', views.candidature_status, name='candidature_status'),
    path('candidatures/<int:pk>/delete/', views.candidature_delete, name='candidature_delete'),

    # ============================================================================
    # INSCRIPTIONS
    # ============================================================================
    path('inscriptions/', views.inscription_list, name='inscription_list'),
    path('inscriptions/<int:pk>/', views.inscription_detail, name='inscription_detail'),
    path('inscriptions/<int:pk>/status/', views.inscription_status, name='inscription_status'),

    # ============================================================================
    # STUDENTS
    # ============================================================================
    path('students/', views.student_list, name='student_list'),
    path('students/<int:pk>/', views.student_detail, name='student_detail'),
    path('students/<int:pk>/edit/', views.student_edit, name='student_edit'),

    # ============================================================================
    # PAYMENTS
    # ============================================================================
    path('payments/', views.payment_list, name='payment_list'),
    path('payments/<int:pk>/', views.payment_detail, name='payment_detail'),

    # ============================================================================
    # FEES
    # ============================================================================
    path('fees/', views.fee_list, name='fee_list'),
    path('fees/create/', views.fee_create, name='fee_create'),
    path('fees/<int:pk>/edit/', views.fee_edit, name='fee_edit'),
    path('fees/<int:pk>/delete/', views.fee_delete, name='fee_delete'),

    # ============================================================================
    # ARTICLES (Blog)
    # ============================================================================
    path('articles/', views.article_list, name='article_list'),
    path('articles/create/', views.article_create, name='article_create'),
    path('articles/<int:pk>/', views.article_detail, name='article_detail'),
    path('articles/<int:pk>/edit/', views.article_edit, name='article_edit'),
    path('articles/<int:pk>/delete/', views.article_delete, name='article_delete'),
    path('articles/<int:pk>/toggle/', views.toggle_article, name='article_toggle'),

    # ============================================================================
    # CATEGORIES (Blog)
    # ============================================================================
    path('categories/', views.category_list, name='category_list'),
    path('categories/create/', views.category_create, name='category_create'),
    path('categories/<int:pk>/edit/', views.category_edit, name='category_edit'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'),

    # ============================================================================
    # NEWS (Actualités)
    # ============================================================================
    path('news/', views.news_list, name='news_list'),
    path('actualites/', views.news_list, name='actualite_list'),  # ALIAS FR
    path('news/create/', views.news_create, name='news_create'),
    path('news/<int:pk>/', views.news_detail, name='news_detail'),
    path('news/<int:pk>/edit/', views.news_edit, name='news_edit'),
    path('news/<int:pk>/delete/', views.news_delete, name='news_delete'),
    path('news/<int:pk>/toggle/', views.toggle_news, name='news_toggle'),

    # ============================================================================
    # EVENTS (Événements)
    # ============================================================================
    path('events/', views.event_list, name='event_list'),
    path('events/create/', views.event_create, name='event_create'),
    path('events/<int:pk>/', views.event_detail, name='event_detail'),
    path('events/<int:pk>/edit/', views.event_edit, name='event_edit'),
    path('events/<int:pk>/delete/', views.event_delete, name='event_delete'),
    path('events/<int:pk>/toggle/', views.toggle_event, name='event_toggle'),

    # ============================================================================
    # PAGES (Legal / Institutionnelles)
    # ============================================================================
    path('pages/', views.page_list, name='page_list'),
    path('pages/create/', views.page_create, name='page_create'),
    path('pages/<int:pk>/', views.page_detail, name='page_detail'),
    path('pages/<int:pk>/edit/', views.page_edit, name='page_edit'),
    path('pages/<int:pk>/delete/', views.page_delete, name='page_delete'),

    # ============================================================================
    # PARTNERS (Partenaires)
    # ============================================================================
    path('partners/', views.partner_list, name='partner_list'),
    path('partners/create/', views.partner_create, name='partner_create'),
    path('partners/<int:pk>/edit/', views.partner_edit, name='partner_edit'),
    path('partners/<int:pk>/delete/', views.partner_delete, name='partner_delete'),
    path('partners/<int:pk>/toggle/', views.toggle_partner, name='partner_toggle'),

    # ============================================================================
    # TESTIMONIALS (Témoignages)
    # ============================================================================
    path('testimonials/', views.testimonial_list, name='testimonial_list'),
    path('testimonials/create/', views.testimonial_create, name='testimonial_create'),
    path('testimonials/<int:pk>/edit/', views.testimonial_edit, name='testimonial_edit'),
    path('testimonials/<int:pk>/delete/', views.testimonial_delete, name='testimonial_delete'),
    path('testimonials/<int:pk>/toggle/', views.toggle_testimonial, name='testimonial_toggle'),

    # ============================================================================
    # BRANCHES (Campus)
    # ============================================================================
    path('branches/', views.branch_list, name='branch_list'),
    path('campus/', views.branch_list, name='campus_list'),  # ALIAS
    path('branches/create/', views.branch_create, name='branch_create'),
    path('branches/<int:pk>/edit/', views.branch_edit, name='branch_edit'),
    path('branches/<int:pk>/delete/', views.branch_delete, name='branch_delete'),
    path('branches/<int:pk>/toggle/', views.toggle_branch, name='branch_toggle'),

    # ============================================================================
    # MESSAGES (Contact)
    # ============================================================================
    path('messages/', views.message_list, name='message_list'),
    path('messages/<int:pk>/', views.message_detail, name='message_detail'),
    path('messages/<int:pk>/status/', views.update_message_status, name='message_status'),
    path('messages/<int:pk>/delete/', views.message_delete, name='message_delete'),

    # ============================================================================
    # SETTINGS (Paramètres Institution)
    # ============================================================================
    path('settings/', views.settings, name='settings'),
    path('parametres/', views.settings, name='parametres'),  # ALIAS FR

    # ============================================================================
    # UTILITIES (Recherche, Actions groupées, Export)
    # ============================================================================
    path('search/', views.search_global, name='search_global'),
    path('bulk-action/', views.bulk_action, name='bulk_action'),
    path('export/<str:model_type>/', views.export_data, name='export_data'),

]