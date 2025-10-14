# apps/referrals/models.py
from django.db import models
from django.conf import settings
from apps.core.models import BaseModel
from apps.profiles.models import UserProfile


class ProviderReferral(BaseModel):
    """
    Tracks provider referrals - who referred whom
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    # The provider who was referred (new provider)
    referred_provider = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='referral_info',
        limit_choices_to={'user_type': 'provider'},
        help_text="The new provider who used a referral code"
    )

    # The provider who referred (existing provider)
    referrer_provider = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='referrals_made',
        limit_choices_to={'user_type': 'provider'},
        help_text="The existing provider who shared the referral code"
    )

    # Referral code used (stored for reference)
    referral_code_used = models.CharField(
        max_length=20,
        help_text="The provider_id used as referral code"
    )

    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='completed',
        help_text="Referral status"
    )

    # Timestamp for when referral was completed
    completed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the referral was successfully registered"
    )

    class Meta:
        verbose_name = "Provider Referral"
        verbose_name_plural = "Provider Referrals"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['referrer_provider', '-created_at']),
            models.Index(fields=['referred_provider']),
        ]

    def __str__(self):
        return f"{self.referred_provider.full_name} referred by {self.referrer_provider.full_name}"


class ReferralReward(BaseModel):
    """
    Tracks rewards given for referrals
    """
    REWARD_TYPE_CHOICES = [
        ('referrer', 'Referrer Reward'),
        ('referee', 'Referee Reward'),
    ]

    # Link to the referral
    referral = models.ForeignKey(
        ProviderReferral,
        on_delete=models.CASCADE,
        related_name='rewards'
    )

    # Provider who received the reward
    provider = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='referral_rewards'
    )

    # Reward details
    reward_type = models.CharField(
        max_length=20,
        choices=REWARD_TYPE_CHOICES,
        help_text="Type of reward: referrer (100 Rs) or referee (50 Rs)"
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Reward amount"
    )

    currency = models.CharField(
        max_length=3,
        default='INR'
    )

    # Whether the reward was successfully credited
    is_credited = models.BooleanField(
        default=False,
        help_text="Whether reward was credited to wallet"
    )

    credited_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When reward was credited to wallet"
    )

    class Meta:
        verbose_name = "Referral Reward"
        verbose_name_plural = "Referral Rewards"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['provider', '-created_at']),
        ]

    def __str__(self):
        return f"{self.reward_type} - {self.amount} {self.currency} for {self.provider.full_name}"
