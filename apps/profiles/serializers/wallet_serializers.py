# apps/profiles/serializers/wallet_serializers.py
"""
Wallet and transaction serializers.
"""
from rest_framework import serializers
from apps.profiles.models import Wallet, WalletTransaction

class WalletTransactionSerializer(serializers.ModelSerializer):
    """Serializer for wallet transaction details"""

    class Meta:
        model = WalletTransaction
        fields = [
            'id',
            'transaction_type',
            'amount',
            'description',
            'balance_after',
            'created_at'
        ]
        read_only_fields = fields


class WalletSerializer(serializers.ModelSerializer):
    """Serializer for wallet details"""
    is_online_subscription_active = serializers.SerializerMethodField()
    online_subscription_time_remaining = serializers.SerializerMethodField()
    recent_transactions = serializers.SerializerMethodField()

    class Meta:
        model = Wallet
        fields = [
            'id',
            'balance',
            'currency',
            'last_online_payment_at',
            'online_subscription_expires_at',
            'is_online_subscription_active',
            'online_subscription_time_remaining',
            'recent_transactions',
            'created_at',
            'updated_at'
        ]
        read_only_fields = fields

    def get_is_online_subscription_active(self, obj):
        """Check if online subscription is currently active"""
        return obj.is_online_subscription_active()

    def get_online_subscription_time_remaining(self, obj):
        """Get time remaining in 'Xh Ym' format for online subscription, or None if expired/not active"""
        from django.utils import timezone

        if obj.online_subscription_expires_at:
            now = timezone.now()
            if now < obj.online_subscription_expires_at:
                time_diff = obj.online_subscription_expires_at - now
                total_seconds = int(time_diff.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                return f"{hours}h {minutes}m"
        return None

    def get_recent_transactions(self, obj):
        """Get recent transactions (last 10)"""
        transactions = obj.transactions.all()[:10]
        return WalletTransactionSerializer(transactions, many=True).data


