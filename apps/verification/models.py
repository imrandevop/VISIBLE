#apps\verification\models.py
from django.db import models
from django.conf import settings
from apps.core.models import BaseModel
from apps.core.validators import validate_aadhaar_number, validate_license_number
from django.utils import timezone

class AadhaarVerification(BaseModel):
    """Aadhaar verification details"""
    VERIFICATION_STATUS = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ]
    
    user = models.OneToOneField(
        'profiles.UserProfile',
        on_delete=models.CASCADE,
        related_name='aadhaar_verification'
    )
    aadhaar_number = models.CharField(
        max_length=12, 
        validators=[validate_aadhaar_number],
        null=True,
        blank=True
    )
    status = models.CharField(
        max_length=10, 
        choices=VERIFICATION_STATUS, 
        default='pending'
    )
    otp_sent_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    can_skip = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.user.full_name} - Aadhaar {self.status}"
    
    def is_verified(self):
        return self.status == 'verified'
    
    def is_skipped(self):
        return self.status == 'skipped'
    
    def mark_verified(self):
        self.status = 'verified'
        self.verified_at = timezone.now()
        self.save()
    
    def mark_skipped(self):
        self.status = 'skipped'
        self.save()

class LicenseVerification(BaseModel):
    """License verification details"""
    VERIFICATION_STATUS = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('failed', 'Failed'),
    ]
    
    LICENSE_TYPES = [
        ('driving', 'Driving License'),
        ('commercial', 'Commercial License'),
        ('other', 'Other'),
    ]
    
    user = models.OneToOneField(
        'profiles.UserProfile',
        on_delete=models.CASCADE,
        related_name='license_verification'
    )
    license_number = models.CharField(
        max_length=50,
        validators=[validate_license_number],
        null=True,
        blank=True
    )
    license_type = models.CharField(
        max_length=20,
        choices=LICENSE_TYPES,
        default='driving'
    )
    status = models.CharField(
        max_length=10,
        choices=VERIFICATION_STATUS,
        default='pending'
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    is_required = models.BooleanField(default=False)  # True for drivers
    
    def __str__(self):
        return f"{self.user.full_name} - License {self.status}"
    
    def is_verified(self):
        return self.status == 'verified'
    
    def mark_verified(self):
        self.status = 'verified'
        self.verified_at = timezone.now()
        self.save()