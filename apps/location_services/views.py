import logging
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction

from apps.core.models import ProviderActiveStatus, SeekerSearchPreference, calculate_distance
from apps.work_categories.models import WorkCategory, WorkSubCategory, UserWorkSubCategory, UserWorkSelection, WorkPortfolioImage
from apps.profiles.models import UserProfile

logger = logging.getLogger(__name__)


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
        "provider_category_code": "MS0001",
        "provider_subcategory_code": "SS0001",
        "active": true
    }
    """
    try:
        # Get and validate numeric fields
        longitude = request.data.get('longitude')
        latitude = request.data.get('latitude')

        # Validate longitude
        try:
            longitude = float(longitude) if longitude is not None else None
        except (ValueError, TypeError):
            return Response({
                "error": "Invalid longitude value"
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate latitude
        try:
            latitude = float(latitude) if latitude is not None else None
        except (ValueError, TypeError):
            return Response({
                "error": "Invalid latitude value"
            }, status=status.HTTP_400_BAD_REQUEST)

        provider_category_code = request.data.get('provider_category_code', '').strip()
        provider_subcategory_code = request.data.get('provider_subcategory_code', '').strip()
        active = request.data.get('active', False)

        # Validate required fields
        if not all([longitude, latitude, provider_category_code, provider_subcategory_code]):
            return Response({
                "error": "longitude, latitude, provider_category_code, and provider_subcategory_code are required"
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

            sub_category = WorkSubCategory.objects.get(
                subcategory_code=provider_subcategory_code,
                category=main_category,
                is_active=True
            )

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
        "searching_category_code": "MS0001",
        "searching_subcategory_code": "SS0001",
        "searching": true,
        "distance_radius": 5
    }

    Response includes nearby providers with:
    - provider_id, name, rating (default 0)
    - description (from UserProfile.bio)
    - is_verified (default false)
    - images (portfolio images array)
    - distance and location data
    """
    try:
        # Get and validate numeric fields
        longitude = request.data.get('longitude')
        latitude = request.data.get('latitude')
        distance_radius = request.data.get('distance_radius', 5)

        # Validate longitude
        try:
            longitude = float(longitude) if longitude is not None else None
        except (ValueError, TypeError):
            return Response({
                "error": "Invalid longitude value"
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate latitude
        try:
            latitude = float(latitude) if latitude is not None else None
        except (ValueError, TypeError):
            return Response({
                "error": "Invalid latitude value"
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate distance_radius
        try:
            distance_radius = int(distance_radius)
            if distance_radius <= 0 or distance_radius > 50:  # Reasonable limits
                return Response({
                    "error": "Distance radius must be between 1 and 50 km"
                }, status=status.HTTP_400_BAD_REQUEST)
        except (ValueError, TypeError):
            return Response({
                "error": "Invalid distance radius value"
            }, status=status.HTTP_400_BAD_REQUEST)

        searching_category_code = request.data.get('searching_category_code', '').strip()
        searching_subcategory_code = request.data.get('searching_subcategory_code', '').strip()
        searching = request.data.get('searching', False)

        # Validate required fields
        if not all([longitude, latitude, searching_category_code, searching_subcategory_code]):
            return Response({
                "error": "longitude, latitude, searching_category_code, and searching_subcategory_code are required"
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

            sub_category = WorkSubCategory.objects.get(
                subcategory_code=searching_subcategory_code,
                category=main_category,
                is_active=True
            )

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
            logger.info(f"Searching for providers in category {main_category.category_code}, subcategory {sub_category.subcategory_code}")

            # Get providers who are active and have the searched subcategory in their skills
            # First get user IDs who have this subcategory skill
            user_ids_with_subcategory = UserWorkSubCategory.objects.filter(
                sub_category=sub_category,
                user_work_selection__main_category=main_category
            ).values_list('user_work_selection__user__user__id', flat=True)

            logger.info(f"Found {len(user_ids_with_subcategory)} users with subcategory skills: {list(user_ids_with_subcategory)}")

            active_providers = ProviderActiveStatus.objects.filter(
                is_active=True,
                main_category=main_category,
                latitude__isnull=False,
                longitude__isnull=False,
                user_id__in=user_ids_with_subcategory
            ).select_related('user__profile')

            logger.info(f"Found {active_providers.count()} active providers with location data")

            for provider in active_providers:
                distance = calculate_distance(
                    latitude, longitude,
                    provider.latitude, provider.longitude
                )

                logger.info(f"Provider {provider.user.id} at ({provider.latitude}, {provider.longitude}) - Distance: {distance:.2f}km vs radius: {distance_radius}km")

                if distance <= distance_radius:
                    # Get portfolio images safely
                    portfolio_images = []
                    try:
                        # Use direct query to avoid potential prefetch issues
                        work_selection = UserWorkSelection.objects.filter(
                            user=provider.user.profile
                        ).first()

                        if work_selection:
                            portfolio_images_objs = WorkPortfolioImage.objects.filter(
                                user_work_selection=work_selection
                            ).order_by('image_order')

                            portfolio_images = [img.image.url for img in portfolio_images_objs]
                    except Exception:
                        # If there's any error getting portfolio images, continue with empty list
                        portfolio_images = []

                    nearby_providers.append({
                        'provider_id': provider.user.profile.provider_id,
                        'name': provider.user.profile.full_name,
                        'rating': 0,  # Default rating as requested
                        'description': provider.user.profile.bio or "",  # From UserProfile.bio
                        'is_verified': False,  # Default false as requested
                        'images': portfolio_images,  # Portfolio images array
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
            logger.info(f"Final result: Found {len(nearby_providers)} nearby providers within {distance_radius}km")

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
        logger.error(f"Seeker search toggle error for user {request.user.id}: {str(e)}", exc_info=True)
        return Response({
            "error": "An unexpected server error occurred. Please try again."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)