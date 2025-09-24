#apps\work_categories\models.py
from django.db import models
from django.conf import settings
from apps.core.models import BaseModel, ActiveManager, work_portfolio_path, validate_image_size
from django.core.validators import FileExtensionValidator

class WorkCategory(BaseModel):
    """Main work categories like worker, driver, business"""
    category_code = models.CharField(max_length=10, unique=True, editable=False, null=True, blank=True)
    name = models.CharField(max_length=50, unique=True)
    display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    icon_url = models.URLField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    
    objects = models.Manager()
    active = ActiveManager()
    
    class Meta:
        ordering = ['sort_order', 'display_name']
        verbose_name_plural = "Work Categories"
    
    def save(self, *args, **kwargs):
        if not self.category_code:
            # Generate category code in format MS0001
            last_category = WorkCategory.objects.order_by('id').last()
            if last_category:
                last_number = int(last_category.category_code[2:])  # Extract number from MS0001
                new_number = last_number + 1
            else:
                new_number = 1
            self.category_code = f"MS{new_number:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.display_name

class WorkSubCategory(BaseModel):
    """Sub-categories under main work categories"""
    subcategory_code = models.CharField(max_length=10, unique=True, editable=False, null=True, blank=True)
    category = models.ForeignKey(
        WorkCategory,
        on_delete=models.CASCADE,
        related_name='subcategories'
    )
    name = models.CharField(max_length=50)
    display_name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    
    objects = models.Manager()
    active = ActiveManager()
    
    class Meta:
        ordering = ['sort_order', 'display_name']
        unique_together = ['category', 'name']
        verbose_name_plural = "Work Sub Categories"
    
    def save(self, *args, **kwargs):
        if not self.subcategory_code:
            # Generate subcategory code in format SS0001
            last_subcategory = WorkSubCategory.objects.order_by('id').last()
            if last_subcategory:
                last_number = int(last_subcategory.subcategory_code[2:])  # Extract number from SS0001
                new_number = last_number + 1
            else:
                new_number = 1
            self.subcategory_code = f"SS{new_number:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.category.display_name} - {self.display_name}"

class UserWorkSelection(BaseModel):
    """User's selected work category with experience and skills"""
    user = models.OneToOneField(
        'profiles.UserProfile',
        on_delete=models.CASCADE,
        related_name='work_selection'
    )
    main_category = models.ForeignKey(
        WorkCategory,
        on_delete=models.CASCADE,
        related_name='user_selections'
    )
    years_experience = models.IntegerField()
    skills = models.TextField()
    
    def __str__(self):
        return f"{self.user.full_name} - {self.main_category.display_name}"

class UserWorkSubCategory(BaseModel):
    """Many-to-many relationship between user work selection and subcategories"""
    user_work_selection = models.ForeignKey(
        UserWorkSelection,
        on_delete=models.CASCADE,
        related_name='selected_subcategories'
    )
    sub_category = models.ForeignKey(
        WorkSubCategory,
        on_delete=models.CASCADE,
        related_name='user_selections'
    )
    
    class Meta:
        unique_together = ['user_work_selection', 'sub_category']
    
    def __str__(self):
        return f"{self.user_work_selection.user.full_name} - {self.sub_category.display_name}"

class WorkPortfolioImage(BaseModel):
    """Portfolio images for user's work (max 3 per user)"""
    user_work_selection = models.ForeignKey(
        UserWorkSelection,
        on_delete=models.CASCADE,
        related_name='portfolio_images'
    )
    image = models.ImageField(
        upload_to=work_portfolio_path,
        validators=[
            FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png']),
            validate_image_size
        ]
    )
    image_order = models.IntegerField()  # 1, 2, or 3
    
    class Meta:
        unique_together = ['user_work_selection', 'image_order']
        ordering = ['image_order']
    
    def __str__(self):
        return f"{self.user_work_selection.user.full_name} - Image {self.image_order}"

class ServiceRequest(BaseModel):
    """User requests for services not available in categories"""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='service_requests'
    )
    service_name = models.TextField()

    class Meta:
        unique_together = ['user', 'service_name']
        ordering = ['-created_at']
        verbose_name_plural = "Service Requests"

    def __str__(self):
        return f"{self.user.mobile_number} - {self.service_name[:50]}"