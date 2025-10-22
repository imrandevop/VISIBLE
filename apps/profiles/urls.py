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

    # Role switching endpoint
    path('switch-role/', views.switch_role_api, name='switch_role'),

    # Provider dashboard endpoint
    path('provider/dashboard/', views.provider_dashboard_api, name='provider_dashboard'),

    # Seeker dashboard endpoint
    path('seeker/dashboard/', views.seeker_dashboard_api, name='seeker_dashboard'),

    # Wallet endpoint
    path('wallet/', views.get_wallet_details_api, name='wallet_details'),

    # Communication settings endpoint (GET and POST)
    path('communication/settings/', communication_views.communication_settings_api, name='communication_settings'),

    # Work assignment endpoints
    path('fcm-token/', work_assignment_views.update_fcm_token, name='update_fcm_token'),
    path('assign-work/', work_assignment_views.assign_work, name='assign_work'),
    path('work-orders/', work_assignment_views.get_work_orders, name='get_work_orders'),
    path('work-orders/<int:work_id>/respond/', work_assignment_views.respond_to_work, name='respond_to_work'),
    path('provider-status/', work_assignment_views.update_provider_status, name='update_provider_status'),
    path('active-providers/', work_assignment_views.get_active_providers, name='get_active_providers'),
    path('running-services/', work_assignment_views.get_running_services, name='get_running_services'),
]