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
    path('formations/<int:pk>/toggle/', views.toggle_formation, name='toggle_formation'),

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
    path('candidatures/<int:pk>/edit/', views.candidature_edit, name='candidature_edit'),
    path('candidatures/<int:pk>/delete/', views.candidature_delete, name='candidature_delete'),

    # ============================================================================
    # INSCRIPTIONS
    # ============================================================================
    path('inscriptions/', views.inscription_list, name='inscription_list'),
    path('inscriptions/create/', views.inscription_create, name='inscription_create'),
    path('inscriptions/<int:pk>/', views.inscription_detail, name='inscription_detail'),
    path('inscriptions/<int:pk>/edit/', views.inscription_edit, name='inscription_edit'),
    path('inscriptions/<int:pk>/delete/', views.inscription_delete, name='inscription_delete'),

    # ============================================================================
    # STUDENTS
    # ============================================================================
    path('students/', views.student_list, name='student_list'),
    path('students/<int:pk>/', views.student_detail, name='student_detail'),
    path('students/<int:pk>/edit/', views.student_edit, name='student_edit'),
    path('students/<int:pk>/delete/', views.student_delete, name='student_delete'),

    # ============================================================================
    # PAYMENTS
    # ============================================================================
    path('payments/', views.payment_list, name='payment_list'),
    path('payments/<int:pk>/', views.payment_detail, name='payment_detail'),
    path('payments/<int:pk>/edit/', views.payment_edit, name='payment_edit'),
    path('payments/<int:pk>/delete/', views.payment_delete, name='payment_delete'),

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
    path('articles/<int:pk>/toggle/', views.toggle_article, name='toggle_article'),

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
    path('news/<int:pk>/toggle/', views.toggle_news, name='toggle_news'),

    # ============================================================================
    # EVENTS (Événements)
    # ============================================================================
    path('events/', views.event_list, name='event_list'),
    path('events/create/', views.event_create, name='event_create'),
    path('events/<int:pk>/', views.event_detail, name='event_detail'),
    path('events/<int:pk>/edit/', views.event_edit, name='event_edit'),
    path('events/<int:pk>/delete/', views.event_delete, name='event_delete'),
    path('events/<int:pk>/toggle/', views.toggle_event, name='toggle_event'),

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
    path('partners/<int:pk>/toggle/', views.toggle_partner, name='toggle_partner'),

    # ============================================================================
    # TESTIMONIALS (Témoignages)
    # ============================================================================
    path('testimonials/', views.testimonial_list, name='testimonial_list'),
    path('testimonials/create/', views.testimonial_create, name='testimonial_create'),
    path('testimonials/<int:pk>/edit/', views.testimonial_edit, name='testimonial_edit'),
    path('testimonials/<int:pk>/delete/', views.testimonial_delete, name='testimonial_delete'),
    path('testimonials/<int:pk>/toggle/', views.toggle_testimonial, name='toggle_testimonial'),

    # ============================================================================
    # BRANCHES (Campus)
    # ============================================================================
    path('branches/', views.branch_list, name='branch_list'),
    path('campus/', views.branch_list, name='campus_list'),  # ALIAS
    path('branches/create/', views.branch_create, name='branch_create'),
    path('branches/<int:pk>/edit/', views.branch_edit, name='branch_edit'),
    path('branches/<int:pk>/delete/', views.branch_delete, name='branch_delete'),
    path('branches/<int:pk>/toggle/', views.toggle_branch, name='toggle_branch'),

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

    # ============================================================================
    # PROGRAMME YEARS
    # ============================================================================
    path('programme-years/', views.programme_year_list, name='programme_year_list'),
    path('programme-years/create/', views.programme_year_create, name='programme_year_create'),
    path('programme-years/<int:pk>/edit/', views.programme_year_edit, name='programme_year_edit'),
    path('programme-years/<int:pk>/delete/', views.programme_year_delete, name='programme_year_delete'),

    # ============================================================================
    # PROGRAMME QUICK FACTS
    # ============================================================================
    path('quick-facts/', views.quick_fact_list, name='quick_fact_list'),
    path('quick-facts/create/', views.quick_fact_create, name='quick_fact_create'),
    path('quick-facts/<int:pk>/edit/', views.quick_fact_edit, name='quick_fact_edit'),
    path('quick-facts/<int:pk>/delete/', views.quick_fact_delete, name='quick_fact_delete'),

    # ============================================================================
    # PROGRAMME TABS
    # ============================================================================
    path('programme-tabs/', views.programme_tab_list, name='programme_tab_list'),
    path('programme-tabs/create/', views.programme_tab_create, name='programme_tab_create'),
    path('programme-tabs/<int:pk>/edit/', views.programme_tab_edit, name='programme_tab_edit'),
    path('programme-tabs/<int:pk>/delete/', views.programme_tab_delete, name='programme_tab_delete'),

    # ============================================================================
    # PROGRAMME SECTIONS
    # ============================================================================
    path('programme-sections/', views.programme_section_list, name='programme_section_list'),
    path('programme-sections/create/', views.programme_section_create, name='programme_section_create'),
    path('programme-sections/<int:pk>/edit/', views.programme_section_edit, name='programme_section_edit'),
    path('programme-sections/<int:pk>/delete/', views.programme_section_delete, name='programme_section_delete'),

    # ============================================================================
    # COMPETENCE BLOCKS
    # ============================================================================
    path('competence-blocks/', views.competence_block_list, name='competence_block_list'),
    path('competence-blocks/create/', views.competence_block_create, name='competence_block_create'),
    path('competence-blocks/<int:pk>/edit/', views.competence_block_edit, name='competence_block_edit'),
    path('competence-blocks/<int:pk>/delete/', views.competence_block_delete, name='competence_block_delete'),

    # ============================================================================
    # COMPETENCE ITEMS
    # ============================================================================
    path('competence-items/', views.competence_item_list, name='competence_item_list'),
    path('competence-items/create/', views.competence_item_create, name='competence_item_create'),
    path('competence-items/<int:pk>/edit/', views.competence_item_edit, name='competence_item_edit'),
    path('competence-items/<int:pk>/delete/', views.competence_item_delete, name='competence_item_delete'),

    # ============================================================================
    # REQUIRED DOCUMENTS
    # ============================================================================
    path('required-documents/', views.required_document_list, name='required_document_list'),
    path('required-documents/create/', views.required_document_create, name='required_document_create'),
    path('required-documents/<int:pk>/edit/', views.required_document_edit, name='required_document_edit'),
    path('required-documents/<int:pk>/delete/', views.required_document_delete, name='required_document_delete'),

    # ============================================================================
    # PROGRAMME REQUIRED DOCUMENTS
    # ============================================================================
    path('programme-required-documents/', views.programme_required_document_list, name='programme_required_document_list'),
    path('programme-required-documents/create/', views.programme_required_document_create, name='programme_required_document_create'),
    path('programme-required-documents/<int:pk>/delete/', views.programme_required_document_delete, name='programme_required_document_delete'),

    # ============================================================================
    # CANDIDATURE DOCUMENTS
    # ============================================================================
    path('candidatures/<int:pk>/documents/add/', views.candidature_document_add, name='candidature_document_add'),
    path('candidatures/<int:pk>/documents/<int:doc_pk>/delete/', views.candidature_document_delete, name='candidature_document_delete'),
    path('candidatures/<int:pk>/documents/<int:doc_pk>/validate/', views.candidature_document_validate, name='candidature_document_validate'),

    # ============================================================================
    # COMMUNITY CATEGORIES
    # ============================================================================
    path('community/categories/', views.community_category_list, name='community_category_list'),
    path('community/categories/create/', views.community_category_create, name='community_category_create'),
    path('community/categories/<int:pk>/edit/', views.community_category_edit, name='community_category_edit'),
    path('community/categories/<int:pk>/delete/', views.community_category_delete, name='community_category_delete'),
    path('community/categories/<int:pk>/toggle/', views.toggle_community_category, name='toggle_community_category'),

    # ============================================================================
    # COMMUNITY TOPICS
    # ============================================================================
    path('community/topics/', views.community_topic_list, name='community_topic_list'),
    path('community/topics/<int:pk>/', views.community_topic_detail, name='community_topic_detail'),
    path('community/topics/<int:pk>/edit/', views.community_topic_edit, name='community_topic_edit'),
    path('community/topics/<int:pk>/delete/', views.community_topic_delete, name='community_topic_delete'),
    path('community/topics/<int:pk>/toggle/', views.toggle_community_topic, name='toggle_community_topic'),

    # ============================================================================
    # COMMUNITY ANSWERS
    # ============================================================================
    path('community/answers/', views.community_answer_list, name='community_answer_list'),
    path('community/answers/<int:pk>/', views.community_answer_detail, name='community_answer_detail'),
    path('community/answers/<int:pk>/edit/', views.community_answer_edit, name='community_answer_edit'),
    path('community/answers/<int:pk>/delete/', views.community_answer_delete, name='community_answer_delete'),
    path('community/answers/<int:pk>/toggle/', views.toggle_community_answer, name='toggle_community_answer'),

]
