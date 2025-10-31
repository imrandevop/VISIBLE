# apps/profiles/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction

from apps.profiles.models import UserProfile, Wallet
from apps.core.models import ProviderActiveStatus

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def provider_dashboard_api(request, version=None):
    """
    Get provider dashboard data including active status, wallet, services, and previous services

    GET /api/1/profiles/provider/dashboard/

    Headers:
        Authorization: Bearer <jwt_token>

    Response:
        Success (200):
        {
            "status": "success",
            "message": "provider dashboard data fetched successfully",
            "data": {
                "profile_complete": true,
                "active_status": {
                    "is_active": false,
                    "provider_id": "WKR1023",
                    "last_updated": "2025-10-07T10:55:00Z"
                },
                "wallet": {
                    "balance": 850.00,
                    "currency": "INR",
                    "online_subscription_expires_at": "2025-10-15T10:30:00Z",
                    "is_online_subscription_active": true,
                    "online_subscription_time_remaining": "12h 0m"
                },
                "services": {
                    "active_services": 2
                },
                "offers": [
                    {
                        "offer_id": "OFF001",
                        "title": "Snapdeal Mega Sale",
                        "description": "Get up to 70% off on all products",
                        "image_url": "https://imagesvs.oneindia.com/img/2016/09/snapdeal-21-1474438626.jpg",
                        "valid_until": "2025-10-31T23:59:59Z",
                        "is_active": true,
                        "priority": 1
                    }
                ],
                "previous_services": [...],
                "aadhaar_verified": true,
                "maintenance_mode": false
            }
        }

        Error (403):
        {
            "status": "error",
            "message": "Only providers can access dashboard"
        }

        Error (400):
        {
            "status": "error",
            "message": "Profile incomplete. Please complete your profile setup."
        }
    """
    try:
        user = request.user

        # Check if user has profile
        try:
            user_profile = UserProfile.objects.select_related('wallet').get(user=user)
        except UserProfile.DoesNotExist:
            return Response({
                "status": "error",
                "message": "User profile not found. Please complete profile setup."
            }, status=status.HTTP_404_NOT_FOUND)

        # Check if user is provider
        if user_profile.user_type != 'provider':
            return Response({
                "status": "error",
                "message": "Only providers can access dashboard"
            }, status=status.HTTP_403_FORBIDDEN)

        # Allow access to dashboard even if profile incomplete
        # They can see what needs to be completed via profile_complete field in response

        # 1. Get active status from ProviderActiveStatus (location service)
        provider_status = ProviderActiveStatus.objects.filter(user=user).first()
        active_status_data = {
            "is_active": provider_status.is_active if provider_status else False,
            "provider_id": user_profile.provider_id,
            "last_updated": provider_status.last_active_at.isoformat() if provider_status and provider_status.last_active_at else None
        }

        # 2. Get wallet data with subscription details
        # Check if wallet exists, if not create it
        if hasattr(user_profile, 'wallet'):
            wallet = user_profile.wallet
        else:
            # Create wallet if doesn't exist
            from apps.profiles.models import Wallet
            wallet = Wallet.objects.create(
                user_profile=user_profile,
                balance=0.00,
                currency='INR'
            )

        # Calculate subscription time remaining
        from django.utils import timezone
        online_subscription_time_remaining = None
        if wallet.online_subscription_expires_at:
            now = timezone.now()
            if now < wallet.online_subscription_expires_at:
                time_diff = wallet.online_subscription_expires_at - now
                total_seconds = int(time_diff.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                online_subscription_time_remaining = f"{hours}h {minutes}m"

        wallet_data = {
            "balance": float(wallet.balance),
            "currency": wallet.currency,
            "online_subscription_expires_at": wallet.online_subscription_expires_at.isoformat() if wallet.online_subscription_expires_at else None,
            "is_online_subscription_active": wallet.is_online_subscription_active(),
            "online_subscription_time_remaining": online_subscription_time_remaining
        }

        # 3. Get active services count (services with active WorkSession)
        from apps.profiles.work_assignment_models import WorkOrder, WorkSession

        active_services_count = WorkSession.objects.filter(
            work_order__provider=user,
            connection_state='active'
        ).count()

        services_data = {
            "active_services": active_services_count
        }

        # 4. Get previous services (5 most recent, all statuses)
        work_orders = WorkOrder.objects.filter(
            provider=user
        ).select_related('seeker__profile').order_by('-created_at')[:5]

        previous_services = []
        for order in work_orders:
            # Format date and time
            created_at = order.created_at
            date_str = created_at.strftime("%Y-%m-%d")
            time_str = created_at.strftime("%I:%M %p")

            previous_services.append({
                "customer_name": order.seeker_profile.full_name if hasattr(order, 'seeker_profile') else "Unknown",
                "date": date_str,
                "time": time_str,
                "status": order.status
            })

        # 5. Check aadhaar verification
        aadhaar_verified = False
        try:
            from apps.verification.models import AadhaarVerification
            aadhaar_verification = AadhaarVerification.objects.get(user=user_profile)
            aadhaar_verified = aadhaar_verification.status == 'verified'
        except AadhaarVerification.DoesNotExist:
            aadhaar_verified = False

        # 6. Get active offers (sorted by priority, only active and not expired)
        from apps.profiles.models import Offer
        from django.utils import timezone

        active_offers = Offer.objects.filter(
            is_active=True,
            valid_until__gt=timezone.now()
        ).order_by('priority', '-created_at')

        offers_data = []
        for offer in active_offers:
            offers_data.append({
                "offer_id": offer.offer_id,
                "title": offer.title,
                "description": offer.description,
                "image_url": offer.image_url,
                "valid_until": offer.valid_until.isoformat(),
                "is_active": offer.is_active,
                "priority": offer.priority
            })

        # 7. Get maintenance mode status (from the first offer record, default to False)
        maintenance_mode = False
        first_offer = Offer.objects.first()
        if first_offer:
            maintenance_mode = first_offer.maintenance_mode

        # Build response
        response_data = {
            "status": "success",
            "message": "provider dashboard data fetched successfully",
            "data": {
                "profile_complete": user_profile.profile_complete,
                "active_status": active_status_data,
                "wallet": wallet_data,
                "services": services_data,
                "offers": offers_data,
                "previous_services": previous_services,
                "aadhaar_verified": aadhaar_verified,
                "maintenance_mode": maintenance_mode
            }
        }

        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in provider dashboard API: {str(e)}")
        return Response({
            "status": "error",
            "message": "An unexpected server error occurred. Please try again."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def seeker_dashboard_api(request, version=None):
    """
    Get seeker dashboard data including search status, wallet, services, and previous services

    GET /api/1/profiles/seeker/dashboard/

    Headers:
        Authorization: Bearer <jwt_token>

    Response:
        Success (200):
        {
            "status": "success",
            "message": "seeker dashboard data fetched successfully",
            "data": {
                "profile_complete": true,
                "search_status": {
                    "is_searching": false,
                    "last_updated": "2025-10-07T10:55:00Z"
                },
                "wallet": {
                    "balance": 850.00,
                    "currency": "INR"
                },
                "services": {
                    "active_services": 2
                },
                "offers": [
                    {
                        "offer_id": "OFF001",
                        "title": "Snapdeal Mega Sale",
                        "description": "Get up to 70% off on all products",
                        "image_url": "https://imagesvs.oneindia.com/img/2016/09/snapdeal-21-1474438626.jpg",
                        "valid_until": "2025-10-31T23:59:59Z",
                        "is_active": true,
                        "priority": 1
                    }
                ],
                "previous_services": [...],
                "maintenance_mode": false
            }
        }

        Error (403):
        {
            "status": "error",
            "message": "Only seekers can access dashboard"
        }

        Error (400):
        {
            "status": "error",
            "message": "Profile incomplete. Please complete your profile setup."
        }
    """
    try:
        user = request.user

        # Check if user has profile
        try:
            user_profile = UserProfile.objects.select_related('wallet').get(user=user)
        except UserProfile.DoesNotExist:
            return Response({
                "status": "error",
                "message": "User profile not found. Please complete profile setup."
            }, status=status.HTTP_404_NOT_FOUND)

        # Check if user is seeker
        if user_profile.user_type != 'seeker':
            return Response({
                "status": "error",
                "message": "Only seekers can access dashboard"
            }, status=status.HTTP_403_FORBIDDEN)

        # Allow access to dashboard even if profile incomplete
        # They can see what needs to be completed via profile_complete field in response

        # 1. Get search status from SeekerSearchPreference
        from apps.core.models import SeekerSearchPreference

        seeker_search = SeekerSearchPreference.objects.filter(user=user).first()
        search_status_data = {
            "is_searching": seeker_search.is_searching if seeker_search else False,
            "last_updated": seeker_search.last_search_at.isoformat() if seeker_search and seeker_search.last_search_at else None
        }

        # 2. Get wallet data (no subscription details for seekers)
        # Check if wallet exists, if not create it
        if hasattr(user_profile, 'wallet'):
            wallet = user_profile.wallet
        else:
            # Create wallet if doesn't exist
            from apps.profiles.models import Wallet
            wallet = Wallet.objects.create(
                user_profile=user_profile,
                balance=0.00,
                currency='INR'
            )

        wallet_data = {
            "balance": float(wallet.balance),
            "currency": wallet.currency
        }

        # 3. Get active services count (services with active WorkSession where seeker is the customer)
        from apps.profiles.work_assignment_models import WorkOrder, WorkSession

        active_services_count = WorkSession.objects.filter(
            work_order__seeker=user,
            connection_state='active'
        ).count()

        services_data = {
            "active_services": active_services_count
        }

        # 4. Get previous services (5 most recent, all statuses) - show provider name
        work_orders = WorkOrder.objects.filter(
            seeker=user
        ).select_related('provider__profile').order_by('-created_at')[:5]

        previous_services = []
        for order in work_orders:
            # Format date and time
            created_at = order.created_at
            date_str = created_at.strftime("%Y-%m-%d")
            time_str = created_at.strftime("%I:%M %p")

            previous_services.append({
                "provider_name": order.provider_profile.full_name if hasattr(order, 'provider_profile') else "Unknown",
                "date": date_str,
                "time": time_str,
                "status": order.status
            })

        # 5. Get active offers (sorted by priority, only active and not expired) - same as provider
        from apps.profiles.models import Offer
        from django.utils import timezone

        active_offers = Offer.objects.filter(
            is_active=True,
            valid_until__gt=timezone.now()
        ).order_by('priority', '-created_at')

        offers_data = []
        for offer in active_offers:
            offers_data.append({
                "offer_id": offer.offer_id,
                "title": offer.title,
                "description": offer.description,
                "image_url": offer.image_url,
                "valid_until": offer.valid_until.isoformat(),
                "is_active": offer.is_active,
                "priority": offer.priority
            })

        # 6. Get maintenance mode status (from the first offer record, default to False)
        maintenance_mode = False
        first_offer = Offer.objects.first()
        if first_offer:
            maintenance_mode = first_offer.maintenance_mode

        # Build response
        response_data = {
            "status": "success",
            "message": "seeker dashboard data fetched successfully",
            "data": {
                "profile_complete": user_profile.profile_complete,
                "search_status": search_status_data,
                "wallet": wallet_data,
                "services": services_data,
                "offers": offers_data,
                "previous_services": previous_services,
                "maintenance_mode": maintenance_mode
            }
        }

        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in seeker dashboard API: {str(e)}")
        return Response({
            "status": "error",
            "message": "An unexpected server error occurred. Please try again."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


