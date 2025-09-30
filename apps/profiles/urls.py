# apps/profiles/urls.py
from django.urls import path
from apps.profiles import views
from apps.profiles import communication_views
from apps.profiles import work_assignment_views

app_name = 'profiles'

urlpatterns = [
    # Profile setup endpoints
    path('setup/', views.profile_setup_api, name='profile_setup'),
    path('me/', views.get_profile_api, name='get_profile'),
    path('status/', views.check_profile_status_api, name='profile_status'),

    # Communication settings endpoint (GET and POST)
    path('communication/settings/', communication_views.communication_settings_api, name='communication_settings'),

    # Work assignment endpoints
    path('fcm-token/', work_assignment_views.update_fcm_token, name='update_fcm_token'),
    path('assign-work/', work_assignment_views.assign_work, name='assign_work'),
    path('work-orders/', work_assignment_views.get_work_orders, name='get_work_orders'),
    path('provider-status/', work_assignment_views.update_provider_status, name='update_provider_status'),
    path('active-providers/', work_assignment_views.get_active_providers, name='get_active_providers'),
]