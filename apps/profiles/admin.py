# apps/profiles/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django import forms
from apps.profiles.models import UserProfile, ServicePortfolioImage, Offer
from apps.profiles.work_assignment_models import (
    WorkOrder,
    WorkAssignmentNotification,
    WorkSession,
    ChatMessage,
    TypingIndicator
)
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


@admin.register(WorkOrder)
class WorkOrderAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'seeker_name',
        'provider_name',
        'service_type',
        'status',
        'calculated_distance',
        'created_at'
    ]

    list_filter = [
        'status',
        'service_type',
        'created_at'
    ]

    search_fields = [
        'seeker__mobile_number',
        'provider__mobile_number',
        'seeker__profile__full_name',
        'provider__profile__full_name'
    ]

    readonly_fields = [
        'created_at',
        'updated_at',
        'response_time',
        'completion_time'
    ]

    fieldsets = (
        ('Users', {
            'fields': ('seeker', 'provider')
        }),
        ('Work Details', {
            'fields': (
                'service_type',
                'main_category_code',
                'sub_category_code',
                'message',
                'status'
            )
        }),
        ('Schedule', {
            'fields': ('schedule_data',)
        }),
        ('Location', {
            'fields': (
                'calculated_distance',
                'seeker_latitude',
                'seeker_longitude',
                'provider_latitude',
                'provider_longitude'
            )
        }),
        ('Notifications', {
            'fields': ('fcm_sent', 'websocket_sent')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'response_time', 'completion_time')
        })
    )

    def seeker_name(self, obj):
        return obj.seeker_profile.full_name if obj.seeker_profile else 'N/A'
    seeker_name.short_description = 'Seeker'
    seeker_name.admin_order_field = 'seeker__profile__full_name'

    def provider_name(self, obj):
        return obj.provider_profile.full_name if obj.provider_profile else 'N/A'
    provider_name.short_description = 'Provider'
    provider_name.admin_order_field = 'provider__profile__full_name'


@admin.register(WorkAssignmentNotification)
class WorkAssignmentNotificationAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'notification_type',
        'recipient_name',
        'delivery_method',
        'delivery_status',
        'created_at'
    ]

    list_filter = [
        'notification_type',
        'delivery_method',
        'delivery_status',
        'created_at'
    ]

    search_fields = [
        'recipient__mobile_number',
        'work_order__id'
    ]

    readonly_fields = [
        'created_at',
        'updated_at',
        'sent_at',
        'delivered_at'
    ]

    def recipient_name(self, obj):
        return obj.recipient.profile.full_name if hasattr(obj.recipient, 'profile') else 'N/A'
    recipient_name.short_description = 'Recipient'


@admin.register(WorkSession)
class WorkSessionAdmin(admin.ModelAdmin):
    list_display = [
        'session_id_short',
        'work_order_id',
        'connection_state',
        'distance_display',
        'mediums_shared',
        'chat_active',
        'created_at'
    ]

    list_filter = [
        'connection_state',
        'created_at',
        'chat_started_at',
        'cancelled_at'
    ]

    search_fields = [
        'session_id',
        'work_order__id',
        'work_order__seeker__mobile_number',
        'work_order__provider__mobile_number'
    ]

    readonly_fields = [
        'session_id',
        'chat_room_id',
        'created_at',
        'updated_at',
        'provider_last_location_update',
        'seeker_last_location_update',
        'last_distance_update',
        'mediums_shared_at',
        'chat_started_at',
        'cancelled_at',
        'completed_at',
        'distance_formatted'
    ]

    fieldsets = (
        ('Session Info', {
            'fields': ('session_id', 'work_order', 'connection_state')
        }),
        ('Provider Location', {
            'fields': (
                'provider_latitude',
                'provider_longitude',
                'provider_last_location_update'
            )
        }),
        ('Seeker Location', {
            'fields': (
                'seeker_latitude',
                'seeker_longitude',
                'seeker_last_location_update'
            )
        }),
        ('Distance Tracking', {
            'fields': (
                'current_distance_meters',
                'distance_formatted',
                'last_distance_update'
            )
        }),
        ('Communication Mediums', {
            'fields': (
                'seeker_selected_mediums',
                'provider_selected_mediums',
                'mediums_shared_at'
            )
        }),
        ('Chat', {
            'fields': (
                'chat_room_id',
                'chat_started_at'
            )
        }),
        ('Status', {
            'fields': (
                'cancelled_by',
                'cancelled_at',
                'completed_at'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        })
    )

    def session_id_short(self, obj):
        return str(obj.session_id)[:8] + '...'
    session_id_short.short_description = 'Session ID'

    def work_order_id(self, obj):
        return f"#{obj.work_order.id}"
    work_order_id.short_description = 'Work Order'
    work_order_id.admin_order_field = 'work_order__id'

    def distance_display(self, obj):
        return obj.get_formatted_distance()
    distance_display.short_description = 'Distance'

    def mediums_shared(self, obj):
        seeker_count = len(obj.seeker_selected_mediums) if obj.seeker_selected_mediums else 0
        provider_count = len(obj.provider_selected_mediums) if obj.provider_selected_mediums else 0
        return f"S:{seeker_count} / P:{provider_count}"
    mediums_shared.short_description = 'Mediums (S/P)'

    def chat_active(self, obj):
        return bool(obj.chat_started_at)
    chat_active.short_description = 'Chat Active'
    chat_active.boolean = True

    def distance_formatted(self, obj):
        return obj.get_formatted_distance()
    distance_formatted.short_description = 'Distance (Formatted)'


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = [
        'message_id_short',
        'session_id_short',
        'sender_type',
        'message_preview',
        'delivery_status',
        'created_at',
        'expires_at'
    ]

    list_filter = [
        'sender_type',
        'delivery_status',
        'created_at',
        'expires_at'
    ]

    search_fields = [
        'message_id',
        'session__session_id',
        'message_text',
        'sender__mobile_number'
    ]

    readonly_fields = [
        'message_id',
        'created_at',
        'updated_at',
        'delivered_at',
        'read_at',
        'expires_at'
    ]

    fieldsets = (
        ('Message Info', {
            'fields': ('message_id', 'session', 'sender', 'sender_type')
        }),
        ('Content', {
            'fields': ('message_text',)
        }),
        ('Delivery Tracking', {
            'fields': (
                'delivery_status',
                'delivered_at',
                'read_at'
            )
        }),
        ('Expiry', {
            'fields': ('expires_at',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        })
    )

    def message_id_short(self, obj):
        return str(obj.message_id)[:8] + '...'
    message_id_short.short_description = 'Message ID'

    def session_id_short(self, obj):
        return str(obj.session.session_id)[:8] + '...'
    session_id_short.short_description = 'Session'

    def message_preview(self, obj):
        return obj.message_text[:50] + '...' if len(obj.message_text) > 50 else obj.message_text
    message_preview.short_description = 'Message'


@admin.register(TypingIndicator)
class TypingIndicatorAdmin(admin.ModelAdmin):
    list_display = [
        'session_id_short',
        'user_type',
        'user_mobile',
        'is_typing',
        'last_typing_at'
    ]

    list_filter = [
        'user_type',
        'is_typing',
        'last_typing_at'
    ]

    search_fields = [
        'session__session_id',
        'user__mobile_number'
    ]

    readonly_fields = [
        'created_at',
        'updated_at',
        'last_typing_at'
    ]

    def session_id_short(self, obj):
        return str(obj.session.session_id)[:8] + '...'
    session_id_short.short_description = 'Session'

    def user_mobile(self, obj):
        return obj.user.mobile_number if obj.user else 'N/A'
    user_mobile.short_description = 'Mobile'


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = [
        'offer_id',
        'title',
        'priority',
        'is_active',
        'maintenance_mode',
        'valid_until',
        'created_at'
    ]

    list_filter = [
        'is_active',
        'maintenance_mode',
        'priority',
        'created_at',
        'valid_until'
    ]

    search_fields = [
        'offer_id',
        'title',
        'description'
    ]

    readonly_fields = [
        'offer_id',
        'created_at',
        'updated_at'
    ]

    fieldsets = (
        ('Offer Information', {
            'fields': ('offer_id', 'title', 'description', 'image_url')
        }),
        ('Settings', {
            'fields': ('priority', 'is_active', 'valid_until')
        }),
        ('System Settings', {
            'fields': ('maintenance_mode',),
            'description': 'Global app maintenance mode setting (affects all users)'
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    ordering = ['priority', '-created_at']