from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction

from apps.core.models import ProviderActiveStatus, SeekerSearchPreference, calculate_distance
from apps.work_categories.models import WorkCategory, WorkSubCategory, UserWorkSubCategory
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
        "provider_category_code": "MS0001",
        "provider_subcategory": "plumber",
        "provider_subcategory_code": "SS0001",
        "active": true
    }
    """
    try:
        longitude = request.data.get('longitude')
        latitude = request.data.get('latitude')
        provider_category = request.data.get('provider_category', '').strip()
        provider_category_code = request.data.get('provider_category_code', '').strip()
        provider_subcategory = request.data.get('provider_subcategory', '').strip()
        provider_subcategory_code = request.data.get('provider_subcategory_code', '').strip()
        active = request.data.get('active', False)

        # Validate required fields
        if not all([longitude, latitude, provider_category, provider_category_code, provider_subcategory, provider_subcategory_code]):
            return Response({
                "error": "longitude, latitude, provider_category, provider_category_code, provider_subcategory, and provider_subcategory_code are required"
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

        # Validate categories exist and match provided codes
        try:
            main_category = WorkCategory.objects.get(
                category_code=provider_category_code,
                is_active=True
            )

            # Validate that provided name matches the code
            if main_category.name != provider_category:
                return Response({
                    "error": f"Category name '{provider_category}' does not match code '{provider_category_code}'"
                }, status=status.HTTP_400_BAD_REQUEST)

            sub_category = WorkSubCategory.objects.get(
                subcategory_code=provider_subcategory_code,
                category=main_category,
                is_active=True
            )

            # Validate that provided subcategory name matches the code
            if sub_category.name != provider_subcategory:
                return Response({
                    "error": f"Subcategory name '{provider_subcategory}' does not match code '{provider_subcategory_code}'"
                }, status=status.HTTP_400_BAD_REQUEST)

        except WorkCategory.DoesNotExist:
            return Response({
                "error": f"Category with code '{provider_category_code}' not found or inactive"
            }, status=status.HTTP_400_BAD_REQUEST)
        except WorkSubCategory.DoesNotExist:
            return Response({
                "error": f"Subcategory with code '{provider_subcategory_code}' not found or inactive under category code '{provider_category_code}'"
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
            "category": {
                "code": main_category.category_code,
                "name": main_category.name
            },
            "subcategory": {
                "code": sub_category.subcategory_code,
                "name": sub_category.name
            },
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
        "searching_category_code": "MS0001",
        "searching_subcategory": "plumber",
        "searching_subcategory_code": "SS0001",
        "searching": true,
        "distance_radius": 5
    }
    """
    try:
        longitude = request.data.get('longitude')
        latitude = request.data.get('latitude')
        searching_category = request.data.get('searching_category', '').strip()
        searching_category_code = request.data.get('searching_category_code', '').strip()
        searching_subcategory = request.data.get('searching_subcategory', '').strip()
        searching_subcategory_code = request.data.get('searching_subcategory_code', '').strip()
        searching = request.data.get('searching', False)
        distance_radius = request.data.get('distance_radius', 5)

        # Validate required fields
        if not all([longitude, latitude, searching_category, searching_category_code, searching_subcategory, searching_subcategory_code]):
            return Response({
                "error": "longitude, latitude, searching_category, searching_category_code, searching_subcategory, and searching_subcategory_code are required"
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

        # Validate categories exist and match provided codes
        try:
            main_category = WorkCategory.objects.get(
                category_code=searching_category_code,
                is_active=True
            )

            # Validate that provided name matches the code
            if main_category.name != searching_category:
                return Response({
                    "error": f"Category name '{searching_category}' does not match code '{searching_category_code}'"
                }, status=status.HTTP_400_BAD_REQUEST)

            sub_category = WorkSubCategory.objects.get(
                subcategory_code=searching_subcategory_code,
                category=main_category,
                is_active=True
            )

            # Validate that provided subcategory name matches the code
            if sub_category.name != searching_subcategory:
                return Response({
                    "error": f"Subcategory name '{searching_subcategory}' does not match code '{searching_subcategory_code}'"
                }, status=status.HTTP_400_BAD_REQUEST)

        except WorkCategory.DoesNotExist:
            return Response({
                "error": f"Category with code '{searching_category_code}' not found or inactive"
            }, status=status.HTTP_400_BAD_REQUEST)
        except WorkSubCategory.DoesNotExist:
            return Response({
                "error": f"Subcategory with code '{searching_subcategory_code}' not found or inactive under category code '{searching_category_code}'"
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
                    'searching_subcategory': sub_category,
                    'distance_radius': distance_radius,
                }
            )

            if not created:
                search_preference.is_searching = searching
                search_preference.latitude = latitude
                search_preference.longitude = longitude
                search_preference.searching_category = main_category
                search_preference.searching_subcategory = sub_category
                search_preference.distance_radius = distance_radius
                search_preference.save()

        # Find nearby active providers if searching is enabled
        nearby_providers = []
        if searching:
            # Get providers who are active and have the searched subcategory in their skills
            # First get user IDs who have this subcategory skill
            user_ids_with_subcategory = UserWorkSubCategory.objects.filter(
                sub_category=sub_category,
                user_work_selection__main_category=main_category
            ).values_list('user_work_selection__user__user_id', flat=True)

            active_providers = ProviderActiveStatus.objects.filter(
                is_active=True,
                main_category=main_category,
                latitude__isnull=False,
                longitude__isnull=False,
                user_id__in=user_ids_with_subcategory
            ).select_related('user__profile')

            for provider in active_providers:
                distance = calculate_distance(
                    latitude, longitude,
                    provider.latitude, provider.longitude
                )

                if distance <= distance_radius:
                    nearby_providers.append({
                        'provider_id': provider.user.profile.provider_id,
                        'name': provider.user.profile.full_name,
                        'subcategory': {
                            'code': sub_category.subcategory_code,
                            'name': sub_category.display_name
                        },
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
            "category": {
                "code": main_category.category_code,
                "name": main_category.name
            },
            "subcategory": {
                "code": sub_category.subcategory_code,
                "name": sub_category.name
            },
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