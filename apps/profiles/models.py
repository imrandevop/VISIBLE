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
        ('skill', 'Skill'),
        ('vehicle', 'Vehicle'),
        ('properties', 'Properties'),
        ('SOS', 'Emergency Services'),
    ]

    SEEKER_TYPE_CHOICES = [
        ('individual', 'Individual'),
        ('business', 'Business'),
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

    # Seeker business profile fields
    seeker_type = models.CharField(max_length=15, choices=SEEKER_TYPE_CHOICES, null=True, blank=True, help_text="Type of seeker (individual or business)")
    business_name = models.CharField(max_length=200, null=True, blank=True, help_text="Business name for business-type seekers")
    business_location = models.CharField(max_length=300, null=True, blank=True, help_text="Business location/address")
    established_date = models.DateField(null=True, blank=True, help_text="Date when business was established")
    website = models.CharField(max_length=300, null=True, blank=True, help_text="Business website (optional, no validation)")

    # Provider service coverage area
    service_coverage_area = models.PositiveIntegerField(null=True, blank=True, help_text="Service coverage area in kilometers (how far the provider can travel)")

    profile_complete = models.BooleanField(default=False)
    can_access_app = models.BooleanField(default=False)

    # FCM Token for push notifications
    fcm_token = models.CharField(max_length=255, blank=True, null=True, help_text="Firebase Cloud Messaging token for push notifications")
    is_active_for_work = models.BooleanField(default=False, help_text="Provider is actively available for work assignments")

    # Role switching fields
    previous_user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES, null=True, blank=True, help_text="Previous user type before role switch")
    role_switch_count = models.PositiveIntegerField(default=0, help_text="Number of times user has switched roles")
    last_role_switch_date = models.DateTimeField(null=True, blank=True, help_text="Last time user switched roles")
    
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
            # Check if business-type seeker
            if self.seeker_type == 'business':
                # Business seekers need additional business fields
                business_complete = all([
                    self.business_name,
                    self.business_location,
                    self.established_date,
                    # website is optional
                ])
                if not business_complete:
                    self.profile_complete = False
                    self.can_access_app = False
                    self.save(update_fields=['profile_complete', 'can_access_app'])
                    return False

            # Individual seeker or business seeker with complete profile
            self.profile_complete = True
            self.can_access_app = True
            self.save(update_fields=['profile_complete', 'can_access_app'])
            return True

        elif self.user_type == 'provider':
            # Provider needs service-specific data and portfolio images

            # Check if this user recently switched from seeker to provider
            # If so, preserve can_access_app to allow them to complete provider profile
            was_seeker = self.previous_user_type == 'seeker'

            if not self.service_type:
                self.profile_complete = False
                # Preserve can_access_app for users who switched from seeker
                if not was_seeker:
                    self.can_access_app = False
                self.save(update_fields=['profile_complete', 'can_access_app'])
                return False

            # Check portfolio images (required for all provider types)
            portfolio_count = self.service_portfolio_images.count()
            if portfolio_count == 0:
                self.profile_complete = False
                # Preserve can_access_app for users who switched from seeker
                if not was_seeker:
                    self.can_access_app = False
                self.save(update_fields=['profile_complete', 'can_access_app'])
                return False

            # Check service-specific requirements
            service_complete = False

            if self.service_type == 'skill':
                # Skill needs work selection
                work_selection = hasattr(self, 'work_selection') and self.work_selection
                service_complete = work_selection is not None

            elif self.service_type == 'vehicle':
                # Vehicle needs vehicle service data
                vehicle_service = hasattr(self, 'vehicle_service') and self.vehicle_service
                service_complete = vehicle_service is not None

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
                # Preserve can_access_app for users who switched from seeker
                if not was_seeker:
                    self.can_access_app = False

            self.save(update_fields=['profile_complete', 'can_access_app'])
            return self.profile_complete

        self.profile_complete = False
        self.can_access_app = False
        self.save(update_fields=['profile_complete', 'can_access_app'])
        return False


class VehicleServiceData(BaseModel):
    """Vehicle-specific service data"""
    user_profile = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='vehicle_service'
    )
    vehicle_types = models.TextField(blank=True, null=True, help_text="Vehicle types as comma-separated")
    license_number = models.CharField(max_length=50)
    vehicle_registration_number = models.CharField(max_length=20)
    years_experience = models.IntegerField()
    driving_experience_description = models.TextField()
    service_offering_types = models.TextField(blank=True, null=True, help_text="Service offering types as comma-separated (rent, sale, lease, all)")

    def __str__(self):
        return f"{self.user_profile.full_name} - Vehicle Service"


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
    service_offering_types = models.TextField(blank=True, null=True, help_text="Service offering types as comma-separated (rent, sale, lease, all)")

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
    """User wallet for managing earnings, payments, and subscriptions"""
    user_profile = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='wallet'
    )
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    currency = models.CharField(max_length=3, default='INR')

    # Online subscription tracking
    last_online_payment_at = models.DateTimeField(null=True, blank=True, help_text="Last time ₹20 was paid for going online")
    online_subscription_expires_at = models.DateTimeField(null=True, blank=True, help_text="When the 24-hour online period expires")

    def __str__(self):
        return f"{self.user_profile.full_name} - Wallet: {self.balance} {self.currency}"

    def is_online_subscription_active(self):
        """Check if the 24-hour online subscription is still active"""
        from django.utils import timezone
        if self.online_subscription_expires_at:
            return timezone.now() < self.online_subscription_expires_at
        return False

    def deduct_online_charge(self):
        """Deduct ₹20 for 24-hour online access"""
        from django.utils import timezone
        from datetime import timedelta
        from decimal import Decimal

        ONLINE_CHARGE = Decimal('20.00')

        if self.balance < ONLINE_CHARGE:
            return False, "Insufficient balance. Please add money to your wallet."

        # Deduct the charge
        self.balance -= ONLINE_CHARGE
        self.last_online_payment_at = timezone.now()
        self.online_subscription_expires_at = timezone.now() + timedelta(hours=24)
        self.save()

        # Create transaction record
        WalletTransaction.objects.create(
            wallet=self,
            transaction_type='debit',
            amount=ONLINE_CHARGE,
            description='24-hour online subscription charge',
            balance_after=self.balance
        )

        return True, "Payment successful. You can go online/offline for the next 24 hours."

    class Meta:
        verbose_name = "User Wallet"
        verbose_name_plural = "User Wallets"


class WalletTransaction(BaseModel):
    """Transaction history for user wallet"""
    TRANSACTION_TYPE_CHOICES = [
        ('credit', 'Credit'),
        ('debit', 'Debit'),
    ]

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.TextField(help_text="Transaction description")
    balance_after = models.DecimalField(max_digits=10, decimal_places=2, help_text="Wallet balance after transaction")

    def __str__(self):
        return f"{self.wallet.user_profile.full_name} - {self.transaction_type.upper()} ₹{self.amount}"

    class Meta:
        verbose_name = "Wallet Transaction"
        verbose_name_plural = "Wallet Transactions"
        ordering = ['-created_at']


class Offer(BaseModel):
    """Global offers shown to all providers on dashboard"""
    offer_id = models.CharField(max_length=20, unique=True, editable=False, help_text="Auto-generated unique offer ID")
    title = models.CharField(max_length=200, help_text="Offer title")
    description = models.TextField(help_text="Offer description")
    image_url = models.URLField(max_length=500, help_text="Offer image URL")
    valid_until = models.DateTimeField(help_text="Offer validity end date")
    is_active = models.BooleanField(default=True, help_text="Offer active status")
    priority = models.PositiveIntegerField(default=999, help_text="Display priority (lower number = higher priority)")
    maintenance_mode = models.BooleanField(default=False, help_text="App maintenance mode (affects all users)")

    def __str__(self):
        return f"{self.offer_id} - {self.title}"

    def save(self, *args, **kwargs):
        """Auto-generate unique offer_id if not set"""
        if not self.offer_id:
            self.offer_id = self.generate_unique_offer_id()

        # Auto-update is_active based on valid_until
        from django.utils import timezone
        if self.valid_until and timezone.now() > self.valid_until:
            self.is_active = False

        super().save(*args, **kwargs)

    def generate_unique_offer_id(self):
        """Generate unique offer ID with pattern: OFF + 3 digits"""
        counter = 1
        while True:
            offer_id = f"OFF{counter:03d}"
            if not Offer.objects.filter(offer_id=offer_id).exists():
                return offer_id
            counter += 1

    class Meta:
        ordering = ['priority', '-created_at']
        verbose_name = "Offer"
        verbose_name_plural = "Offers"


class RoleSwitchHistory(BaseModel):
    """Track history of role switches for users"""
    user_profile = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name='role_switch_history'
    )
    from_user_type = models.CharField(max_length=10, choices=UserProfile.USER_TYPE_CHOICES, null=True, blank=True)
    to_user_type = models.CharField(max_length=10, choices=UserProfile.USER_TYPE_CHOICES)
    switch_date = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True, null=True, help_text="Optional reason for role switch")

    def __str__(self):
        from_type = self.from_user_type or "None"
        return f"{self.user_profile.full_name}: {from_type} → {self.to_user_type} on {self.switch_date.strftime('%Y-%m-%d')}"

    class Meta:
        ordering = ['-switch_date']
        verbose_name = "Role Switch History"
        verbose_name_plural = "Role Switch Histories"


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
