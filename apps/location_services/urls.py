from django.urls import path
from . import views

urlpatterns = [
    path('provider/toggle-status/', views.provider_toggle_status, name='provider_toggle_status'),
    path('seeker/search-toggle/', views.seeker_search_toggle, name='seeker_search_toggle'),
]