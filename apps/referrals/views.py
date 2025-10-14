# apps/referrals/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.utils import timezone
from decimal import Decimal

from apps.referrals.models import ProviderReferral, ReferralReward
from apps.referrals.serializers import ApplyReferralCodeSerializer
from apps.profiles.models import UserProfile, Wallet, WalletTransaction


# Referral reward amounts
REFERRER_REWARD = Decimal('100.00')  # Existing provider gets 100 Rs
REFEREE_REWARD = Decimal('50.00')    # New provider gets 50 Rs


@api_view(['POST', 'GET'])
@permission_classes([IsAuthenticated])
def referral_api(request, version=None):
    """
    Referral API - handles both POST (apply referral code) and GET (get referral stats)

    POST /api/1/referral/
    Apply a referral code for a new provider

    Headers:
        Authorization: Bearer <jwt_token>
        Content-Type: application/json

    Body:
        {
            "referral_code": "AB12345678"
        }

    Response:
        Success (200):
        {
            "success": true,
            "message": "Referral code applied successfully! You earned ₹50 and your referrer earned ₹100",
            "data": {
                "referrer_reward": 100.00,
                "referee_reward": 50.00,
                "your_new_balance": 50.00
            }
        }

        Error (400):
        {
            "success": false,
            "message": "Validation error message",
            "errors": {...}
        }

    ---

    GET /api/1/referral/
    Get referral statistics for the current provider

    Headers:
        Authorization: Bearer <jwt_token>

    Response:
        Success (200):
        {
            "success": true,
            "message": "Referral data retrieved successfully",
            "data": {
                "referralCode": "AB12345678",
                "referralCount": 5,
                "totalEarned": 500.0,
                "currency": "INR",
                "rewardPerReferral": 100.0,
                "stats": {
                    "totalReferrals": 5,
                    "pendingReferrals": 0,
                    "completedReferrals": 5
                },
                "recentReferrals": [
                    {
                        "friendName": "John Doe",
                        "status": "completed",
                        "rewardAmount": 100.0,
                        "referredAt": "2025-10-10T14:30:00Z",
                        "completedAt": "2025-10-10T14:30:00Z"
                    }
                ]
            }
        }
    """

    if request.method == 'POST':
        return apply_referral_code(request)
    elif request.method == 'GET':
        return get_referral_stats(request)


def apply_referral_code(request):
    """
    POST endpoint - Apply referral code and credit rewards to both providers
    """
    try:
        # Validate input
        serializer = ApplyReferralCodeSerializer(
            data=request.data,
            context={'request': request}
        )

        if not serializer.is_valid():
            return Response({
                "success": False,
                "message": "Validation failed",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get validated data from context
        referrer = serializer.context['referrer']
        current_profile = serializer.context['current_profile']
        referral_code = serializer.validated_data['referral_code']

        # Create referral and rewards in a transaction
        with transaction.atomic():
            # 1. Create ProviderReferral record
            provider_referral = ProviderReferral.objects.create(
                referred_provider=current_profile,
                referrer_provider=referrer,
                referral_code_used=referral_code,
                status='completed',
                completed_at=timezone.now()
            )

            # 2. Get or create wallets for both providers
            referrer_wallet, _ = Wallet.objects.get_or_create(
                user_profile=referrer,
                defaults={'balance': Decimal('0.00'), 'currency': 'INR'}
            )

            referee_wallet, _ = Wallet.objects.get_or_create(
                user_profile=current_profile,
                defaults={'balance': Decimal('0.00'), 'currency': 'INR'}
            )

            # 3. Credit reward to referrer (existing provider) - 100 Rs
            referrer_wallet.balance += REFERRER_REWARD
            referrer_wallet.save()

            # Create referrer reward record
            referrer_reward = ReferralReward.objects.create(
                referral=provider_referral,
                provider=referrer,
                reward_type='referrer',
                amount=REFERRER_REWARD,
                currency='INR',
                is_credited=True,
                credited_at=timezone.now()
            )

            # Create wallet transaction for referrer
            WalletTransaction.objects.create(
                wallet=referrer_wallet,
                transaction_type='credit',
                amount=REFERRER_REWARD,
                description=f'Referral reward for referring {current_profile.full_name}',
                balance_after=referrer_wallet.balance
            )

            # 4. Credit reward to referee (new provider) - 50 Rs
            referee_wallet.balance += REFEREE_REWARD
            referee_wallet.save()

            # Create referee reward record
            referee_reward = ReferralReward.objects.create(
                referral=provider_referral,
                provider=current_profile,
                reward_type='referee',
                amount=REFEREE_REWARD,
                currency='INR',
                is_credited=True,
                credited_at=timezone.now()
            )

            # Create wallet transaction for referee
            WalletTransaction.objects.create(
                wallet=referee_wallet,
                transaction_type='credit',
                amount=REFEREE_REWARD,
                description=f'Referral reward for joining with code {referral_code}',
                balance_after=referee_wallet.balance
            )

        # Return success response
        return Response({
            "success": True,
            "message": f"Referral code applied successfully! You earned ₹{REFEREE_REWARD} and your referrer earned ₹{REFERRER_REWARD}",
            "data": {
                "referrer_reward": float(REFERRER_REWARD),
                "referee_reward": float(REFEREE_REWARD),
                "your_new_balance": float(referee_wallet.balance)
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in apply_referral_code: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

        return Response({
            "success": False,
            "message": "An unexpected server error occurred. Please try again."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def get_referral_stats(request):
    """
    GET endpoint - Get referral statistics for current provider
    """
    try:
        # Get current user's profile
        try:
            current_profile = UserProfile.objects.get(user=request.user)
        except UserProfile.DoesNotExist:
            return Response({
                "success": False,
                "message": "User profile not found. Please complete profile setup first."
            }, status=status.HTTP_404_NOT_FOUND)

        # Check if user is a provider
        if current_profile.user_type != 'provider':
            return Response({
                "success": False,
                "message": "Only providers can access referral statistics."
            }, status=status.HTTP_403_FORBIDDEN)

        # Get all referrals made by this provider
        referrals_made = ProviderReferral.objects.filter(
            referrer_provider=current_profile
        ).select_related('referred_provider')

        # Calculate statistics
        total_referrals = referrals_made.count()
        completed_referrals = referrals_made.filter(status='completed').count()
        pending_referrals = referrals_made.filter(status='pending').count()

        # Calculate total earned from referrals
        referrer_rewards = ReferralReward.objects.filter(
            provider=current_profile,
            reward_type='referrer',
            is_credited=True
        )
        total_earned = sum(reward.amount for reward in referrer_rewards)

        # Get recent referrals (last 10)
        recent_referrals = []
        for referral in referrals_made.order_by('-created_at')[:10]:
            recent_referrals.append({
                "friendName": referral.referred_provider.full_name,
                "status": referral.status,
                "rewardAmount": float(REFERRER_REWARD),
                "referredAt": referral.completed_at.isoformat() if referral.completed_at else referral.created_at.isoformat(),
                "completedAt": referral.completed_at.isoformat() if referral.completed_at else None
            })

        # Build response data
        response_data = {
            "referralCode": current_profile.provider_id,
            "referralCount": total_referrals,
            "totalEarned": float(total_earned),
            "currency": "INR",
            "rewardPerReferral": float(REFERRER_REWARD),
            "stats": {
                "totalReferrals": total_referrals,
                "pendingReferrals": pending_referrals,
                "completedReferrals": completed_referrals
            },
            "recentReferrals": recent_referrals
        }

        return Response({
            "success": True,
            "message": "Referral data retrieved successfully",
            "data": response_data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_referral_stats: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

        return Response({
            "success": False,
            "message": "An unexpected server error occurred. Please try again."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
