# apps/authentication/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.urls import reverse
from apps.authentication.models import User, OTP


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = [
        'mobile_number',
        'username', 
        'first_name',
        'last_name',
        'is_mobile_verified',
        'profile_status',
        'is_active',
        'date_joined'
    ]
    
    list_filter = [
        'is_mobile_verified',
        'is_active',
        'is_staff',
        'is_superuser',
        'date_joined'
    ]
    
    search_fields = [
        'mobile_number',
        'username',
        'first_name',
        'last_name',
        'email'
    ]
    
    ordering = ['-date_joined']
    
    fieldsets = (
        (None, {
            'fields': ('username', 'password')
        }),
        ('Personal info', {
            'fields': (
                'first_name', 
                'last_name', 
                'email',
                'mobile_number',
                'is_mobile_verified'
            )
        }),
        ('Permissions', {
            'fields': (
                'is_active',
                'is_staff',
                'is_superuser',
                'groups',
                'user_permissions'
            ),
            'classes': ('collapse',)
        }),
        ('Important dates', {
            'fields': ('last_login', 'date_joined'),
            'classes': ('collapse',)
        }),
        ('Profile Link', {
            'fields': ('profile_link',),
            'classes': ('collapse',)
        })
    )
    
    readonly_fields = ['date_joined', 'last_login', 'profile_link']
    
    actions = ['verify_mobile', 'unverify_mobile']
    
    def profile_status(self, obj):
        try:
            profile = obj.profile
            if profile.profile_complete:
                return format_html(
                    '<span style="color: green;">✓ Complete</span>'
                )
            else:
                return format_html(
                    '<span style="color: orange;">⚠ Incomplete</span>'
                )
        except:
            return format_html(
                '<span style="color: red;">✗ No Profile</span>'
            )
    profile_status.short_description = 'Profile Status'
    
    def profile_link(self, obj):
        try:
            profile = obj.profile
            url = reverse('admin:profiles_userprofile_change', args=[profile.id])
            return format_html('<a href="{}" target="_blank">View Profile</a>', url)
        except:
            return "No profile created"
    profile_link.short_description = 'Profile Link'
    
    def verify_mobile(self, request, queryset):
        queryset.update(is_mobile_verified=True)
        self.message_user(request, f"Verified mobile for {queryset.count()} users.")
    verify_mobile.short_description = "Mark mobile as verified"
    
    def unverify_mobile(self, request, queryset):
        queryset.update(is_mobile_verified=False)
        self.message_user(request, f"Unverified mobile for {queryset.count()} users.")
    unverify_mobile.short_description = "Mark mobile as unverified"


@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = [
        'mobile_number',
        'otp_code',
        'is_verified',
        'is_valid_now',
        'created_at'
    ]
    
    list_filter = [
        'is_verified',
        'created_at'
    ]
    
    search_fields = [
        'mobile_number',
        'otp_code'
    ]
    
    ordering = ['-created_at']
    
    readonly_fields = [
        'created_at',
        'is_valid_now',
        'time_remaining'
    ]
    
    fieldsets = (
        ('OTP Details', {
            'fields': (
                'mobile_number',
                'otp_code',
                'is_verified'
            )
        }),
        ('Status', {
            'fields': (
                'is_valid_now',
                'time_remaining',
                'created_at'
            )
        })
    )
    
    actions = ['mark_verified', 'mark_unverified']
    
    def is_valid_now(self, obj):
        if obj.is_valid():
            return format_html('<span style="color: green;">✓ Valid</span>')
        else:
            return format_html('<span style="color: red;">✗ Expired</span>')
    is_valid_now.short_description = 'Current Status'
    
    def time_remaining(self, obj):
        if obj.is_valid():
            from django.utils import timezone
            from django.conf import settings
            validity_minutes = getattr(settings, 'OTP_VALIDITY_MINUTES', 10)
            valid_until = obj.created_at + timezone.timedelta(minutes=validity_minutes)
            remaining = valid_until - timezone.now()
            minutes = int(remaining.total_seconds() / 60)
            return f"{minutes} minutes"
        return "Expired"
    time_remaining.short_description = 'Time Remaining'
    
    def mark_verified(self, request, queryset):
        queryset.update(is_verified=True)
        self.message_user(request, f"Marked {queryset.count()} OTPs as verified.")
    mark_verified.short_description = "Mark as verified"
    
    def mark_unverified(self, request, queryset):
        queryset.update(is_verified=False)
        self.message_user(request, f"Marked {queryset.count()} OTPs as unverified.")
    mark_unverified.short_description = "Mark as unverified"