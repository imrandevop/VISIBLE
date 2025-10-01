# apps/profiles/work_assignment_views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import logging

from .models import UserProfile
from .work_assignment_models import WorkOrder, WorkAssignmentNotification
from .notification_services import send_work_assignment_notification, validate_fcm_token

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_fcm_token(request, version=None):
    """
    Update the user's FCM token for push notifications

    POST /api/1/profiles/fcm-token/
    Body: {"fcm_token": "string"}
    """
    try:
        fcm_token = request.data.get('fcm_token')

        if not fcm_token:
            return Response({
                'status': 'error',
                'message': 'FCM token is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate FCM token format (basic validation)
        if len(fcm_token) < 10:
            return Response({
                'status': 'error',
                'message': 'Invalid FCM token format'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get user profile
        try:
            user_profile = UserProfile.objects.get(user=request.user)
        except UserProfile.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'User profile not found'
            }, status=status.HTTP_404_NOT_FOUND)

        # Update FCM token
        user_profile.fcm_token = fcm_token
        user_profile.save(update_fields=['fcm_token'])

        logger.info(f"✅ FCM token updated for user: {request.user.mobile_number}")

        return Response({
            'status': 'success',
            'message': 'FCM token updated successfully',
            'data': {
                'user_id': str(request.user.id),
                'user_type': user_profile.user_type,
                'fcm_token_set': True
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error updating FCM token for user {request.user.id}: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'An unexpected error occurred'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def assign_work(request, version=None):
    """
    Assign work to a provider

    POST /api/1/profiles/assign-work/
    Body: {
        "provider_id": 123,
        "service_type": "painter",
        "message": "Need to paint living room",
        "distance": "5km",
        "latitude": 12.345,
        "longitude": 67.890
    }
    """
    try:
        seeker = request.user
        seeker_profile = seeker.profile

        # Validate seeker
        if seeker_profile.user_type != 'seeker':
            return Response({
                'status': 'error',
                'message': 'Only seekers can assign work'
            }, status=status.HTTP_403_FORBIDDEN)

        # Extract request data
        provider_id = request.data.get('provider_id')
        service_type = request.data.get('service_type')
        message = request.data.get('message', '')
        distance = request.data.get('distance', '')
        latitude = request.data.get('latitude')
        longitude = request.data.get('longitude')

        # Validation
        if not provider_id or not service_type:
            return Response({
                'status': 'error',
                'message': 'provider_id and service_type are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get provider
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            provider = User.objects.get(id=provider_id)
            provider_profile = provider.profile

            # Validate provider
            if provider_profile.user_type != 'provider':
                return Response({
                    'status': 'error',
                    'message': 'Selected user is not a provider'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Check if provider provides this service type
            if provider_profile.service_type != service_type:
                return Response({
                    'status': 'error',
                    'message': f'Provider does not offer {service_type} services'
                }, status=status.HTTP_400_BAD_REQUEST)

        except User.DoesNotExist:
            return Response({
                'status': 'error',
                'message': 'Provider not found'
            }, status=status.HTTP_404_NOT_FOUND)

        # Check for existing pending work orders
        existing_order = WorkOrder.objects.filter(
            seeker=seeker,
            provider=provider,
            status='pending'
        ).first()

        if existing_order:
            return Response({
                'status': 'error',
                'message': 'You already have a pending work order with this provider'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Create work order
        with transaction.atomic():
            work_order = WorkOrder.objects.create(
                seeker=seeker,
                provider=provider,
                service_type=service_type,
                message=message,
                distance=distance,
                seeker_latitude=latitude,
                seeker_longitude=longitude,
                status='pending'
            )

            logger.info(f"📋 Work order #{work_order.id} created: {seeker.mobile_number} → {provider.mobile_number}")

            # 1. Send FCM push notification (PRIMARY)
            fcm_success, fcm_message_id, fcm_error = send_work_assignment_notification(provider_profile, work_order)
            work_order.fcm_sent = fcm_success
            work_order.save(update_fields=['fcm_sent'])

            # 2. Send WebSocket message (BACKUP/INSTANT)
            websocket_success = send_websocket_notification(provider, work_order, seeker_profile)
            work_order.websocket_sent = websocket_success
            work_order.save(update_fields=['websocket_sent'])

            logger.info(f"✅ Work assignment sent to provider {provider.mobile_number} (FCM: {fcm_success}, WS: {websocket_success})")

            return Response({
                'status': 'success',
                'message': 'Work assigned successfully',
                'data': {
                    'work_order_id': work_order.id,
                    'provider_name': provider_profile.full_name,
                    'provider_mobile': provider.mobile_number,
                    'provider_rating': 4.88,  # Mock rating data
                    'service_type': service_type,
                    'fcm_sent': fcm_success,
                    'websocket_sent': websocket_success,
                    'created_at': work_order.created_at.isoformat()
                }
            }, status=status.HTTP_201_CREATED)

    except Exception as e:
        logger.error(f"Error assigning work for user {request.user.id}: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'An unexpected error occurred while assigning work'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def send_websocket_notification(provider, work_order, seeker_profile):
    """Send WebSocket notification to provider with complete seeker profile data"""
    try:
        from django.conf import settings

        # Build complete seeker profile data
        seeker_data = build_complete_seeker_data(seeker_profile)

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'provider_{provider.id}',
            {
                'type': 'work_assignment',
                'work_id': work_order.id,
                'service_type': work_order.service_type,
                'distance': work_order.distance,
                'message': work_order.message,
                'seeker_latitude': float(work_order.seeker_latitude) if work_order.seeker_latitude else None,
                'seeker_longitude': float(work_order.seeker_longitude) if work_order.seeker_longitude else None,
                'created_at': work_order.created_at.isoformat(),
                'seeker': seeker_data
            }
        )
        return True
    except Exception as e:
        logger.error(f"Error sending WebSocket notification: {e}")
        return False


def build_complete_seeker_data(seeker_profile):
    """Build complete seeker profile data"""
    try:
        from django.conf import settings

        # Determine base URL for images
        if hasattr(settings, 'ALLOWED_HOSTS') and settings.ALLOWED_HOSTS:
            production_hosts = [host for host in settings.ALLOWED_HOSTS if host not in ['localhost', '127.0.0.1']]
            base_domain = production_hosts[0] if production_hosts else 'localhost:8000'
        else:
            base_domain = 'localhost:8000'

        base_url = f"https://{base_domain}" if base_domain != 'localhost:8000' else f"http://{base_domain}"

        # Get profile photo URL
        profile_photo = None
        if seeker_profile.profile_photo:
            profile_photo = f"{base_url}{seeker_profile.profile_photo.url}"

        # Get languages as array
        languages = []
        if seeker_profile.languages:
            languages = [lang.strip() for lang in seeker_profile.languages.split(',') if lang.strip()]

        return {
            'user_id': seeker_profile.user.id,
            'name': seeker_profile.full_name,
            'mobile_number': seeker_profile.user.mobile_number if seeker_profile.user else '',
            'age': seeker_profile.age,
            'gender': seeker_profile.gender,
            'date_of_birth': seeker_profile.date_of_birth.isoformat() if seeker_profile.date_of_birth else None,
            'profile_photo': profile_photo,
            'languages': languages,
            'user_type': seeker_profile.user_type,
            'profile_complete': seeker_profile.profile_complete,
            'can_access_app': seeker_profile.can_access_app,
            'created_at': seeker_profile.created_at.isoformat() if seeker_profile.created_at else None
        }
    except Exception as e:
        logger.error(f"Error building seeker data: {str(e)}")
        return {
            'user_id': seeker_profile.user.id if seeker_profile.user else None,
            'name': getattr(seeker_profile, 'full_name', 'Unknown'),
            'mobile_number': seeker_profile.user.mobile_number if seeker_profile.user else '',
            'profile_photo': None,
            'languages': [],
            'user_type': getattr(seeker_profile, 'user_type', 'seeker')
        }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_work_orders(request, version=None):
    """
    Get work orders for the authenticated user

    GET /api/1/profiles/work-orders/
    Query params:
    - status: pending, accepted, rejected, completed, cancelled
    - limit: number of results (default: 20)
    - offset: pagination offset (default: 0)
    """
    try:
        user = request.user
        user_profile = user.profile

        # Query parameters
        status_filter = request.GET.get('status')
        limit = int(request.GET.get('limit', 20))
        offset = int(request.GET.get('offset', 0))

        # Build queryset based on user type
        if user_profile.user_type == 'seeker':
            queryset = WorkOrder.objects.filter(seeker=user)
        elif user_profile.user_type == 'provider':
            queryset = WorkOrder.objects.filter(provider=user)
        else:
            return Response({
                'status': 'error',
                'message': 'Invalid user type'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Apply status filter
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Get total count
        total_count = queryset.count()

        # Apply pagination
        work_orders = queryset.select_related(
            'seeker__profile',
            'provider__profile'
        )[offset:offset + limit]

        # Serialize work orders
        work_orders_data = []
        for order in work_orders:
            work_orders_data.append({
                'id': order.id,
                'seeker': {
                    'id': order.seeker.id,
                    'name': order.seeker_profile.full_name,
                    'mobile': order.seeker.mobile_number,
                },
                'provider': {
                    'id': order.provider.id,
                    'name': order.provider_profile.full_name,
                    'mobile': order.provider.mobile_number,
                    'provider_id': order.provider_profile.provider_id,
                },
                'service_type': order.service_type,
                'message': order.message,
                'distance': order.distance,
                'status': order.status,
                'created_at': order.created_at.isoformat(),
                'response_time': order.response_time.isoformat() if order.response_time else None,
                'completion_time': order.completion_time.isoformat() if order.completion_time else None,
            })

        return Response({
            'status': 'success',
            'data': {
                'work_orders': work_orders_data,
                'pagination': {
                    'total_count': total_count,
                    'limit': limit,
                    'offset': offset,
                    'has_next': offset + limit < total_count
                }
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error getting work orders for user {request.user.id}: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'An unexpected error occurred'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def update_provider_status(request, version=None):
    """
    Update provider's active status for work assignments

    PATCH /api/1/profiles/provider-status/
    Body: {
        "is_active_for_work": true,
        "service_type": "worker"  # optional
    }
    """
    try:
        user = request.user
        user_profile = user.profile

        # Validate user is a provider
        if user_profile.user_type != 'provider':
            return Response({
                'status': 'error',
                'message': 'Only providers can update work status'
            }, status=status.HTTP_403_FORBIDDEN)

        # Extract request data
        is_active = request.data.get('is_active_for_work')
        service_type = request.data.get('service_type')

        if is_active is None:
            return Response({
                'status': 'error',
                'message': 'is_active_for_work is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Update profile
        user_profile.is_active_for_work = bool(is_active)
        if service_type:
            user_profile.service_type = service_type

        user_profile.save(update_fields=['is_active_for_work', 'service_type'])

        logger.info(f"✅ Provider {user.mobile_number} status updated: active={is_active}")

        return Response({
            'status': 'success',
            'message': 'Provider status updated successfully',
            'data': {
                'user_id': str(user.id),
                'provider_id': user_profile.provider_id,
                'is_active_for_work': user_profile.is_active_for_work,
                'service_type': user_profile.service_type
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error updating provider status for user {request.user.id}: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'An unexpected error occurred'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_active_providers(request, version=None):
    """
    Get list of active providers by service type

    GET /api/1/profiles/active-providers/
    Query params:
    - service_type: worker, driver, properties, SOS
    - limit: number of results (default: 20)
    - offset: pagination offset (default: 0)
    """
    try:
        # Query parameters
        service_type = request.GET.get('service_type')
        limit = int(request.GET.get('limit', 20))
        offset = int(request.GET.get('offset', 0))

        if not service_type:
            return Response({
                'status': 'error',
                'message': 'service_type is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get active providers
        queryset = UserProfile.objects.filter(
            user_type='provider',
            service_type=service_type,
            is_active_for_work=True,
            profile_complete=True,
            can_access_app=True
        ).select_related('user')

        total_count = queryset.count()
        providers = queryset[offset:offset + limit]

        # Serialize providers
        providers_data = []
        for profile in providers:
            providers_data.append({
                'id': profile.user.id,
                'provider_id': profile.provider_id,
                'name': profile.full_name,
                'mobile': profile.user.mobile_number,
                'service_type': profile.service_type,
                'languages': profile.languages,
                'is_active_for_work': profile.is_active_for_work,
                'profile_photo': profile.profile_photo.url if profile.profile_photo else None,
                'created_at': profile.created_at.isoformat(),
            })

        return Response({
            'status': 'success',
            'data': {
                'providers': providers_data,
                'pagination': {
                    'total_count': total_count,
                    'limit': limit,
                    'offset': offset,
                    'has_next': offset + limit < total_count
                }
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error getting active providers: {str(e)}")
        return Response({
            'status': 'error',
            'message': 'An unexpected error occurred'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)