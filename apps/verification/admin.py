# apps/verification/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from apps.verification.models import AadhaarVerification, LicenseVerification


@admin.register(AadhaarVerification)
class AadhaarVerificationAdmin(admin.ModelAdmin):
    list_display = [
        'user_name',
        'mobile_number',
        'masked_aadhaar',
        'status',
        'can_skip',
        'verified_at',
        'created_at'
    ]
    
    list_filter = [
        'status',
        'can_skip',
        'verified_at',
        'created_at'
    ]
    
    search_fields = [
        'user__full_name',
        'user__user__mobile_number',
        'aadhaar_number'
    ]
    
    fieldsets = (
        ('User Information', {
            'fields': (
                'user',
                'user_profile_link'
            )
        }),
        ('Aadhaar Details', {
            'fields': (
                'aadhaar_number',
                'status',
                'can_skip'
            )
        }),
        ('Verification Status', {
            'fields': (
                'otp_sent_at',
                'verified_at'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    readonly_fields = [
        'created_at', 
        'updated_at',
        'user_profile_link'
    ]
    
    actions = ['mark_verified', 'mark_failed', 'mark_skipped']
    
    def user_name(self, obj):
        return obj.user.full_name
    user_name.short_description = 'User Name'
    user_name.admin_order_field = 'user__full_name'
    
    def mobile_number(self, obj):
        return obj.user.user.mobile_number
    mobile_number.short_description = 'Mobile'
    mobile_number.admin_order_field = 'user__user__mobile_number'
    
    def masked_aadhaar(self, obj):
        if obj.aadhaar_number:
            return f"****-****-{obj.aadhaar_number[-4:]}"
        return "Not provided"
    masked_aadhaar.short_description = 'Aadhaar Number'
    
    def user_profile_link(self, obj):
        url = reverse('admin:profiles_userprofile_change', args=[obj.user.id])
        return format_html('<a href="{}" target="_blank">View Profile</a>', url)
    user_profile_link.short_description = 'User Profile'
    
    def mark_verified(self, request, queryset):
        from django.utils import timezone
        queryset.update(status='verified', verified_at=timezone.now())
        self.message_user(request, f"Marked {queryset.count()} Aadhaar verifications as verified.")
    mark_verified.short_description = "Mark as verified"
    
    def mark_failed(self, request, queryset):
        queryset.update(status='failed', verified_at=None)
        self.message_user(request, f"Marked {queryset.count()} Aadhaar verifications as failed.")
    mark_failed.short_description = "Mark as failed"
    
    def mark_skipped(self, request, queryset):
        queryset.update(status='skipped')
        self.message_user(request, f"Marked {queryset.count()} Aadhaar verifications as skipped.")
    mark_skipped.short_description = "Mark as skipped"


@admin.register(LicenseVerification)
class LicenseVerificationAdmin(admin.ModelAdmin):
    list_display = [
        'user_name',
        'mobile_number',
        'license_number',
        'license_type',
        'status',
        'is_required',
        'verified_at',
        'created_at'
    ]
    
    list_filter = [
        'license_type',
        'status',
        'is_required',
        'verified_at',
        'created_at'
    ]
    
    search_fields = [
        'user__full_name',
        'user__user__mobile_number',
        'license_number'
    ]
    
    fieldsets = (
        ('User Information', {
            'fields': (
                'user',
                'user_profile_link'
            )
        }),
        ('License Details', {
            'fields': (
                'license_number',
                'license_type',
                'status',
                'is_required'
            )
        }),
        ('Verification Status', {
            'fields': ('verified_at',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    readonly_fields = [
        'created_at', 
        'updated_at',
        'user_profile_link'
    ]
    
    actions = ['mark_verified', 'mark_failed', 'mark_required', 'mark_optional']
    
    def user_name(self, obj):
        return obj.user.full_name
    user_name.short_description = 'User Name'
    user_name.admin_order_field = 'user__full_name'
    
    def mobile_number(self, obj):
        return obj.user.user.mobile_number
    mobile_number.short_description = 'Mobile'
    mobile_number.admin_order_field = 'user__user__mobile_number'
    
    def user_profile_link(self, obj):
        url = reverse('admin:profiles_userprofile_change', args=[obj.user.id])
        return format_html('<a href="{}" target="_blank">View Profile</a>', url)
    user_profile_link.short_description = 'User Profile'
    
    def mark_verified(self, request, queryset):
        from django.utils import timezone
        queryset.update(status='verified', verified_at=timezone.now())
        self.message_user(request, f"Marked {queryset.count()} license verifications as verified.")
    mark_verified.short_description = "Mark as verified"
    
    def mark_failed(self, request, queryset):
        queryset.update(status='failed', verified_at=None)
        self.message_user(request, f"Marked {queryset.count()} license verifications as failed.")
    mark_failed.short_description = "Mark as failed"
    
    def mark_required(self, request, queryset):
        queryset.update(is_required=True)
        self.message_user(request, f"Marked {queryset.count()} license verifications as required.")
    mark_required.short_description = "Mark as required"
    
    def mark_optional(self, request, queryset):
        queryset.update(is_required=False)
        self.message_user(request, f"Marked {queryset.count()} license verifications as optional.")
    mark_optional.short_description = "Mark as optional"