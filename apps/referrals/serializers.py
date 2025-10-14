# apps/referrals/serializers.py
from rest_framework import serializers
from apps.referrals.models import ProviderReferral, ReferralReward
from apps.profiles.models import UserProfile


class ApplyReferralCodeSerializer(serializers.Serializer):
    """
    Serializer for applying referral code when provider registers
    """
    referral_code = serializers.CharField(
        max_length=20,
        required=True,
        help_text="Provider ID to use as referral code"
    )

    def validate_referral_code(self, value):
        """
        Validate that the referral code exists and is valid
        """
        # Check if referral code (provider_id) exists
        try:
            referrer = UserProfile.objects.get(
                provider_id=value,
                user_type='provider'
            )
        except UserProfile.DoesNotExist:
            raise serializers.ValidationError("Invalid referral code. Please check and try again.")

        # Store referrer in context for use in create method
        self.context['referrer'] = referrer

        return value

    def validate(self, attrs):
        """
        Additional validation to prevent self-referral and duplicate referrals
        """
        request = self.context.get('request')
        referral_code = attrs.get('referral_code')

        # Get current user's profile
        try:
            current_profile = UserProfile.objects.get(user=request.user)
        except UserProfile.DoesNotExist:
            raise serializers.ValidationError("User profile not found. Please complete profile setup first.")

        # Check if user is a provider
        if current_profile.user_type != 'provider':
            raise serializers.ValidationError("Only providers can use referral codes.")

        # Prevent self-referral
        if current_profile.provider_id == referral_code:
            raise serializers.ValidationError("You cannot use your own referral code.")

        # Check if user has already used a referral code
        if ProviderReferral.objects.filter(referred_provider=current_profile).exists():
            raise serializers.ValidationError("You have already used a referral code. Each provider can only use one referral code.")

        # Store current profile in context
        self.context['current_profile'] = current_profile

        return attrs


class ReferralStatsSerializer(serializers.Serializer):
    """
    Serializer for GET endpoint - returns referral statistics
    """
    referralCode = serializers.CharField(source='provider_id')
    referralCount = serializers.IntegerField()
    totalEarned = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField()
    rewardPerReferral = serializers.DecimalField(max_digits=10, decimal_places=2)
    stats = serializers.DictField()
    recentReferrals = serializers.ListField()


class RecentReferralSerializer(serializers.Serializer):
    """
    Serializer for individual referral in the recentReferrals list
    """
    friendName = serializers.CharField()
    status = serializers.CharField()
    rewardAmount = serializers.DecimalField(max_digits=10, decimal_places=2)
    referredAt = serializers.DateTimeField()
    completedAt = serializers.DateTimeField()
