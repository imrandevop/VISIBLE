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
            # Get providers who are active and have the searched subcategory in their skills
            # First get user IDs who have this subcategory skill
            user_ids_with_subcategory = UserWorkSubCategory.objects.filter(
                sub_category=sub_category,
                user_work_selection__main_category=main_category
            ).values_list('user_work_selection__user__user__id', flat=True)

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
                    try:
                        # Get complete provider profile data
                        profile = provider.user.profile
                        provider_data = get_complete_provider_data(profile, sub_category, distance, provider.latitude, provider.longitude)
                        if provider_data:
                            nearby_providers.append(provider_data)
                    except Exception as e:
                        logger.error(f"Error processing provider {provider.user.id}: {str(e)}")
                        continue

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
        logger.error(f"Seeker search toggle error for user {request.user.id}: {str(e)}", exc_info=True)
        return Response({
            "error": "An unexpected server error occurred. Please try again."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def get_mock_rating_data():
    """Get mock rating data for testing (will be replaced with real data in future)"""
    return {
        "rating": 4.88,
        "total_reviews": "472K",
        "rating_distribution": {
            "5_star": "450K",
            "4_star": "10K",
            "3_star": "4K",
            "2_star": "3K",
            "1_star": "5K"
        },
        "reviews": [
            {
                "user": "Amitabh",
                "date": "Sep 27, 2025",
                "rating": 5,
                "review": "Ashik was very professional and cut my hair exactly how I wanted it. He even suggested a new style that fit me perfectly. Very pleased with his service and would highly recommend him. His equipment is professional."
            },
            {
                "user": "Soumya Ray",
                "date": "Sep 26, 2025",
                "rating": 5,
                "review": "On time. Very polite behaviour. He is neat and clean, he follows all my instructions as I like my hair and beard to be cut. No mess, he cleared up all the cut hairs."
            }
        ]
    }


def get_complete_provider_data(profile, subcategory, distance, provider_lat, provider_lng):
    """Get complete provider data including all profile details"""
    try:
        from django.conf import settings

        # Determine base URL for images
        if hasattr(settings, 'ALLOWED_HOSTS') and settings.ALLOWED_HOSTS:
            production_hosts = [host for host in settings.ALLOWED_HOSTS if host not in ['localhost', '127.0.0.1']]
            base_domain = production_hosts[0] if production_hosts else 'localhost:8000'
        else:
            base_domain = 'localhost:8000'

        base_url = f"https://{base_domain}" if base_domain != 'localhost:8000' else f"http://{base_domain}"

        # Get portfolio images from both sources
        portfolio_images = []
        try:
            # Work-specific portfolio images
            if hasattr(profile, 'work_selection') and profile.work_selection:
                work_portfolio_images = [
                    f"{base_url}{img.image.url}" for img in profile.work_selection.portfolio_images.all()
                ]
                portfolio_images.extend(work_portfolio_images)

            # General service portfolio images
            service_portfolio_images = [
                f"{base_url}{img.image.url}" for img in profile.service_portfolio_images.all()
            ]
            portfolio_images.extend(service_portfolio_images)
        except Exception as e:
            logger.error(f"Error getting portfolio images for provider {profile.user.id}: {str(e)}")
            portfolio_images = []

        # Get profile photo URL
        profile_photo = None
        if profile.profile_photo:
            profile_photo = f"{base_url}{profile.profile_photo.url}"

        # Get languages as array
        languages = []
        if profile.languages:
            languages = [lang.strip() for lang in profile.languages.split(',') if lang.strip()]

        # Get skills (subcategory names), description (actual skills text), and experience from work selection
        skills = None  # Will be array of subcategory names
        description = ""  # Will be actual skills description text
        experience = 0
        main_category_data = None
        all_subcategories = []

        if hasattr(profile, 'work_selection') and profile.work_selection:
            work_selection = profile.work_selection
            description = work_selection.skills or ""  # Actual skills description
            experience = work_selection.years_experience or 0

            if work_selection.main_category:
                main_category_data = {
                    'code': work_selection.main_category.category_code,
                    'name': work_selection.main_category.display_name
                }

            # Get all subcategories this provider offers
            subcategories_qs = work_selection.selected_subcategories.all()
            all_subcategories = [
                {
                    'code': sub.sub_category.subcategory_code,
                    'name': sub.sub_category.display_name
                }
                for sub in subcategories_qs
            ]

            # Skills = array of subcategory names
            if all_subcategories:
                skills = [sub['name'] for sub in all_subcategories]
            else:
                skills = None

        # Get service-specific data based on provider type
        service_specific_data = get_service_specific_data(profile)

        # Get mock rating data (will be replaced with real data in future)
        rating_data = get_mock_rating_data()

        # Build complete provider data
        provider_data = {
            'provider_id': getattr(profile, 'provider_id', f'P{profile.user.id}'),
            'name': getattr(profile, 'full_name', 'Unknown'),
            'mobile_number': profile.user.mobile_number if profile.user else '',
            'age': profile.age,
            'gender': profile.gender,
            'date_of_birth': profile.date_of_birth.isoformat() if profile.date_of_birth else None,
            'profile_photo': profile_photo,
            'languages': languages,
            'skills': skills,
            'description': description,
            'years_experience': experience,
            'user_type': profile.user_type,
            'service_type': profile.service_type,
            'rating': rating_data['rating'],
            'total_reviews': rating_data['total_reviews'],
            'rating_distribution': rating_data['rating_distribution'],
            'reviews': rating_data['reviews'],
            'is_verified': False,  # Default false
            'images': portfolio_images,
            'main_category': main_category_data,
            'subcategory': {
                'code': subcategory.subcategory_code,
                'name': subcategory.display_name
            },
            'all_subcategories': all_subcategories,
            'service_data': service_specific_data,
            'distance_km': round(distance, 2),
            'location': {
                'latitude': provider_lat,
                'longitude': provider_lng
            },
            'profile_complete': profile.profile_complete,
            'can_access_app': profile.can_access_app,
            'created_at': profile.created_at.isoformat() if profile.created_at else None
        }

        return provider_data

    except Exception as e:
        logger.error(f"Error building complete provider data for {profile.user.id}: {str(e)}")
        return None


def get_service_specific_data(profile):
    """Get service-specific data based on provider type"""
    if profile.user_type != 'provider' or not profile.service_type:
        return None

    try:
        if profile.service_type == 'worker':
            return get_worker_service_data(profile)
        elif profile.service_type == 'driver':
            return get_driver_service_data(profile)
        elif profile.service_type == 'properties':
            return get_property_service_data(profile)
        elif profile.service_type == 'SOS':
            return get_sos_service_data(profile)
    except Exception as e:
        logger.error(f"Error getting service data for provider {profile.user.id}: {str(e)}")
        return None

    return None


def get_worker_service_data(profile):
    """Get worker-specific service data"""
    if hasattr(profile, 'work_selection') and profile.work_selection:
        work_selection = profile.work_selection
        subcategories = work_selection.selected_subcategories.all()

        # Skills = array of subcategory names
        skills = [sub.sub_category.display_name for sub in subcategories] if subcategories else None

        return {
            'main_category_id': work_selection.main_category.category_code if work_selection.main_category else None,
            'main_category_name': work_selection.main_category.display_name if work_selection.main_category else None,
            'sub_category_ids': [sub.sub_category.subcategory_code for sub in subcategories],
            'sub_category_names': [sub.sub_category.display_name for sub in subcategories],
            'years_experience': work_selection.years_experience,
            'skills': skills,
            'description': work_selection.skills
        }
    return None


def get_driver_service_data(profile):
    """Get driver-specific service data"""
    data = {}

    # Get category data from work selection
    if hasattr(profile, 'work_selection') and profile.work_selection:
        work_selection = profile.work_selection
        subcategories = work_selection.selected_subcategories.all()

        # Skills = array of subcategory names
        skills = [sub.sub_category.display_name for sub in subcategories] if subcategories else None

        data.update({
            'main_category_id': work_selection.main_category.category_code if work_selection.main_category else None,
            'sub_category_ids': [sub.sub_category.subcategory_code for sub in subcategories],
            'years_experience': work_selection.years_experience,
            'skills': skills,
            'description': work_selection.skills
        })

    # Get driver-specific data
    if hasattr(profile, 'driver_service') and profile.driver_service:
        driver_data = profile.driver_service
        data.update({
            'vehicle_types': driver_data.vehicle_types.split(',') if driver_data.vehicle_types else [],
            'license_number': driver_data.license_number,
            'vehicle_registration_number': driver_data.vehicle_registration_number,
            'driving_experience_description': driver_data.driving_experience_description
        })

    return data if data else None


def get_property_service_data(profile):
    """Get property-specific service data"""
    data = {}

    # Get category data from work selection
    if hasattr(profile, 'work_selection') and profile.work_selection:
        work_selection = profile.work_selection
        subcategories = work_selection.selected_subcategories.all()

        # Skills = array of subcategory names
        skills = [sub.sub_category.display_name for sub in subcategories] if subcategories else None

        data.update({
            'main_category_id': work_selection.main_category.category_code if work_selection.main_category else None,
            'sub_category_ids': [sub.sub_category.subcategory_code for sub in subcategories],
            'years_experience': work_selection.years_experience,
            'skills': skills,
            'description': work_selection.skills
        })

    # Get property-specific data
    if hasattr(profile, 'property_service') and profile.property_service:
        property_data = profile.property_service
        data.update({
            'property_types': property_data.property_types.split(',') if property_data.property_types else [],
            'property_title': property_data.property_title,
            'parking_availability': property_data.parking_availability,
            'furnishing_type': property_data.furnishing_type,
            'property_description': property_data.property_description
        })

    return data if data else None


def get_sos_service_data(profile):
    """Get SOS/Emergency-specific service data"""
    data = {}

    # Get category data from work selection
    if hasattr(profile, 'work_selection') and profile.work_selection:
        work_selection = profile.work_selection
        subcategories = work_selection.selected_subcategories.all()

        # Skills = array of subcategory names
        skills = [sub.sub_category.display_name for sub in subcategories] if subcategories else None

        data.update({
            'main_category_id': work_selection.main_category.category_code if work_selection.main_category else None,
            'sub_category_ids': [sub.sub_category.subcategory_code for sub in subcategories],
            'years_experience': work_selection.years_experience,
            'skills': skills,
            'description': work_selection.skills
        })

    # Get SOS-specific data
    if hasattr(profile, 'sos_service') and profile.sos_service:
        sos_data = profile.sos_service
        data.update({
            'emergency_service_types': sos_data.emergency_service_types.split(',') if sos_data.emergency_service_types else [],
            'contact_number': sos_data.contact_number,
            'current_location': sos_data.current_location,
            'emergency_description': sos_data.emergency_description
        })

    return data if data else None