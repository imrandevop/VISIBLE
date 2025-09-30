# apps/profiles/urls.py
from django.urls import path
from apps.profiles import views
from apps.profiles import communication_views

app_name = 'profiles'

urlpatterns = [
    # Profile setup endpoints
    path('setup/', views.profile_setup_api, name='profile_setup'),
    path('me/', views.get_profile_api, name='get_profile'),
    path('status/', views.check_profile_status_api, name='profile_status'),

    # Communication settings endpoint (GET and POST)
    path('communication/settings/', communication_views.communication_settings_api, name='communication_settings'),
]