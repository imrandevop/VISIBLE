# apps/profiles/communication_models.py
from django.db import models
from django.conf import settings
from apps.core.models import BaseModel

class CommunicationSettings(BaseModel):
    """Communication settings for users (primarily providers)"""

    user_profile = models.OneToOneField(
        'profiles.UserProfile',
        on_delete=models.CASCADE,
        related_name='communication_settings'
    )

    # Telegram settings
    telegram_enabled = models.BooleanField(default=False)
    telegram_value = models.CharField(max_length=100, blank=True, null=True)

    # WhatsApp settings
    whatsapp_enabled = models.BooleanField(default=False)
    whatsapp_value = models.CharField(max_length=100, blank=True, null=True)

    # Call settings
    call_enabled = models.BooleanField(default=False)
    call_value = models.CharField(max_length=15, blank=True, null=True, help_text="10-digit phone number")

    # Map location settings
    map_location_enabled = models.BooleanField(default=False)
    map_location_value = models.URLField(blank=True, null=True, help_text="Google Maps link")

    # Website settings
    website_enabled = models.BooleanField(default=False)
    website_value = models.URLField(blank=True, null=True, help_text="Website URL")

    # Instagram settings
    instagram_enabled = models.BooleanField(default=False)
    instagram_value = models.URLField(blank=True, null=True, help_text="Instagram profile link")

    # Facebook settings
    facebook_enabled = models.BooleanField(default=False)
    facebook_value = models.URLField(blank=True, null=True, help_text="Facebook profile link")

    # Land mark
    land_mark = models.CharField(max_length=255, blank=True, null=True, help_text="Physical landmark or address")

    # UPI ID
    upi_ID = models.CharField(max_length=100, blank=True, null=True, help_text="UPI payment ID")

    def __str__(self):
        return f"{self.user_profile.full_name} - Communication Settings"

    class Meta:
        verbose_name = "Communication Settings"
        verbose_name_plural = "Communication Settings"