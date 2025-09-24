# apps/profiles/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django import forms
from apps.profiles.models import UserProfile, ServicePortfolioImage
from apps.authentication.models import User


class UserProfileForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Get users who don't already have profiles
        existing_profile_user_ids = UserProfile.objects.values_list('user_id', flat=True)
        if self.instance.pk:
            # If editing existing profile, include the current user
            existing_profile_user_ids = existing_profile_user_ids.exclude(id=self.instance.user_id)
        
        # Set up the user field properly
        self.fields['user'].queryset = User.objects.filter(
            is_staff=False, 
            is_mobile_verified=True
        ).exclude(id__in=existing_profile_user_ids)
    
    class Meta:
        model = UserProfile
        fields = '__all__'


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    form = UserProfileForm
    list_display = [
        'full_name', 
        'mobile_number', 
        'user_type', 
        'profile_complete', 
        'can_access_app',
        'profile_photo_preview',
        'created_at'
    ]
    
    list_filter = [
        'user_type', 
        'profile_complete', 
        'can_access_app', 
        'gender',
        'created_at'
    ]
    
    search_fields = [
        'full_name', 
        'user__mobile_number',
        'user__username'
    ]
    
    def get_readonly_fields(self, request, obj=None):
        readonly_fields = [
            'created_at', 
            'updated_at',
            'profile_photo_preview',
            'work_details_link'
        ]
        # Only show mobile_number as readonly when editing existing object
        if obj:
            readonly_fields.append('mobile_number')
        return readonly_fields
    
    def get_fieldsets(self, request, obj=None):
        basic_fields = ['user', 'full_name', 'date_of_birth', 'gender', 'user_type']
        if obj:  # Only show mobile_number when editing existing object
            basic_fields.insert(1, 'mobile_number')
            
        return (
            ('Basic Information', {
                'fields': basic_fields
            }),
            ('Profile Photo', {
                'fields': (
                    'profile_photo',
                    'profile_photo_preview'
                )
            }),
            ('Status', {
                'fields': (
                    'profile_complete', 
                    'can_access_app'
                )
            }),
            ('Work Information', {
                'fields': ('work_details_link',),
                'classes': ('collapse',)
            }),
            ('Timestamps', {
                'fields': ('created_at', 'updated_at'),
                'classes': ('collapse',)
            })
        )
    
    actions = ['mark_profile_complete', 'mark_profile_incomplete', 'refresh_completion_status']
    
    def save_model(self, request, obj, form, change):
        # Ensure the user field is properly set
        if hasattr(form, 'cleaned_data') and 'user' in form.cleaned_data:
            user = form.cleaned_data['user']
            if user and hasattr(user, 'id'):
                obj.user = user
        super().save_model(request, obj, form, change)
    
    def mobile_number(self, obj):
        if obj and obj.user:
            return obj.user.mobile_number
        return "Not assigned"
    mobile_number.short_description = 'Mobile Number'
    mobile_number.admin_order_field = 'user__mobile_number'
    
    def profile_photo_preview(self, obj):
        if obj.profile_photo:
            return format_html(
                '<img src="{}" style="width: 50px; height: 50px; border-radius: 50%; object-fit: cover;" />',
                obj.profile_photo.url
            )
        return "No Photo"
    profile_photo_preview.short_description = 'Photo Preview'
    
    def work_details_link(self, obj):
        if obj.user_type == 'worker':
            try:
                work_selection = obj.work_selection
                url = reverse('admin:work_categories_userworkselection_change', args=[work_selection.id])
                return format_html('<a href="{}" target="_blank">View Work Details</a>', url)
            except:
                return "No work details found"
        return "Not a worker"
    work_details_link.short_description = 'Work Details'
    
    def mark_profile_complete(self, request, queryset):
        for profile in queryset:
            profile.profile_complete = True
            profile.can_access_app = True
            profile.save()
        self.message_user(request, f"Marked {queryset.count()} profiles as complete.")
    mark_profile_complete.short_description = "Mark selected profiles as complete"
    
    def mark_profile_incomplete(self, request, queryset):
        for profile in queryset:
            profile.profile_complete = False
            profile.can_access_app = False
            profile.save()
        self.message_user(request, f"Marked {queryset.count()} profiles as incomplete.")
    mark_profile_incomplete.short_description = "Mark selected profiles as incomplete"
    
    def refresh_completion_status(self, request, queryset):
        updated_count = 0
        for profile in queryset:
            old_status = profile.profile_complete
            profile.check_profile_completion()
            if old_status != profile.profile_complete:
                updated_count += 1
        self.message_user(request, f"Refreshed completion status. {updated_count} profiles updated.")
    refresh_completion_status.short_description = "Refresh profile completion status"


@admin.register(ServicePortfolioImage)
class ServicePortfolioImageAdmin(admin.ModelAdmin):
    list_display = [
        'user_profile_name',
        'mobile_number',
        'image_order',
        'image_preview',
        'created_at'
    ]

    list_filter = [
        'image_order',
        'created_at',
        'user_profile__user_type'
    ]

    search_fields = [
        'user_profile__full_name',
        'user_profile__user__mobile_number'
    ]

    readonly_fields = ['image_preview', 'created_at', 'updated_at']

    def user_profile_name(self, obj):
        return obj.user_profile.full_name
    user_profile_name.short_description = 'User Name'
    user_profile_name.admin_order_field = 'user_profile__full_name'

    def mobile_number(self, obj):
        return obj.user_profile.user.mobile_number
    mobile_number.short_description = 'Mobile'
    mobile_number.admin_order_field = 'user_profile__user__mobile_number'

    def image_preview(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="width: 100px; height: 100px; object-fit: cover;" />',
                obj.image.url
            )
        return "No Image"
    image_preview.short_description = 'Image Preview'