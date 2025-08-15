#apps\core\models.py
from django.db import models
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError

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