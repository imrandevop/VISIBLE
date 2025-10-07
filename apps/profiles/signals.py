# apps/profiles/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import UserProfile, Wallet
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=UserProfile)
def create_provider_wallet(sender, instance, created, **kwargs):
    """
    Automatically create a wallet when a provider profile is created
    """
    # Only create wallet for providers
    if instance.user_type == 'provider':
        # Check if wallet doesn't exist
        if not hasattr(instance, 'wallet'):
            try:
                Wallet.objects.create(
                    user_profile=instance,
                    balance=0.00,
                    currency='INR'
                )
                logger.info(f"✅ Wallet created for provider: {instance.full_name}")
            except Exception as e:
                logger.error(f"❌ Error creating wallet for provider {instance.id}: {e}")
