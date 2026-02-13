from django.urls import path
from . import views

app_name = 'blog'

urlpatterns = [

    # ======================================================
    # PUBLIC
    # ======================================================

    path('', views.article_list, name='article_list'),

    path('article/<slug:slug>/',
         views.article_detail,
         name='article_detail'),

    path('categorie/<slug:slug>/',
         views.category_detail,
         name='category_detail'),


    # ======================================================
    # COMMENTAIRES
    # ======================================================

    path('comment/<int:comment_id>/like/',
         views.like_comment_view,
         name='like_comment'),


    # ======================================================
    # MODERATION
    # ======================================================

    path('moderation/comments/',
         views.moderate_comments,
         name='moderate_comments'),

    path('moderation/comments/<int:comment_id>/approve/',
         views.approve_comment_view,
         name='approve_comment'),


    # ======================================================
    # BACKOFFICE ARTICLES
    # ======================================================

    path('admin/articles/create/',
         views.article_create,
         name='article_create'),

    path('admin/articles/<int:article_id>/edit/',
         views.article_edit,
         name='article_edit'),

    path('admin/articles/<int:article_id>/delete/',
         views.article_delete,
         name='article_delete'),
]
