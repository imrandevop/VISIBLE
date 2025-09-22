#apps\profiles\models.py
from django.db import models
from django.conf import settings
from apps.core.models import BaseModel, user_profile_photo_path, validate_image_size
from django.core.validators import FileExtensionValidator

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
    profile_complete = models.BooleanField(default=False)
    can_access_app = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.full_name} ({self.user.mobile_number})"
    
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
    
    