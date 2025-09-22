#apps\profiles\models.py
from django.db import models
from django.conf import settings
from apps.core.models import BaseModel, user_profile_photo_path, validate_image_size
from django.core.validators import FileExtensionValidator
import random
import string
from datetime import date

class UserProfile(BaseModel):
    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
    ]
    
    USER_TYPE_CHOICES = [
        ('provider', 'Provider'),
        ('seeker', 'Seeker'),
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
    languages = models.TextField(blank=True, null=True, help_text="Languages spoken by the user")
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
            # Provider needs work selection and portfolio
            work_selection = hasattr(self, 'work_selection') and self.work_selection
            if not work_selection:
                self.profile_complete = False
                self.can_access_app = False
                self.save(update_fields=['profile_complete', 'can_access_app'])
                return False
                
            # Check if portfolio images exist (at least 1)
            portfolio_images = work_selection.portfolio_images.count() if work_selection else 0
            if portfolio_images > 0:
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
    
    