# apps/profiles/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from apps.profiles.models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
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
    
    readonly_fields = [
        'created_at', 
        'updated_at',
        'profile_photo_preview',
        'mobile_number',
        'work_details_link'
    ]
    
    fieldsets = (
        ('Basic Information', {
            'fields': (
                'user',
                'mobile_number', 
                'full_name', 
                'date_of_birth', 
                'gender',
                'user_type'
            )
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
    
    def mobile_number(self, obj):
        return obj.user.mobile_number
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