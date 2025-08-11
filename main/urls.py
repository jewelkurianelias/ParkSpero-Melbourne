# main/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('predictions/', views.predictions, name='predictions'), 
    path('analytics/', views.analytics, name='analytics'),
    path('live_parking/', views.live_parking, name='live_parking'),
    path('contact/', views.contact, name='contact'),
    path("api/live_parking/", views.live_parking_api, name="live_parking_api"),

    # NEW: predictions API (cache-backed, read-only)
    path('api/v1/predictions/', views.predictions_api, name='predictions_api'),
]
