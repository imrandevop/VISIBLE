# apps/profiles/work_assignment_models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import uuid
from apps.core.models import BaseModel
from .models import UserProfile

class WorkOrder(BaseModel):
    """Work assignment orders between seekers and providers"""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    # Relationships
    seeker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='seeker_orders'
    )
    provider = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='provider_orders'
    )

    # Work details
    service_type = models.CharField(max_length=100, help_text="Type of service requested")
    main_category_code = models.CharField(max_length=20, blank=True, default='', help_text="Main category code (e.g., MS0001)")
    sub_category_code = models.CharField(max_length=20, blank=True, default='', help_text="Sub category code (e.g., SS0001)")
    message = models.TextField(blank=True, help_text="Additional message from seeker")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Schedule info
    schedule_data = models.JSONField(null=True, blank=True, help_text="Schedule information from frontend")

    # Location info
    calculated_distance = models.FloatField(null=True, blank=True, help_text="Calculated distance in kilometers")
    seeker_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    seeker_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    provider_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    provider_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Timestamps
    response_time = models.DateTimeField(null=True, blank=True, help_text="When provider responded")
    completion_time = models.DateTimeField(null=True, blank=True, help_text="When work was completed")

    # Notification tracking
    fcm_sent = models.BooleanField(default=False, help_text="FCM notification was sent")
    websocket_sent = models.BooleanField(default=False, help_text="WebSocket message was sent")

    def __str__(self):
        return f"Order #{self.id}: {self.seeker.mobile_number} → {self.provider.mobile_number}"

    @property
    def seeker_profile(self):
        """Get seeker's profile"""
        return self.seeker.profile

    @property
    def provider_profile(self):
        """Get provider's profile"""
        return self.provider.profile

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['seeker', 'status']),
            models.Index(fields=['provider', 'status']),
            models.Index(fields=['status', 'created_at']),
        ]


class WorkAssignmentNotification(BaseModel):
    """Track notification delivery status"""

    NOTIFICATION_TYPE_CHOICES = [
        ('work_assigned', 'Work Assigned'),
        ('work_accepted', 'Work Accepted'),
        ('work_rejected', 'Work Rejected'),
        ('work_completed', 'Work Completed'),
        ('work_cancelled', 'Work Cancelled'),
    ]

    DELIVERY_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed'),
    ]

    work_order = models.ForeignKey(
        WorkOrder,
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='work_notifications'
    )

    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPE_CHOICES)
    delivery_method = models.CharField(max_length=20, choices=[('fcm', 'FCM'), ('websocket', 'WebSocket')])
    delivery_status = models.CharField(max_length=20, choices=DELIVERY_STATUS_CHOICES, default='pending')

    # FCM/WebSocket specific data
    fcm_message_id = models.CharField(max_length=255, blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)

    # Delivery timestamps
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.notification_type} to {self.recipient.mobile_number} - {self.delivery_status}"

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['work_order', 'notification_type']),
            models.Index(fields=['recipient', 'delivery_status']),
        ]


class WorkSession(BaseModel):
    """Real-time work session connecting seeker and provider after work acceptance"""

    CONNECTION_STATE_CHOICES = [
        ('waiting', 'Waiting for medium selection'),
        ('active', 'Active connection'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]

    # Link to work order
    work_order = models.OneToOneField(
        WorkOrder,
        on_delete=models.CASCADE,
        related_name='session'
    )

    # Session identifier (also used as chat_room_id)
    session_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    # Connection state
    connection_state = models.CharField(max_length=20, choices=CONNECTION_STATE_CHOICES, default='waiting')

    # Real-time locations (updated via WebSocket)
    seeker_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    seeker_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    seeker_last_location_update = models.DateTimeField(null=True, blank=True)

    provider_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    provider_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    provider_last_location_update = models.DateTimeField(null=True, blank=True)

    # Current distance between users (in meters)
    current_distance_meters = models.FloatField(null=True, blank=True)
    last_distance_update = models.DateTimeField(null=True, blank=True)

    # Communication mediums (selected by seeker, then provider can add theirs)
    seeker_selected_mediums = models.JSONField(
        default=dict,
        blank=True,
        help_text="{'telegram': '9876543210', 'whatsapp': '9876543210', 'call': '9876543210'}"
    )
    provider_selected_mediums = models.JSONField(
        default=dict,
        blank=True,
        help_text="{'telegram': '9876543210', 'whatsapp': '9876543210', 'call': '9876543210'}"
    )
    mediums_shared_at = models.DateTimeField(null=True, blank=True)

    # Chat room (same as session_id, but stored for easy reference)
    chat_room_id = models.UUIDField(null=True, blank=True, editable=False)
    chat_started_at = models.DateTimeField(null=True, blank=True)

    # Cancellation info
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cancelled_sessions'
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Completion
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Session {self.session_id} - {self.connection_state}"

    @property
    def chat_room_id_str(self):
        """Return chat room ID as string"""
        return str(self.session_id)

    def get_formatted_distance(self):
        """Format distance as 'X.X km' or 'XXX meters'"""
        if self.current_distance_meters is None:
            return "Distance unavailable"

        if self.current_distance_meters < 1000:
            return f"{int(self.current_distance_meters)} meters away"
        else:
            km = self.current_distance_meters / 1000
            return f"{km:.1f} km away"

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['session_id']),
            models.Index(fields=['work_order']),
            models.Index(fields=['connection_state']),
        ]


class ChatMessage(BaseModel):
    """Anonymous chat messages between seeker and provider (expire after 24 hours)"""

    DELIVERY_STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
    ]

    # Link to session
    session = models.ForeignKey(
        WorkSession,
        on_delete=models.CASCADE,
        related_name='chat_messages'
    )

    # Message details
    message_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_messages'
    )
    sender_type = models.CharField(
        max_length=10,
        choices=[('seeker', 'Seeker'), ('provider', 'Provider')],
        help_text="Anonymous sender type"
    )
    message_text = models.TextField()

    # Delivery tracking
    delivery_status = models.CharField(max_length=20, choices=DELIVERY_STATUS_CHOICES, default='sent')
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    # Expiry (24 hours after session ends)
    expires_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.sender_type} message in session {self.session.session_id}"

    def save(self, *args, **kwargs):
        """Set expiry time based on session state"""
        if not self.expires_at:
            # Messages expire 24 hours after session completion/cancellation
            if self.session.connection_state in ['cancelled', 'completed']:
                expiry_time = self.session.cancelled_at or self.session.completed_at
                if expiry_time:
                    self.expires_at = expiry_time + timedelta(hours=24)
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['session', 'created_at']),
            models.Index(fields=['message_id']),
            models.Index(fields=['expires_at']),
        ]


class TypingIndicator(BaseModel):
    """Track real-time typing status in chat"""

    session = models.ForeignKey(
        WorkSession,
        on_delete=models.CASCADE,
        related_name='typing_indicators'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='typing_status'
    )
    user_type = models.CharField(
        max_length=10,
        choices=[('seeker', 'Seeker'), ('provider', 'Provider')]
    )
    is_typing = models.BooleanField(default=False)
    last_typing_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        status = "typing" if self.is_typing else "not typing"
        return f"{self.user_type} {status} in session {self.session.session_id}"

    class Meta:
        unique_together = ['session', 'user']
        indexes = [
            models.Index(fields=['session', 'user']),
        ]