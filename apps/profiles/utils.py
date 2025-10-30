# apps/profiles/utils.py
from django.db.models import Q
from apps.core.models import ProviderActiveStatus


def can_switch_role(user_profile):
    """
    Check if a user can switch roles based on activity status.

    Requirements:
    - No active work orders (as seeker or provider)
    - No pending transactions/payments
    - No ongoing service requests

    Returns:
        tuple: (can_switch: bool, reason: str or None)
    """
    from apps.profiles.work_assignment_models import WorkOrder

    # Check for active work orders where user is seeker
    active_seeker_orders = WorkOrder.objects.filter(
        seeker=user_profile.user,
        status__in=['pending', 'accepted', 'in_progress']
    ).exists()

    if active_seeker_orders:
        return False, "You have active work orders as a seeker. Please complete or cancel them before switching roles."

    # Check for active work orders where user is provider
    active_provider_orders = WorkOrder.objects.filter(
        provider=user_profile.user,
        status__in=['pending', 'accepted', 'in_progress']
    ).exists()

    if active_provider_orders:
        return False, "You have active work orders as a provider. Please complete them before switching roles."

    # Check for pending transactions (for providers with wallets)
    if user_profile.user_type == 'provider' and hasattr(user_profile, 'wallet'):
        from apps.profiles.models import WalletTransaction
        from django.utils import timezone
        from datetime import timedelta

        # Check for recent pending transactions (within last 5 minutes)
        recent_time = timezone.now() - timedelta(minutes=5)
        recent_transactions = WalletTransaction.objects.filter(
            wallet=user_profile.wallet,
            created_at__gte=recent_time
        ).exists()

        if recent_transactions:
            return False, "You have recent wallet transactions. Please wait a few minutes before switching roles."

    # Check if provider is currently active for work
    if user_profile.user_type == 'provider':
        # Check UserProfile.is_active_for_work field
        if user_profile.is_active_for_work:
            return False, "Please go offline before switching roles."

        # Also check ProviderActiveStatus model (used by dashboard/location services)
        provider_status = ProviderActiveStatus.objects.filter(
            user=user_profile.user,
            is_active=True
        ).exists()

        if provider_status:
            return False, "Please go offline before switching roles."

    # All checks passed
    return True, None


def validate_role_switch_data(user_profile, new_user_type, service_type=None):
    """
    Validate role switch request data.

    Args:
        user_profile: UserProfile instance
        new_user_type: Target user type ('seeker' or 'provider')
        service_type: Service type (required if switching to provider)

    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    # Check if switching to same role
    if user_profile.user_type == new_user_type:
        return False, f"You are already a {new_user_type}."

    # Validate new_user_type value
    valid_types = ['seeker', 'provider']
    if new_user_type not in valid_types:
        return False, f"Invalid user type. Must be one of: {', '.join(valid_types)}"

    # If switching to provider, service_type is required
    if new_user_type == 'provider':
        if not service_type:
            return False, "Service type is required when switching to provider role."

        valid_service_types = ['skill', 'vehicle', 'properties', 'SOS']
        if service_type not in valid_service_types:
            return False, f"Invalid service type. Must be one of: {', '.join(valid_service_types)}"

    return True, None
