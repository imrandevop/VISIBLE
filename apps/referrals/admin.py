# apps/referrals/admin.py
from django.contrib import admin
from apps.referrals.models import ProviderReferral, ReferralReward


@admin.register(ProviderReferral)
class ProviderReferralAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'referred_provider_name',
        'referrer_provider_name',
        'referral_code_used',
        'status',
        'completed_at',
        'created_at'
    ]
    list_filter = ['status', 'created_at', 'completed_at']
    search_fields = [
        'referred_provider__full_name',
        'referrer_provider__full_name',
        'referral_code_used',
        'referred_provider__provider_id',
        'referrer_provider__provider_id'
    ]
    readonly_fields = ['created_at', 'updated_at', 'completed_at']
    raw_id_fields = ['referred_provider', 'referrer_provider']

    def referred_provider_name(self, obj):
        return obj.referred_provider.full_name
    referred_provider_name.short_description = 'Referred Provider'

    def referrer_provider_name(self, obj):
        return obj.referrer_provider.full_name
    referrer_provider_name.short_description = 'Referrer'


@admin.register(ReferralReward)
class ReferralRewardAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'provider_name',
        'reward_type',
        'amount',
        'currency',
        'is_credited',
        'credited_at',
        'created_at'
    ]
    list_filter = ['reward_type', 'is_credited', 'created_at', 'credited_at']
    search_fields = [
        'provider__full_name',
        'provider__provider_id',
        'referral__referral_code_used'
    ]
    readonly_fields = ['created_at', 'updated_at', 'credited_at']
    raw_id_fields = ['referral', 'provider']

    def provider_name(self, obj):
        return obj.provider.full_name
    provider_name.short_description = 'Provider'
