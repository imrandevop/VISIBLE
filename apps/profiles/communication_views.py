# apps/profiles/communication_views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from apps.profiles.models import UserProfile
from apps.profiles.communication_models import CommunicationSettings
import logging

logger = logging.getLogger(__name__)

@api_view(['POST', 'GET'])
@permission_classes([IsAuthenticated])
def communication_settings_api(request, version=None):
    """
    API endpoint to set/update and get user's communication preferences

    POST /api/1/profiles/communication/settings/
    Body: {
        "user_id": "8138945646",  // Optional - will use authenticated user if not provided
        "communication_settings": {
            "telegram": {
                "enabled": true,
                "value": "815558"
            },
            "whatsapp": {
                "enabled": true,
                "value": "888"
            },
            "call": {
                "enabled": true,
                "value": ""
            },
            "map_location": {
                "enabled": false,
                "value": ""
            },
            "website": {
                "enabled": true,
                "value": ""
            },
            "instagram": {
                "enabled": false,
                "value": ""
            },
            "facebook": {
                "enabled": true,
                "value": ""
            },
            "land_mark": "Near Central Park, 5th Avenue",  // Optional, max 255 chars
            "upi_ID": "user@paytm"  // Optional, max 100 chars
        }
    }

    GET /api/1/profiles/communication/settings/

    Response: {
        "status": "success",
        "message": "Communication settings updated successfully" / "Communication settings retrieved successfully",
        "data": {
            "user_id": "123",
            "provider_id": "AB12345678",
            "full_name": "John Doe",
            "user_type": "provider",
            "communication_settings": {...}
        }
    }
    """
    try:
        # Get the authenticated user
        user = request.user

        # Get user profile
        try:
            user_profile = UserProfile.objects.get(user=user)
        except UserProfile.DoesNotExist:
            return Response({
                "status": "error",
                "message": "User profile not found. Please complete your profile first."
            }, status=status.HTTP_404_NOT_FOUND)

        if request.method == 'GET':
            return handle_get_communication_settings(user_profile)
        elif request.method == 'POST':
            return handle_set_communication_settings(request, user_profile)

    except Exception as e:
        logger.error(f"Error in communication settings API for user {request.user.id}: {str(e)}")
        return Response({
            "status": "error",
            "message": "An unexpected server error occurred. Please try again."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def handle_get_communication_settings(user_profile):
    """Handle GET request for communication settings"""
    try:
        # Get communication settings
        try:
            communication_settings = CommunicationSettings.objects.get(user_profile=user_profile)

            response_communication_settings = {
                "telegram": {
                    "enabled": communication_settings.telegram_enabled,
                    "value": communication_settings.telegram_value or ""
                },
                "whatsapp": {
                    "enabled": communication_settings.whatsapp_enabled,
                    "value": communication_settings.whatsapp_value or ""
                },
                "call": {
                    "enabled": communication_settings.call_enabled,
                    "value": communication_settings.call_value or ""
                },
                "map_location": {
                    "enabled": communication_settings.map_location_enabled,
                    "value": communication_settings.map_location_value or ""
                },
                "website": {
                    "enabled": communication_settings.website_enabled,
                    "value": communication_settings.website_value or ""
                },
                "instagram": {
                    "enabled": communication_settings.instagram_enabled,
                    "value": communication_settings.instagram_value or ""
                },
                "facebook": {
                    "enabled": communication_settings.facebook_enabled,
                    "value": communication_settings.facebook_value or ""
                },
                "land_mark": communication_settings.land_mark or "",
                "upi_ID": communication_settings.upi_ID or ""
            }

        except CommunicationSettings.DoesNotExist:
            # Return default empty settings if none exist
            response_communication_settings = {
                "telegram": {"enabled": False, "value": ""},
                "whatsapp": {"enabled": False, "value": ""},
                "call": {"enabled": False, "value": ""},
                "map_location": {"enabled": False, "value": ""},
                "website": {"enabled": False, "value": ""},
                "instagram": {"enabled": False, "value": ""},
                "facebook": {"enabled": False, "value": ""},
                "land_mark": "",
                "upi_ID": ""
            }

        return Response({
            "status": "success",
            "message": "Communication settings retrieved successfully",
            "data": {
                "user_id": str(user_profile.user.id),
                "provider_id": user_profile.provider_id,
                "full_name": user_profile.full_name,
                "user_type": user_profile.user_type,
                "communication_settings": response_communication_settings
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error getting communication settings for user {user_profile.user.id}: {str(e)}")
        return Response({
            "status": "error",
            "message": "An unexpected error occurred while retrieving communication settings."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def handle_set_communication_settings(request, user_profile):
    """Handle POST request for communication settings"""
    try:
        # Extract communication settings from request
        communication_data = request.data.get('communication_settings', {})

        if not communication_data:
            return Response({
                "status": "error",
                "message": "communication_settings is required"
            }, status=status.HTTP_400_BAD_REQUEST)

        # Update or create communication settings
        with transaction.atomic():
            communication_settings, created = CommunicationSettings.objects.get_or_create(
                user_profile=user_profile,
                defaults={
                    # Telegram
                    'telegram_enabled': communication_data.get('telegram', {}).get('enabled', False),
                    'telegram_value': communication_data.get('telegram', {}).get('value', ''),

                    # WhatsApp
                    'whatsapp_enabled': communication_data.get('whatsapp', {}).get('enabled', False),
                    'whatsapp_value': communication_data.get('whatsapp', {}).get('value', ''),

                    # Call
                    'call_enabled': communication_data.get('call', {}).get('enabled', False),
                    'call_value': communication_data.get('call', {}).get('value', ''),

                    # Map location
                    'map_location_enabled': communication_data.get('map_location', {}).get('enabled', False),
                    'map_location_value': communication_data.get('map_location', {}).get('value', ''),

                    # Website
                    'website_enabled': communication_data.get('website', {}).get('enabled', False),
                    'website_value': communication_data.get('website', {}).get('value', ''),

                    # Instagram
                    'instagram_enabled': communication_data.get('instagram', {}).get('enabled', False),
                    'instagram_value': communication_data.get('instagram', {}).get('value', ''),

                    # Facebook
                    'facebook_enabled': communication_data.get('facebook', {}).get('enabled', False),
                    'facebook_value': communication_data.get('facebook', {}).get('value', ''),

                    # Land mark and UPI ID
                    'land_mark': communication_data.get('land_mark', ''),
                    'upi_ID': communication_data.get('upi_ID', ''),
                }
            )

            if not created:
                # Update existing settings
                # Telegram
                telegram_data = communication_data.get('telegram', {})
                communication_settings.telegram_enabled = telegram_data.get('enabled', False)
                communication_settings.telegram_value = telegram_data.get('value', '')

                # WhatsApp
                whatsapp_data = communication_data.get('whatsapp', {})
                communication_settings.whatsapp_enabled = whatsapp_data.get('enabled', False)
                communication_settings.whatsapp_value = whatsapp_data.get('value', '')

                # Call
                call_data = communication_data.get('call', {})
                communication_settings.call_enabled = call_data.get('enabled', False)
                communication_settings.call_value = call_data.get('value', '')

                # Map location
                map_data = communication_data.get('map_location', {})
                communication_settings.map_location_enabled = map_data.get('enabled', False)
                communication_settings.map_location_value = map_data.get('value', '')

                # Website
                website_data = communication_data.get('website', {})
                communication_settings.website_enabled = website_data.get('enabled', False)
                communication_settings.website_value = website_data.get('value', '')

                # Instagram
                instagram_data = communication_data.get('instagram', {})
                communication_settings.instagram_enabled = instagram_data.get('enabled', False)
                communication_settings.instagram_value = instagram_data.get('value', '')

                # Facebook
                facebook_data = communication_data.get('facebook', {})
                communication_settings.facebook_enabled = facebook_data.get('enabled', False)
                communication_settings.facebook_value = facebook_data.get('value', '')

                # Land mark and UPI ID
                communication_settings.land_mark = communication_data.get('land_mark', '')
                communication_settings.upi_ID = communication_data.get('upi_ID', '')

                communication_settings.save()

        # Prepare response data
        response_communication_settings = {
            "telegram": {
                "enabled": communication_settings.telegram_enabled,
                "value": communication_settings.telegram_value or ""
            },
            "whatsapp": {
                "enabled": communication_settings.whatsapp_enabled,
                "value": communication_settings.whatsapp_value or ""
            },
            "call": {
                "enabled": communication_settings.call_enabled,
                "value": communication_settings.call_value or ""
            },
            "map_location": {
                "enabled": communication_settings.map_location_enabled,
                "value": communication_settings.map_location_value or ""
            },
            "website": {
                "enabled": communication_settings.website_enabled,
                "value": communication_settings.website_value or ""
            },
            "instagram": {
                "enabled": communication_settings.instagram_enabled,
                "value": communication_settings.instagram_value or ""
            },
            "facebook": {
                "enabled": communication_settings.facebook_enabled,
                "value": communication_settings.facebook_value or ""
            },
            "land_mark": communication_settings.land_mark or "",
            "upi_ID": communication_settings.upi_ID or ""
        }

        return Response({
            "status": "success",
            "message": "Communication settings updated successfully",
            "data": {
                "user_id": str(user_profile.user.id),
                "provider_id": user_profile.provider_id,
                "full_name": user_profile.full_name,
                "user_type": user_profile.user_type,
                "communication_settings": response_communication_settings
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Error updating communication settings for user {user_profile.user.id}: {str(e)}")
        return Response({
            "status": "error",
            "message": "An unexpected error occurred while updating communication settings."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)