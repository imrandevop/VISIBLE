# apps/profiles/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction

from apps.profiles.serializers import ProfileSetupSerializer, ProfileResponseSerializer, WalletSerializer, RoleSwitchSerializer
from apps.profiles.models import UserProfile, Wallet
from apps.core.models import ProviderActiveStatus

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_wallet_details_api(request, version=None):
    """
    Get user's wallet details including balance, subscription status, and recent transactions
    Works for both providers and seekers

    GET /api/1/profiles/wallet/

    Headers:
        Authorization: Bearer <jwt_token>

    Response:
        Success (200):
        {
            "status": "success",
            "message": "Wallet details fetched successfully",
            "data": {
                "id": 1,
                "balance": 850.00,
                "currency": "INR",
                "last_online_payment_at": "2025-10-14T10:30:00Z",
                "online_subscription_expires_at": "2025-10-15T10:30:00Z",
                "is_online_subscription_active": true,
                "online_subscription_time_remaining": "12h 0m",
                "recent_transactions": [
                    {
                        "id": 1,
                        "transaction_type": "debit",
                        "amount": 20.00,
                        "description": "24-hour online subscription charge",
                        "balance_after": 830.00,
                        "created_at": "2025-10-14T10:30:00Z"
                    },
                    ...
                ],
                "created_at": "2025-10-01T08:00:00Z",
                "updated_at": "2025-10-14T10:30:00Z"
            }
        }

        Error (404):
        {
            "status": "error",
            "message": "User profile not found. Please complete profile setup."
        }
    """
    try:
        user = request.user

        # Check if user has profile
        try:
            user_profile = UserProfile.objects.get(user=user)
        except UserProfile.DoesNotExist:
            return Response({
                "status": "error",
                "message": "User profile not found. Please complete profile setup."
            }, status=status.HTTP_404_NOT_FOUND)

        # Get or create wallet for both providers and seekers
        wallet, created = Wallet.objects.get_or_create(
            user_profile=user_profile,
            defaults={
                'balance': 0.00,
                'currency': 'INR'
            }
        )

        # Serialize wallet data
        serializer = WalletSerializer(wallet, context={'request': request})

        return Response({
            "status": "success",
            "message": "Wallet details fetched successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_wallet_details_api: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return Response({
            "status": "error",
            "message": "An unexpected server error occurred. Please try again."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def switch_role_api(request):
    """
    Switch user role between seeker and provider.

    POST /api/1/profiles/switch-role/

    Request body:
    {
        "new_user_type": "provider"  # or "seeker"
    }

    Response:
    {
        "status": "success",
        "message": "Role switched successfully from seeker to provider",
        "access_token": "new_jwt_token...",
        "refresh_token": "new_refresh_token...",
        "data": {
            ... updated profile data ...
        }
    }

    Error responses:
    - 400: Validation errors (active work orders, invalid data, etc.)
    - 404: User profile not found
    - 500: Server error
    """
    try:
        from apps.authentication.utils.jwt_utils import get_tokens_for_user

        # Get user profile
        try:
            user_profile = request.user.profile
        except UserProfile.DoesNotExist:
            return Response({
                "status": "error",
                "message": "User profile not found. Please complete profile setup first."
            }, status=status.HTTP_404_NOT_FOUND)

        # Validate and process role switch
        serializer = RoleSwitchSerializer(
            data=request.data,
            context={'request': request}
        )

        if not serializer.is_valid():
            # Extract error message
            errors = serializer.errors
            if 'error' in errors:
                error_message = errors['error'][0] if isinstance(errors['error'], list) else errors['error']
            else:
                error_message = str(errors)

            return Response({
                "status": "error",
                "message": error_message,
                "errors": errors
            }, status=status.HTTP_400_BAD_REQUEST)

        # Perform role switch
        previous_type = user_profile.user_type
        updated_profile = serializer.save()
        new_type = updated_profile.user_type

        # Generate NEW JWT tokens with updated user_type
        new_tokens = get_tokens_for_user(request.user)

        # Get updated profile data
        from apps.profiles.serializers import ProfileResponseSerializer
        profile_serializer = ProfileResponseSerializer(updated_profile, context={'request': request})

        return Response({
            "status": "success",
            "message": f"Role switched successfully from {previous_type} to {new_type}",
            "access_token": new_tokens['access_token'],
            "refresh_token": new_tokens['refresh_token'],
            "data": profile_serializer.data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in switch_role_api: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return Response({
            "status": "error",
            "message": "An unexpected server error occurred. Please try again."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)