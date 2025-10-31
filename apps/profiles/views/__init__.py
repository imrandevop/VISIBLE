# apps/profiles/views/__init__.py
"""
Profile views package.

This module provides backward compatibility by re-exporting all view functions.
"""
from .profile_views import (
    seeker_profile_setup_api,
    provider_profile_setup_api,
    get_profile_api,
    check_profile_status_api
)
from .dashboard_views import provider_dashboard_api, seeker_dashboard_api
from .wallet_views import get_wallet_details_api, switch_role_api

__all__ = [
    'seeker_profile_setup_api',
    'provider_profile_setup_api',
    'get_profile_api',
    'check_profile_status_api',
    'provider_dashboard_api',
    'seeker_dashboard_api',
    'get_wallet_details_api',
    'switch_role_api',
]
