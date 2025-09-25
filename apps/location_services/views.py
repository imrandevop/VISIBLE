from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction

from apps.core.models import ProviderActiveStatus, SeekerSearchPreference, calculate_distance
from apps.work_categories.models import WorkCategory, WorkSubCategory
from apps.profiles.models import UserProfile


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def provider_toggle_status(request, version=None):
    """
    Provider status toggle API

    POST /api/1/location/provider/toggle-status/

    Body:
    {
        "longitude": 75.8577,
        "latitude": 11.2588,
        "provider_category": "worker",
        "provider_subcategory": "plumber",
        "active": true
    }
    """
    try:
        longitude = request.data.get('longitude')
        latitude = request.data.get('latitude')
        provider_category = request.data.get('provider_category', '').strip()
        provider_subcategory = request.data.get('provider_subcategory', '').strip()
        active = request.data.get('active', False)

        # Validate required fields
        if not all([longitude, latitude, provider_category, provider_subcategory]):
            return Response({
                "error": "longitude, latitude, provider_category, and provider_subcategory are required"
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate user is a provider
        try:
            user_profile = UserProfile.objects.get(user=request.user)
            if user_profile.user_type != 'provider':
                return Response({
                    "error": "Only providers can use this endpoint"
                }, status=status.HTTP_403_FORBIDDEN)
        except UserProfile.DoesNotExist:
            return Response({
                "error": "User profile not found"
            }, status=status.HTTP_404_NOT_FOUND)

        # Validate categories exist
        try:
            main_category = WorkCategory.objects.get(name=provider_category, is_active=True)
            sub_category = WorkSubCategory.objects.get(
                name=provider_subcategory,
                category=main_category,
                is_active=True
            )
        except WorkCategory.DoesNotExist:
            return Response({
                "error": f"Category '{provider_category}' not found or inactive"
            }, status=status.HTTP_400_BAD_REQUEST)
        except WorkSubCategory.DoesNotExist:
            return Response({
                "error": f"Subcategory '{provider_subcategory}' not found or inactive"
            }, status=status.HTTP_400_BAD_REQUEST)

        # Update or create provider status
        with transaction.atomic():
            provider_status, created = ProviderActiveStatus.objects.get_or_create(
                user=request.user,
                defaults={
                    'is_active': active,
                    'latitude': latitude,
                    'longitude': longitude,
                    'main_category': main_category,
                    'sub_category': sub_category,
                }
            )

            if not created:
                provider_status.is_active = active
                provider_status.latitude = latitude
                provider_status.longitude = longitude
                provider_status.main_category = main_category
                provider_status.sub_category = sub_category
                provider_status.save()

        return Response({
            "status": "success",
            "active": provider_status.is_active,
            "category": main_category.name,
            "subcategory": sub_category.name,
            "current_location": {
                "latitude": provider_status.latitude,
                "longitude": provider_status.longitude
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            "error": "An unexpected server error occurred. Please try again."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def seeker_search_toggle(request, version=None):
    """
    Seeker search toggle API

    POST /api/1/location/seeker/search-toggle/

    Body:
    {
        "longitude": 75.8577,
        "latitude": 11.2588,
        "searching_category": "worker",
        "searching": true,
        "distance_radius": 5
    }
    """
    try:
        longitude = request.data.get('longitude')
        latitude = request.data.get('latitude')
        searching_category = request.data.get('searching_category', '').strip()
        searching = request.data.get('searching', False)
        distance_radius = request.data.get('distance_radius', 5)

        # Validate required fields
        if not all([longitude, latitude, searching_category]):
            return Response({
                "error": "longitude, latitude, and searching_category are required"
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate user is a seeker
        try:
            user_profile = UserProfile.objects.get(user=request.user)
            if user_profile.user_type != 'seeker':
                return Response({
                    "error": "Only seekers can use this endpoint"
                }, status=status.HTTP_403_FORBIDDEN)
        except UserProfile.DoesNotExist:
            return Response({
                "error": "User profile not found"
            }, status=status.HTTP_404_NOT_FOUND)

        # Validate category exists
        try:
            main_category = WorkCategory.objects.get(name=searching_category, is_active=True)
        except WorkCategory.DoesNotExist:
            return Response({
                "error": f"Category '{searching_category}' not found or inactive"
            }, status=status.HTTP_400_BAD_REQUEST)

        # Update or create seeker search preference
        with transaction.atomic():
            search_preference, created = SeekerSearchPreference.objects.get_or_create(
                user=request.user,
                defaults={
                    'is_searching': searching,
                    'latitude': latitude,
                    'longitude': longitude,
                    'searching_category': main_category,
                    'distance_radius': distance_radius,
                }
            )

            if not created:
                search_preference.is_searching = searching
                search_preference.latitude = latitude
                search_preference.longitude = longitude
                search_preference.searching_category = main_category
                search_preference.distance_radius = distance_radius
                search_preference.save()

        # Find nearby active providers if searching is enabled
        nearby_providers = []
        if searching:
            active_providers = ProviderActiveStatus.objects.filter(
                is_active=True,
                main_category=main_category,
                latitude__isnull=False,
                longitude__isnull=False
            ).select_related('user__profile', 'sub_category')

            for provider in active_providers:
                distance = calculate_distance(
                    latitude, longitude,
                    provider.latitude, provider.longitude
                )

                if distance <= distance_radius:
                    nearby_providers.append({
                        'provider_id': provider.user.profile.provider_id,
                        'name': provider.user.profile.full_name,
                        'subcategory': provider.sub_category.display_name,
                        'distance_km': round(distance, 2),
                        'location': {
                            'latitude': provider.latitude,
                            'longitude': provider.longitude
                        }
                    })

            # Sort by distance
            nearby_providers.sort(key=lambda x: x['distance_km'])

        return Response({
            "status": "success",
            "searching": search_preference.is_searching,
            "category": main_category.name,
            "distance_radius": search_preference.distance_radius,
            "current_location": {
                "latitude": search_preference.latitude,
                "longitude": search_preference.longitude
            },
            "nearby_providers": nearby_providers
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            "error": "An unexpected server error occurred. Please try again."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)