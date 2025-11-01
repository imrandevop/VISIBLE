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

        # Check wallet and payment if provider is trying to go online
        if active:
            from apps.profiles.models import Wallet

            # Get or create wallet for provider
            wallet, created = Wallet.objects.get_or_create(
                user_profile=user_profile,
                defaults={
                    'balance': 0.00,
                    'currency': 'INR'
                }
            )

            # Check if subscription is active
            if not wallet.is_online_subscription_active():
                # Need to deduct ₹20 for 24-hour access
                success, message = wallet.deduct_online_charge()
                if not success:
                    # Insufficient balance - prevent going online
                    return Response({
                        "error": message,
                        "status": "insufficient_balance",
                        "current_balance": float(wallet.balance),
                        "required_amount": 20.00
                    }, status=status.HTTP_402_PAYMENT_REQUIRED)

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

        # Notify nearby seekers about provider status change via WebSocket
        try:
            from channels.layers import get_channel_layer

            channel_layer = get_channel_layer()
            if channel_layer:
                # Notify seekers about provider status change (online or offline)
                notify_seekers_about_provider_status_change(
                    request.user.id, provider_category_code, provider_subcategory_code, active
                )
        except Exception as e:
            logger.warning(f"Failed to send WebSocket notification: {str(e)}")

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
        logger.error(f"Provider toggle status error for user {request.user.id}: {str(e)}", exc_info=True)
        return Response({
            "error": "An unexpected server error occurred. Please try again.",
            "debug_error": str(e) if request.user.is_staff else None
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

                # Check both: seeker's search radius AND provider's service coverage area
                # Provider must be within seeker's search radius
                # AND seeker must be within provider's service coverage area
                if distance <= distance_radius:
                    try:
                        # Get complete provider profile data
                        profile = provider.user.profile

                        # Check if provider has service_coverage_area set and if seeker is within it
                        if profile.service_coverage_area and distance > profile.service_coverage_area:
                            # Seeker is outside provider's service coverage area, skip this provider
                            continue

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


def notify_seekers_about_provider_status_change(provider_user_id, category_code, subcategory_code, is_online):
    """Notify nearby seekers when a provider changes status - SYNCHRONOUS VERSION"""
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        from apps.core.models import SeekerSearchPreference, ProviderActiveStatus, calculate_distance
        from apps.work_categories.models import WorkCategory, WorkSubCategory

        logger.info(f"🔔 notify_seekers_about_provider_status_change called: provider={provider_user_id}, category={category_code}, subcategory={subcategory_code}, online={is_online}")

        # Get provider's current location and details
        try:
            provider_status = ProviderActiveStatus.objects.select_related(
                'user__profile', 'main_category', 'sub_category'
            ).get(user_id=provider_user_id)
            logger.info(f"✅ Provider status found: {provider_status.user.profile.full_name} at ({provider_status.latitude}, {provider_status.longitude})")
        except ProviderActiveStatus.DoesNotExist:
            logger.warning(f"❌ Provider status not found for user_id={provider_user_id}")
            return

        # Get category and subcategory objects
        try:
            category = WorkCategory.objects.get(category_code=category_code, is_active=True)
            subcategory = WorkSubCategory.objects.get(
                subcategory_code=subcategory_code, category=category, is_active=True
            )
            logger.info(f"✅ Category found: {category.name}, Subcategory: {subcategory.name}")
        except (WorkCategory.DoesNotExist, WorkSubCategory.DoesNotExist):
            logger.warning(f"❌ Category or Subcategory not found: category_code={category_code}, subcategory_code={subcategory_code}")
            return

        # Find seekers actively searching for this category/subcategory
        searching_seekers = SeekerSearchPreference.objects.filter(
            is_searching=True,
            searching_category=category,
            searching_subcategory=subcategory
        ).select_related('user')

        logger.info(f"📊 Found {searching_seekers.count()} active seekers searching for {category.name} > {subcategory.name}")

        channel_layer = get_channel_layer()

        if not channel_layer:
            logger.error(f"❌ Channel layer is None!")
            return

        for seeker_pref in searching_seekers:
            # Validate coordinates exist
            if not all([seeker_pref.latitude, seeker_pref.longitude, provider_status.latitude, provider_status.longitude]):
                logger.warning(f"⚠️ Missing coordinates - Seeker: ({seeker_pref.latitude}, {seeker_pref.longitude}), Provider: ({provider_status.latitude}, {provider_status.longitude})")
                continue

            # Calculate distance between seeker and provider
            distance = calculate_distance(
                seeker_pref.latitude, seeker_pref.longitude,
                provider_status.latitude, provider_status.longitude
            )

            logger.info(f"🔍 Checking seeker {seeker_pref.user.mobile_number}: distance={distance:.2f}km, radius={seeker_pref.distance_radius}km")

            # For online: notify only if within range
            # For offline: notify all seekers (they might have this provider visible)
            if is_online and distance > seeker_pref.distance_radius:
                logger.info(f"⚠️ Seeker {seeker_pref.user.mobile_number} is OUT OF RANGE (distance={distance:.2f}km > radius={seeker_pref.distance_radius}km)")
                continue

            # Check provider's service coverage area
            provider_profile = provider_status.user.profile
            if is_online and provider_profile.service_coverage_area:
                if distance > provider_profile.service_coverage_area:
                    logger.info(f"⚠️ Seeker {seeker_pref.user.mobile_number} is OUTSIDE provider's service coverage area (distance={distance:.2f}km > coverage={provider_profile.service_coverage_area}km)")
                    continue

            if distance <= seeker_pref.distance_radius:
                logger.info(f"✅ Seeker {seeker_pref.user.mobile_number} is within range!")
            else:
                logger.info(f"⚠️ Seeker {seeker_pref.user.mobile_number} OUT OF RANGE but notifying offline status")

            if is_online:
                # Provider came online - send new provider notification
                provider_data = get_complete_provider_data(
                    provider_status.user.profile,
                    subcategory,
                    distance,
                    provider_status.latitude,
                    provider_status.longitude
                )

                if provider_data:
                    logger.info(f"📤 Sending new_provider_available to group: user_{seeker_pref.user.id}_seeker")
                    async_to_sync(channel_layer.group_send)(
                        f'user_{seeker_pref.user.id}_seeker',
                        {
                            'type': 'new_provider_available',
                            'provider': provider_data
                        }
                    )
                    logger.info(f"✅ Message sent successfully to seeker {seeker_pref.user.mobile_number}")
                else:
                    logger.warning(f"❌ Provider data is None for provider {provider_user_id}")
            else:
                # Provider went offline - send offline notification
                # Get all subcategories this provider offers
                all_subcategories = []
                if hasattr(provider_status.user.profile, 'work_selection') and provider_status.user.profile.work_selection:
                    subcategories_qs = provider_status.user.profile.work_selection.selected_subcategories.all()
                    all_subcategories = [
                        {
                            'code': sub.sub_category.subcategory_code,
                            'name': sub.sub_category.display_name
                        }
                        for sub in subcategories_qs
                    ]

                logger.info(f"📤 Sending provider_went_offline to group: user_{seeker_pref.user.id}_seeker")
                async_to_sync(channel_layer.group_send)(
                    f'user_{seeker_pref.user.id}_seeker',
                    {
                        'type': 'provider_went_offline',
                        'provider_id': provider_status.user.profile.provider_id,
                        'main_category': {
                            'code': category.category_code,
                            'name': category.name
                        },
                        'all_subcategories': all_subcategories
                    }
                )

    except Exception as e:
        logger.error(f"Error notifying seekers about provider status change: {str(e)}")


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

        # Validate coordinates
        if provider_lat is None or provider_lng is None:
            logger.error(f"❌ Provider coordinates are None: lat={provider_lat}, lng={provider_lng}")
            return None

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
            'service_coverage_area': profile.service_coverage_area,  # Coverage area in km
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
        if profile.service_type == 'skill':
            return get_skill_service_data(profile)
        elif profile.service_type == 'vehicle':
            return get_vehicle_service_data(profile)
        elif profile.service_type == 'properties':
            return get_property_service_data(profile)
        elif profile.service_type == 'SOS':
            return get_sos_service_data(profile)
    except Exception as e:
        logger.error(f"Error getting service data for provider {profile.user.id}: {str(e)}")
        return None

    return None


def get_skill_service_data(profile):
    """Get skill-specific service data"""
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


def get_vehicle_service_data(profile):
    """Get vehicle-specific service data"""
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

    # Get vehicle-specific data
    if hasattr(profile, 'vehicle_service') and profile.vehicle_service:
        vehicle_data = profile.vehicle_service
        data.update({
            'license_number': vehicle_data.license_number,
            'vehicle_registration_number': vehicle_data.vehicle_registration_number,
            'driving_experience_description': vehicle_data.driving_experience_description
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