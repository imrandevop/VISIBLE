#apps\profiles\models.py
from django.db import models
from django.conf import settings
from apps.core.models import BaseModel, user_profile_photo_path, validate_image_size
from django.core.validators import FileExtensionValidator
import random
import string
from datetime import date

def default_list():
    return []

class UserProfile(BaseModel):
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
    ]
    
    USER_TYPE_CHOICES = [
        ('provider', 'Provider'),
        ('seeker', 'Seeker'),
    ]

    SERVICE_TYPE_CHOICES = [
        ('worker', 'Worker'),
        ('driver', 'Driver'),
        ('properties', 'Properties'),
        ('SOS', 'Emergency Services'),
    ]
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name='profile'
    )
    full_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    profile_photo = models.ImageField(
        upload_to=user_profile_photo_path,
        validators=[
            FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png']),
            validate_image_size
        ],
        null=True,
        blank=True
    )
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES, null=True, blank=True)
    service_type = models.CharField(max_length=15, choices=SERVICE_TYPE_CHOICES, null=True, blank=True, help_text="Service type for providers")
    languages = models.TextField(blank=True, null=True, help_text="Languages spoken by the user as comma-separated")
    provider_id = models.CharField(max_length=10, unique=True, blank=True, null=True, help_text="Unique provider ID (2 letters + 8 digits)")
    profile_complete = models.BooleanField(default=False)
    can_access_app = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.full_name} ({self.user.mobile_number})"

    def save(self, *args, **kwargs):
        """Override save to generate provider_id for providers"""
        if self.user_type == 'provider' and not self.provider_id:
            self.provider_id = self.generate_unique_provider_id()
        super().save(*args, **kwargs)

    def generate_unique_provider_id(self):
        """Generate unique provider ID with pattern: 2 alphabets + 8 digits"""
        while True:
            # Generate 2 random uppercase letters
            letters = ''.join(random.choices(string.ascii_uppercase, k=2))
            # Generate 8 random digits
            digits = ''.join(random.choices(string.digits, k=8))
            provider_id = letters + digits

            # Check if this ID already exists
            if not UserProfile.objects.filter(provider_id=provider_id).exists():
                return provider_id

    @property
    def age(self):
        """Calculate age from date of birth"""
        if self.date_of_birth:
            today = date.today()
            return today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        return None

    @property
    def mobile_number(self):
        """Get mobile number from authenticated user"""
        return self.user.mobile_number if self.user else None

    def check_profile_completion(self):
        """Check and update profile completion status"""
        if not self.user_type:
            self.profile_complete = False
            self.can_access_app = False
            self.save(update_fields=['profile_complete', 'can_access_app'])
            return False

        # Basic profile requirements
        basic_complete = all([
            self.full_name,
            self.date_of_birth,
            self.gender,
        ])

        if not basic_complete:
            self.profile_complete = False
            self.can_access_app = False
            self.save(update_fields=['profile_complete', 'can_access_app'])
            return False

        if self.user_type == 'seeker':
            # Seeker just needs basic profile
            self.profile_complete = True
            self.can_access_app = True
            self.save(update_fields=['profile_complete', 'can_access_app'])
            return True

        elif self.user_type == 'provider':
            # Provider needs service-specific data and portfolio images
            if not self.service_type:
                self.profile_complete = False
                self.can_access_app = False
                self.save(update_fields=['profile_complete', 'can_access_app'])
                return False

            # Check portfolio images (required for all provider types)
            portfolio_count = self.service_portfolio_images.count()
            if portfolio_count == 0:
                self.profile_complete = False
                self.can_access_app = False
                self.save(update_fields=['profile_complete', 'can_access_app'])
                return False

            # Check service-specific requirements
            service_complete = False

            if self.service_type == 'worker':
                # Worker needs work selection
                work_selection = hasattr(self, 'work_selection') and self.work_selection
                service_complete = work_selection is not None

            elif self.service_type == 'driver':
                # Driver needs driver service data
                driver_service = hasattr(self, 'driver_service') and self.driver_service
                service_complete = driver_service is not None

            elif self.service_type == 'properties':
                # Properties needs property service data
                property_service = hasattr(self, 'property_service') and self.property_service
                service_complete = property_service is not None

            elif self.service_type == 'SOS':
                # SOS needs emergency service data
                sos_service = hasattr(self, 'sos_service') and self.sos_service
                service_complete = sos_service is not None

            if service_complete:
                self.profile_complete = True
                self.can_access_app = True
            else:
                self.profile_complete = False
                self.can_access_app = False

            self.save(update_fields=['profile_complete', 'can_access_app'])
            return self.profile_complete

        self.profile_complete = False
        self.can_access_app = False
        self.save(update_fields=['profile_complete', 'can_access_app'])
        return False


class DriverServiceData(BaseModel):
    """Driver-specific service data"""
    user_profile = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='driver_service'
    )
    vehicle_types = models.TextField(blank=True, null=True, help_text="Vehicle types as comma-separated")
    license_number = models.CharField(max_length=50)
    vehicle_registration_number = models.CharField(max_length=20)
    driving_years_experience = models.IntegerField()
    driving_experience_description = models.TextField()

    def __str__(self):
        return f"{self.user_profile.full_name} - Driver Service"


class PropertyServiceData(BaseModel):
    """Property-specific service data"""
    PARKING_CHOICES = [
        ('available', 'Available'),
        ('not_available', 'Not Available'),
        ('street_parking', 'Street Parking'),
    ]

    FURNISHING_CHOICES = [
        ('furnished', 'Furnished'),
        ('semi_furnished', 'Semi Furnished'),
        ('unfurnished', 'Unfurnished'),
    ]

    user_profile = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='property_service'
    )
    property_types = models.TextField(blank=True, null=True, help_text="Property types as comma-separated")
    property_title = models.CharField(max_length=200)
    parking_availability = models.CharField(max_length=20, choices=PARKING_CHOICES, null=True, blank=True)
    furnishing_type = models.CharField(max_length=20, choices=FURNISHING_CHOICES, null=True, blank=True)
    property_description = models.TextField()

    def __str__(self):
        return f"{self.user_profile.full_name} - Property Service: {self.property_title}"


class SOSServiceData(BaseModel):
    """Emergency (SOS) service data"""
    user_profile = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='sos_service'
    )
    emergency_service_types = models.TextField(blank=True, null=True, help_text="Emergency service types as comma-separated")
    contact_number = models.CharField(max_length=15)
    current_location = models.TextField()
    emergency_description = models.TextField()

    def __str__(self):
        return f"{self.user_profile.full_name} - Emergency Service"


class ServicePortfolioImage(BaseModel):
    """Portfolio images for all service types (max 3 per user)"""
    user_profile = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='service_portfolio_images'
    )
    image = models.ImageField(
        upload_to=user_profile_photo_path,
        validators=[
            FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png']),
            validate_image_size
        ]
    )
    image_order = models.IntegerField()  # 1, 2, or 3

    class Meta:
        unique_together = ['user_profile', 'image_order']
        ordering = ['image_order']

    def __str__(self):
        return f"{self.user_profile.full_name} - Portfolio Image {self.image_order}"

