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

    # FCM Token for push notifications
    fcm_token = models.CharField(max_length=255, blank=True, null=True, help_text="Firebase Cloud Messaging token for push notifications")
    is_active_for_work = models.BooleanField(default=False, help_text="Provider is actively available for work assignments")
    
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
    years_experience = models.IntegerField()
    driving_experience_description = models.TextField()

    def __str__(self):
        return f"{self.user_profile.full_name} - Driver Service"


class PropertyServiceData(BaseModel):
    """Property-specific service data"""
    PARKING_CHOICES = [
        ('Yes', 'Yes'),
        ('No', 'No'),
    ]

    FURNISHING_CHOICES = [
        ('Fully Furnished', 'Fully Furnished'),
        ('Semi Furnished', 'Semi Furnished'),
        ('Unfurnished', 'Unfurnished'),
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

    @property
    def user(self):
        """Provide user property for compatibility"""
        return self.user_profile

    def __str__(self):
        return f"{self.user_profile.full_name} - Portfolio Image {self.image_order}"


class ProviderRating(BaseModel):
    """Provider rating and review summary"""
    provider = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='rating_summary',
        limit_choices_to={'user_type': 'provider'}
    )
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_reviews = models.PositiveIntegerField(default=0)
    five_star_count = models.PositiveIntegerField(default=0)
    four_star_count = models.PositiveIntegerField(default=0)
    three_star_count = models.PositiveIntegerField(default=0)
    two_star_count = models.PositiveIntegerField(default=0)
    one_star_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.provider.full_name} - {self.average_rating}★ ({self.total_reviews} reviews)"

    def get_formatted_total_reviews(self):
        """Format total reviews count (472000 → '472K')"""
        if self.total_reviews >= 1000000:
            return f"{self.total_reviews / 1000000:.1f}M"
        elif self.total_reviews >= 1000:
            return f"{self.total_reviews // 1000}K"
        else:
            return str(self.total_reviews)

    def get_rating_distribution(self):
        """Get rating distribution with formatted counts"""
        def format_count(count):
            if count >= 1000000:
                return f"{count / 1000000:.1f}M"
            elif count >= 1000:
                return f"{count // 1000}K"
            else:
                return str(count)

        return {
            "5_star": format_count(self.five_star_count),
            "4_star": format_count(self.four_star_count),
            "3_star": format_count(self.three_star_count),
            "2_star": format_count(self.two_star_count),
            "1_star": format_count(self.one_star_count)
        }


class ProviderReview(BaseModel):
    """Individual provider reviews"""
    provider = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='reviews',
        limit_choices_to={'user_type': 'provider'}
    )
    reviewer_name = models.CharField(max_length=100)
    rating = models.PositiveIntegerField(choices=[(i, i) for i in range(1, 6)])  # 1-5 stars
    review_text = models.TextField()
    review_date = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    class Meta:
        ordering = ['-review_date']

    def __str__(self):
        return f"{self.reviewer_name} - {self.rating}★ for {self.provider.full_name}"

    def get_formatted_date(self):
        """Format date as 'Sep 27, 2025'"""
        return self.review_date.strftime("%b %d, %Y")


class Wallet(BaseModel):
    """Provider wallet for managing earnings"""
    user_profile = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='wallet',
        limit_choices_to={'user_type': 'provider'}
    )
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    currency = models.CharField(max_length=3, default='INR')

    def __str__(self):
        return f"{self.user_profile.full_name} - Wallet: {self.balance} {self.currency}"

    class Meta:
        verbose_name = "Provider Wallet"
        verbose_name_plural = "Provider Wallets"


# Import communication models
from .communication_models import CommunicationSettings

# Import work assignment models
from .work_assignment_models import (
    WorkOrder,
    WorkAssignmentNotification,
    WorkSession,
    ChatMessage,
    TypingIndicator
)
