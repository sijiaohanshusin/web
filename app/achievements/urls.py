from django.urls import path
from . import views

app_name = 'achievements'
urlpatterns = [
    path('', views.hub, name='hub'),
    path('catalog/', views.catalog, name='catalog'),
    path('people/', views.people_lookup, name='people_lookup'),
    path('review/', views.review, name='review'),
    path('invitation/<uuid:pk>/', views.invitation, name='invitation'),
    path('claims/<int:pk>/cancel/', views.cancel_claim, name='cancel_claim'),
    path('honors/', views.honors_mine, name='honors'),
    path('honors/new/', views.honor_create, name='honor_create'),
    path('honors/manage/', views.honor_ranking, name='honor_ranking'),
    path('honors/<uuid:pk>/', views.honor_edit, name='honor_edit'),
    path('honors/<uuid:pk>/preview/', views.honor_preview, name='honor_preview'),
    path('honors/<uuid:pk>/publish/', views.honor_publish, name='honor_publish'),
    path('honors/<uuid:pk>/withdraw/', views.honor_withdraw, name='honor_withdraw'),
    path('honors/<uuid:pk>/delete/', views.honor_delete, name='honor_delete'),
    path('honors/<uuid:pk>/images/<uuid:image_pk>/delete/', views.certificate_delete, name='certificate_delete'),
    path('certificates/<uuid:pk>/', views.certificate, name='certificate'),
    path('<str:kind>/<int:pk>/', views.record, name='record'),
]
