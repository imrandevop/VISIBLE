from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
import random
import string

class User(AbstractUser):
    mobile_number = models.CharField(max_length=15, unique=True)
    is_mobile_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Add these to fix the conflict
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        related_name='custom_user_set',
        related_query_name='custom_user',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        related_name='custom_user_set',
        related_query_name='custom_user',
    )
    
    def __str__(self):
        return f"{self.mobile_number}"

# Keep your OTP model as is (you might use it later)
class OTP(models.Model):
    mobile_number = models.CharField(max_length=15)
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-created_at']
    
    def is_valid(self):
        """Check if OTP is still valid (10 minutes)"""
        from django.conf import settings
        validity_minutes = getattr(settings, 'OTP_VALIDITY_MINUTES', 10)
        valid_until = self.created_at + timezone.timedelta(minutes=validity_minutes)
        return timezone.now() <= valid_until and not self.is_verified
    
    @classmethod
    def generate_otp(cls):
        """Generate 6-digit OTP"""
        return ''.join(random.choices(string.digits, k=6))
    
    def __str__(self):
        return f"{self.mobile_number} - {self.otp_code}"