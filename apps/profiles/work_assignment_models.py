# apps/profiles/work_assignment_models.py
from django.db import models
from django.conf import settings
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
    message = models.TextField(blank=True, help_text="Additional message from seeker")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Location info (optional)
    distance = models.CharField(max_length=50, blank=True, help_text="Distance between seeker and provider")
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