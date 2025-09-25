#apps\core\models.py
from django.db import models
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError
from django.conf import settings
import math

class BaseModel(models.Model):
    """Base model with common fields"""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class ActiveManager(models.Manager):
    """Manager to get only active records"""
    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)

def validate_image_size(value):
    """Validate image file size (max 2MB)"""
    limit = 2 * 1024 * 1024  # 2MB
    if value.size > limit:
        raise ValidationError('File too large. Size should not exceed 2 MB.')

def user_profile_photo_path(instance, filename):
    """Generate upload path for user profile photos"""
    return f'profiles/{instance.user.id}/profile_{filename}'

def work_portfolio_path(instance, filename):
    """Generate upload path for work portfolio images"""
    return f'portfolios/{instance.user_work_selection.user.id}/{filename}'


# Location and Status Tracking Models

class ProviderActiveStatus(BaseModel):
    """Track provider active status and location"""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='provider_status'
    )
    is_active = models.BooleanField(default=False)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    main_category = models.ForeignKey(
        'work_categories.WorkCategory',
        on_delete=models.CASCADE,
        null=True, blank=True
    )
    sub_category = models.ForeignKey(
        'work_categories.WorkSubCategory',
        on_delete=models.CASCADE,
        null=True, blank=True
    )
    last_active_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.mobile_number} - {'Active' if self.is_active else 'Inactive'}"


class SeekerSearchPreference(BaseModel):
    """Store seeker search preferences and status"""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='search_preference'
    )
    is_searching = models.BooleanField(default=False)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    searching_category = models.ForeignKey(
        'work_categories.WorkCategory',
        on_delete=models.CASCADE,
        null=True, blank=True
    )
    distance_radius = models.IntegerField(default=5)  # in kilometers
    last_search_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.mobile_number} - {'Searching' if self.is_searching else 'Not Searching'}"


def calculate_distance(lat1, lng1, lat2, lng2):
    """
    Calculate distance between two points using Haversine formula
    Returns distance in kilometers
    """
    if not all([lat1, lng1, lat2, lng2]):
        return float('inf')

    # Convert latitude and longitude from degrees to radians
    lat1_rad = math.radians(lat1)
    lng1_rad = math.radians(lng1)
    lat2_rad = math.radians(lat2)
    lng2_rad = math.radians(lng2)

    # Haversine formula
    dlat = lat2_rad - lat1_rad
    dlng = lng2_rad - lng1_rad

    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlng/2)**2
    c = 2 * math.asin(math.sqrt(a))

    # Earth's radius in kilometers
    earth_radius = 6371

    return earth_radius * c