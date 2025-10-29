# apps/profiles/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django import forms
from apps.profiles.models import UserProfile, ServicePortfolioImage, Offer, Wallet, WalletTransaction
from apps.profiles.work_assignment_models import (
    WorkOrder,
    WorkAssignmentNotification,
    WorkSession,
    ChatMessage,
    TypingIndicator
)
from apps.authentication.models import User
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


