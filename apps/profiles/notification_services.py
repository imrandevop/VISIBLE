# apps/profiles/notification_services.py
import firebase_admin
from firebase_admin import credentials, messaging
from django.utils import timezone
from django.conf import settings
import logging
import os

logger = logging.getLogger(__name__)

# Ensure Firebase is initialized
def _ensure_firebase_initialized():
    """Ensure Firebase Admin SDK is initialized"""
    if not firebase_admin._apps:
        try:
            # Try to load from environment variable first (for production)
            import json
            firebase_credentials_json = os.getenv('FIREBASE_CREDENTIALS_JSON')

            if firebase_credentials_json:
                # Parse JSON from environment variable
                cred_dict = json.loads(firebase_credentials_json)
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred)
                logger.info("✅ Firebase Admin SDK initialized from environment variable")
            else:
                # Fallback to file (for local development)
                firebase_credentials_path = os.path.join(settings.BASE_DIR, 'firebase_credentials.json')
                if os.path.exists(firebase_credentials_path):
                    cred = credentials.Certificate(firebase_credentials_path)
                    firebase_admin.initialize_app(cred)
                    logger.info("✅ Firebase Admin SDK initialized from file")
                else:
                    logger.error(f"❌ Firebase credentials not found. Set FIREBASE_CREDENTIALS_JSON env var or place firebase_credentials.json at {firebase_credentials_path}")
                    raise FileNotFoundError("Firebase credentials not found")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Firebase: {e}")
            raise

# Initialize Firebase when module is loaded
try:
    _ensure_firebase_initialized()
except Exception as e:
    logger.warning(f"⚠️ Firebase initialization failed on module load: {e}")

def send_work_assignment_notification(provider_profile, work_order):
    """
    Send FCM push notification to provider when work is assigned

    Args:
        provider_profile: UserProfile object of the provider
        work_order: WorkOrder object containing work details

    Returns:
        tuple: (success: bool, message_id: str or None, error: str or None)
    """
    # Ensure Firebase is initialized before sending
    _ensure_firebase_initialized()

    if not provider_profile.fcm_token:
        logger.warning(f"⚠️ No FCM token for provider: {provider_profile.user.mobile_number}")
        return False, None, "No FCM token available"

    try:
        # Prepare notification data
        seeker_profile = work_order.seeker_profile
        seeker_name = seeker_profile.full_name
        service_type = work_order.service_type
        distance = f"{work_order.calculated_distance:.2f}km" if work_order.calculated_distance else 'nearby'
        message_text = work_order.message or ''

        # Create FCM message (data-only for Android to ensure WorkAssignmentMessagingService handles it)
        message = messaging.Message(
            data={
                'type': 'work_assigned',
                'work_id': str(work_order.id),
                'seeker_name': seeker_name,
                'seeker_mobile': work_order.seeker.mobile_number,
                'service_type': service_type,
                'distance': distance,
                'message': message_text,
                'seeker_profile_pic': '',  # Add profile picture URL if available
                'created_at': work_order.created_at.isoformat(),
            },
            android=messaging.AndroidConfig(
                priority='high',
            ),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        alert=messaging.ApsAlert(
                            title='🚨 New Work Assignment',
                            body=f'{seeker_name} needs {service_type}',
                        ),
                        sound='alarm.mp3',
                        badge=1,
                    ),
                ),
            ),
            token=provider_profile.fcm_token,
        )

        # Send notification
        response = messaging.send(message)
        logger.info(f"✅ FCM notification sent successfully: {response}")

        # Log notification in database
        from .work_assignment_models import WorkAssignmentNotification
        WorkAssignmentNotification.objects.create(
            work_order=work_order,
            recipient=work_order.provider,
            notification_type='work_assigned',
            delivery_method='fcm',
            delivery_status='sent',
            fcm_message_id=response,
            sent_at=timezone.now()
        )

        return True, response, None

    except Exception as e:
        # Check if it's an invalid token error
        if "Invalid registration token" in str(e) or "InvalidArgument" in str(e):
            error_msg = f"Invalid FCM token: {e}"
            logger.error(f"❌ {error_msg}")

            # Mark FCM token as invalid
            provider_profile.fcm_token = None
            provider_profile.save(update_fields=['fcm_token'])

            return False, None, error_msg
        else:
            error_msg = f"Error sending FCM notification: {e}"
            logger.error(f"❌ {error_msg}")

            # Log failed notification
            from .work_assignment_models import WorkAssignmentNotification
            WorkAssignmentNotification.objects.create(
                work_order=work_order,
                recipient=work_order.provider,
                notification_type='work_assigned',
                delivery_method='fcm',
                delivery_status='failed',
                error_message=error_msg,
                sent_at=timezone.now()
            )

            return False, None, error_msg


def send_work_response_notification(seeker_profile, work_order, accepted):
    """
    Send FCM notification to seeker when provider responds to work assignment

    Args:
        seeker_profile: UserProfile object of the seeker
        work_order: WorkOrder object
        accepted: bool - whether provider accepted or rejected

    Returns:
        tuple: (success: bool, message_id: str or None, error: str or None)
    """
    # Ensure Firebase is initialized before sending
    _ensure_firebase_initialized()

    if not seeker_profile.fcm_token:
        logger.warning(f"⚠️ No FCM token for seeker: {seeker_profile.user.mobile_number}")
        return False, None, "No FCM token available"

    try:
        provider_profile = work_order.provider_profile
        provider_name = provider_profile.full_name
        service_type = work_order.service_type

        notification_type = 'work_accepted' if accepted else 'work_rejected'
        title = f"✅ Work {'Accepted' if accepted else 'Rejected'}"
        body = f"{provider_name} {'accepted' if accepted else 'rejected'} your {service_type} request"

        # Create FCM message
        message = messaging.Message(
            data={
                'type': notification_type,
                'work_id': str(work_order.id),
                'provider_name': provider_name,
                'provider_mobile': work_order.provider.mobile_number,
                'service_type': service_type,
                'accepted': str(accepted).lower(),
                'response_time': timezone.now().isoformat(),
            },
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    title=title,
                    body=body,
                    channel_id='work_response_channel',
                    priority='high',
                ),
            ),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        alert=messaging.ApsAlert(title=title, body=body),
                        sound='default',
                        badge=1,
                    ),
                ),
            ),
            token=seeker_profile.fcm_token,
        )

        # Send notification
        response = messaging.send(message)
        logger.info(f"✅ Work response FCM notification sent: {response}")

        # Log notification in database
        from .work_assignment_models import WorkAssignmentNotification
        WorkAssignmentNotification.objects.create(
            work_order=work_order,
            recipient=work_order.seeker,
            notification_type=notification_type,
            delivery_method='fcm',
            delivery_status='sent',
            fcm_message_id=response,
            sent_at=timezone.now()
        )

        return True, response, None

    except Exception as e:
        error_msg = f"Error sending work response FCM notification: {e}"
        logger.error(f"❌ {error_msg}")
        return False, None, error_msg


def send_chat_message_notification(recipient_profile, sender_profile, session, message_text, message_id):
    """
    Send FCM notification for chat messages between seeker and provider

    Args:
        recipient_profile: UserProfile object of the message recipient
        sender_profile: UserProfile object of the message sender
        session: WorkSession object
        message_text: str - The chat message content
        message_id: UUID - The message ID

    Returns:
        tuple: (success: bool, message_id: str or None, error: str or None)
    """
    # Ensure Firebase is initialized before sending
    _ensure_firebase_initialized()

    if not recipient_profile.fcm_token:
        logger.warning(f"⚠️ No FCM token for user: {recipient_profile.user.mobile_number}")
        return False, None, "No FCM token available"

    try:
        sender_name = sender_profile.full_name
        sender_type = sender_profile.user_type  # 'seeker' or 'provider'

        # Create FCM message (data-only for Android, client handles display)
        message = messaging.Message(
            data={
                'type': 'chat_message',
                'session_id': str(session.session_id),
                'message_id': str(message_id),
                'sender_name': sender_name,
                'sender_type': sender_type,
                'message': message_text,
                'timestamp': timezone.now().isoformat(),
            },
            android=messaging.AndroidConfig(
                priority='high',
            ),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        alert=messaging.ApsAlert(
                            title=sender_name,
                            body=message_text,
                        ),
                        sound='default',
                        badge=1,
                    ),
                ),
            ),
            token=recipient_profile.fcm_token,
        )

        # Send notification
        response = messaging.send(message)
        logger.info(f"✅ Chat message FCM notification sent: {response}")

        # Log notification in database
        from .work_assignment_models import WorkAssignmentNotification, WorkOrder
        # Get the work_order associated with this session
        work_order = session.work_order

        WorkAssignmentNotification.objects.create(
            work_order=work_order,
            recipient=recipient_profile.user,
            notification_type='chat_message',
            delivery_method='fcm',
            delivery_status='sent',
            fcm_message_id=response,
            sent_at=timezone.now()
        )

        return True, response, None

    except Exception as e:
        # Check if it's an invalid token error
        if "Invalid registration token" in str(e) or "InvalidArgument" in str(e):
            error_msg = f"Invalid FCM token: {e}"
            logger.error(f"❌ {error_msg}")

            # Mark FCM token as invalid
            recipient_profile.fcm_token = None
            recipient_profile.save(update_fields=['fcm_token'])

            return False, None, error_msg
        else:
            error_msg = f"Error sending chat message FCM notification: {e}"
            logger.error(f"❌ {error_msg}")

            # Log failed notification
            from .work_assignment_models import WorkAssignmentNotification, WorkOrder
            work_order = session.work_order

            WorkAssignmentNotification.objects.create(
                work_order=work_order,
                recipient=recipient_profile.user,
                notification_type='chat_message',
                delivery_method='fcm',
                delivery_status='failed',
                error_message=error_msg,
                sent_at=timezone.now()
            )

            return False, None, error_msg


def validate_fcm_token(fcm_token):
    """
    Validate FCM token by sending a test message

    Args:
        fcm_token: str - FCM token to validate

    Returns:
        bool: True if token is valid, False otherwise
    """
    # Ensure Firebase is initialized before validating
    _ensure_firebase_initialized()

    if not fcm_token:
        return False

    try:
        # Create a test message (dry run)
        message = messaging.Message(
            data={'test': 'true'},
            token=fcm_token,
        )

        # Send in dry run mode to validate token
        messaging.send(message, dry_run=True)
        return True

    except Exception as e:
        if "Invalid registration token" in str(e) or "InvalidArgument" in str(e):
            logger.warning(f"Invalid FCM token detected: {fcm_token[:20]}...")
            return False
        else:
            logger.error(f"Error validating FCM token: {e}")
            return False