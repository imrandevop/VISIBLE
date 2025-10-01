import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from apps.core.models import ProviderActiveStatus, SeekerSearchPreference, calculate_distance
from apps.profiles.models import UserProfile
from apps.work_categories.models import WorkCategory, WorkSubCategory, UserWorkSubCategory, WorkPortfolioImage

logger = logging.getLogger(__name__)

"""
WebSocket Message Examples:

1. Provider WebSocket Message (Updated):
{
    "type": "provider_status_update",
    "active": true,
    "category_code": "MS0001",
    "subcategory_code": "SS0001"
}

2. Seeker Search Update Message:
{
    "type": "seeker_search_update",
    "searching": true,
    "latitude": 11.2588,
    "longitude": 75.8577,
    "category_code": "MS0001",
    "subcategory_code": "SS0001",
    "distance_radius": 5
}

3. New Provider Available Notification (Updated):
{
    "type": "new_provider_available",
    "provider": {
        "provider_id": "P123",
        "name": "John Smith",
        "rating": 0,
        "description": "Experienced plumber with 5+ years experience",
        "is_verified": false,
        "images": [
            "/media/portfolio/image1.jpg",
            "/media/portfolio/image2.jpg"
        ],
        "main_category": {
            "code": "MS0001",
            "name": "Maintenance Services"
        },
        "subcategory": {
            "code": "SS0001",
            "name": "Plumbing"
        },
        "all_subcategories": [
            {"code": "SS0001", "name": "Plumbing"},
            {"code": "SS0002", "name": "Electrical"},
            {"code": "SS0003", "name": "Carpentry"}
        ],
        "distance_km": 2.5,
        "location": {
            "latitude": 11.2588,
            "longitude": 75.8577
        }
    }
}

4. Provider Went Offline Notification (Updated):
{
    "type": "provider_went_offline",
    "provider_id": "P123",
    "main_category": {
        "code": "MS0001",
        "name": "Maintenance Services"
    },
    "all_subcategories": [
        {"code": "SS0001", "name": "Plumbing"},
        {"code": "SS0002", "name": "Electrical"},
        {"code": "SS0003", "name": "Carpentry"}
    ]
}
"""


class LocationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            self.user_type = self.scope['url_route']['kwargs']['user_type']
            self.user = self.scope["user"]

            logger.info(f"WebSocket connection attempt - User: {self.user}, Type: {self.user_type}, Is Anonymous: {isinstance(self.user, AnonymousUser)}")

            if isinstance(self.user, AnonymousUser):
                logger.warning(f"WebSocket connection rejected - Anonymous user")
                await self.close(code=4001)
                return

            # Create user-specific group
            self.user_group_name = f'user_{self.user.id}_{self.user_type}'

            # Join user group
            await self.channel_layer.group_add(
                self.user_group_name,
                self.channel_name
            )

            logger.info(f"WebSocket connected successfully for user {self.user.id} ({self.user_type})")
            await self.accept()

        except Exception as e:
            logger.error(f"WebSocket connection error: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': f'Connection failed: {str(e)}'
            }))
            await self.close(code=4000)

    async def disconnect(self, close_code):
        # Leave user group
        await self.channel_layer.group_discard(
            self.user_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        try:
            # Check if user and user_type are properly initialized
            if not hasattr(self, 'user') or not hasattr(self, 'user_type'):
                logger.error(f"WebSocket consumer not properly initialized")
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'WebSocket connection not properly initialized'
                }))
                return

            if isinstance(self.user, AnonymousUser):
                logger.error(f"Anonymous user trying to send message")
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'Authentication required'
                }))
                return

            logger.info(f"WebSocket received message for user {self.user.id}: {text_data}")

            # Handle empty or whitespace-only messages
            if not text_data or not text_data.strip():
                logger.warning(f"Empty message received from user {self.user.id}")
                return

            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')

            logger.info(f"Processing message type: {message_type} for user {self.user.id}")

            if message_type == 'provider_status_update':
                await self.handle_provider_status_update(text_data_json)
            elif message_type == 'seeker_search_update':
                await self.handle_seeker_search_update(text_data_json)
            elif message_type == 'update_distance_radius':
                await self.handle_distance_radius_update(text_data_json)
            elif message_type == 'ping':
                # Health check ping
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'message': 'WebSocket connection is active'
                }))
            elif not message_type:
                logger.warning(f"Message without type received from user {self.user.id}")
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'Message type is required'
                }))
            else:
                logger.warning(f"Unknown message type '{message_type}' received from user {self.user.id}")
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': f'Unknown message type: {message_type}'
                }))

        except json.JSONDecodeError as e:
            user_id = getattr(self, 'user', {}).get('id', 'unknown') if hasattr(self, 'user') else 'unknown'
            logger.error(f"JSON decode error for user {user_id}: {str(e)}, data: {text_data}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Invalid JSON format'
            }))
        except Exception as e:
            user_id = getattr(self, 'user', {}).get('id', 'unknown') if hasattr(self, 'user') else 'unknown'
            logger.error(f"WebSocket error for user {user_id}: {str(e)}, data: {text_data}", exc_info=True)
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': f'An unexpected error occurred: {str(e)}'
            }))

    async def handle_provider_status_update(self, data):
        """Handle provider going active/inactive"""
        if self.user_type != 'provider':
            return

        active = data.get('active', False)
        category_code = data.get('category_code', '')
        subcategory_code = data.get('subcategory_code', '')

        if active:
            # Notify seekers in the same category who are currently searching
            await self.notify_nearby_seekers_about_new_provider(category_code, subcategory_code)
        else:
            # Notify seekers that this provider went offline
            await self.notify_seekers_about_provider_offline(category_code, subcategory_code)

    async def handle_seeker_search_update(self, data):
        """Handle seeker starting/stopping search"""
        if self.user_type != 'seeker':
            return

        searching = data.get('searching', False)
        category_code = data.get('category_code', '')
        subcategory_code = data.get('subcategory_code', '')

        if searching:
            # Send current nearby providers
            nearby_providers = await self.get_nearby_providers_enhanced(
                data.get('latitude'),
                data.get('longitude'),
                data.get('distance_radius', 5),
                category_code,
                subcategory_code
            )

            await self.send(text_data=json.dumps({
                'type': 'nearby_providers',
                'providers': nearby_providers
            }))

    async def handle_distance_radius_update(self, data):
        """Handle seeker updating their distance radius"""
        if self.user_type != 'seeker':
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Only seekers can update distance radius'
            }))
            return

        # Validate user is a seeker
        user_profile = await self.get_user_profile(self.user.id)
        if not user_profile or user_profile.get('user_type') != 'seeker':
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Only seekers can update distance radius'
            }))
            return

        # Get and validate fields
        try:
            distance_radius = float(data.get('distance_radius')) if data.get('distance_radius') is not None else None
            latitude = float(data.get('latitude')) if data.get('latitude') is not None else None
            longitude = float(data.get('longitude')) if data.get('longitude') is not None else None
        except (ValueError, TypeError):
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Invalid numeric values for distance_radius, latitude, or longitude'
            }))
            return

        # Validate distance radius range
        if distance_radius is not None and (distance_radius <= 0 or distance_radius > 50):
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Distance radius must be between 1 and 50 km'
            }))
            return

        category_code = data.get('category_code', '').strip()
        subcategory_code = data.get('subcategory_code', '').strip()

        # Validate required fields
        if not all([distance_radius, latitude, longitude, category_code, subcategory_code]):
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'distance_radius, latitude, longitude, category_code, and subcategory_code are required'
            }))
            return

        # Validate categories exist
        categories_valid = await self.validate_categories(category_code, subcategory_code)
        if not categories_valid:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': f'Category with code \'{category_code}\' or subcategory with code \'{subcategory_code}\' not found or inactive'
            }))
            return

        # Update seeker's search preference in database
        update_success = await self.update_seeker_distance_preference(
            self.user.id, distance_radius, latitude, longitude, category_code, subcategory_code
        )

        if not update_success:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Failed to update search preferences'
            }))
            return

        # Get updated nearby providers with new distance radius
        nearby_providers = await self.get_nearby_providers_enhanced(
            latitude, longitude, distance_radius, category_code, subcategory_code
        )

        # Send response with updated provider list
        await self.send(text_data=json.dumps({
            'type': 'distance_updated',
            'distance_radius': distance_radius,
            'providers': nearby_providers
        }))

    async def notify_nearby_seekers_about_new_provider(self, category_code, subcategory_code=None):
        """Notify seekers when a new provider comes online"""
        provider_status = await self.get_provider_status_enhanced(self.user.id)

        if not provider_status:
            return

        # Get all seekers currently searching in this category
        searching_seekers = await self.get_searching_seekers_by_provider(self.user.id, category_code)

        for seeker in searching_seekers:
            distance = calculate_distance(
                seeker['latitude'], seeker['longitude'],
                provider_status['latitude'], provider_status['longitude']
            )

            if distance <= seeker['distance_radius']:
                # Add distance and seeker-specific subcategory to provider data
                provider_data = provider_status.copy()
                provider_data['distance_km'] = round(distance, 2)
                provider_data['subcategory'] = {
                    'code': seeker['searching_subcategory_code'],
                    'name': seeker['searching_subcategory_name']
                }

                # Notify this seeker about the new provider with complete data
                await self.channel_layer.group_send(
                    f'user_{seeker["user_id"]}_seeker',
                    {
                        'type': 'new_provider_available',
                        'provider': provider_data
                    }
                )

    async def notify_seekers_about_provider_offline(self, category_code, subcategory_code=None):
        """Notify seekers when a provider goes offline"""
        provider_info = await self.get_provider_info_for_offline_notification(self.user.id, category_code)

        if not provider_info:
            return

        searching_seekers = await self.get_searching_seekers_by_provider(self.user.id, category_code)

        for seeker in searching_seekers:
            await self.channel_layer.group_send(
                f'user_{seeker["user_id"]}_seeker',
                {
                    'type': 'provider_went_offline',
                    'provider_id': provider_info['provider_id'],
                    'main_category': {
                        'code': provider_info['main_category_code'],
                        'name': provider_info['main_category_name']
                    },
                    'all_subcategories': provider_info['all_subcategories']
                }
            )

    # WebSocket message handlers
    async def new_provider_available(self, event):
        """Send new provider notification to seeker"""
        await self.send(text_data=json.dumps({
            'type': 'new_provider_available',
            'provider': event['provider']
        }))

    async def provider_went_offline(self, event):
        """Send provider offline notification to seeker"""
        await self.send(text_data=json.dumps({
            'type': 'provider_went_offline',
            'provider_id': event['provider_id'],
            'main_category': event.get('main_category', {}),
            'all_subcategories': event.get('all_subcategories', [])
        }))

    # Database queries (async)
    @database_sync_to_async
    def get_provider_status(self, user_id):
        """Get provider status details"""
        try:
            provider_status = ProviderActiveStatus.objects.select_related(
                'user__profile', 'sub_category'
            ).get(user_id=user_id, is_active=True)

            return {
                'provider_id': provider_status.user.profile.provider_id,
                'name': provider_status.user.profile.full_name,
                'subcategory': provider_status.sub_category.display_name,
                'latitude': provider_status.latitude,
                'longitude': provider_status.longitude
            }
        except ProviderActiveStatus.DoesNotExist:
            return None

    @database_sync_to_async
    def get_provider_status_enhanced(self, user_id):
        """Get enhanced provider status details with complete profile information"""
        try:
            provider_status = ProviderActiveStatus.objects.select_related(
                'user__profile', 'sub_category', 'main_category'
            ).get(user_id=user_id, is_active=True)

            profile = provider_status.user.profile

            # Get complete provider data using the same logic as search API
            return self.build_complete_provider_data(
                profile,
                provider_status.latitude,
                provider_status.longitude,
                provider_status.main_category,
                provider_status.sub_category
            )
        except ProviderActiveStatus.DoesNotExist:
            return None

    def build_complete_provider_data(self, profile, latitude, longitude, main_category=None, current_subcategory=None):
        """Build complete provider data with all profile details"""
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
                logger.warning(f"Error getting portfolio images for provider {profile.user.id}: {str(e)}")
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

                # Use main_category from work_selection if not provided
                if not main_category and work_selection.main_category:
                    main_category = work_selection.main_category

                if main_category:
                    main_category_data = {
                        'code': main_category.category_code,
                        'name': main_category.display_name
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

            # Get service-specific data
            service_specific_data = self.get_provider_service_data(profile)

            # Get mock rating data (will be replaced with real data in future)
            rating_data = self.get_mock_rating_data()

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
                'current_subcategory': {
                    'code': current_subcategory.subcategory_code,
                    'name': current_subcategory.display_name
                } if current_subcategory else None,
                'all_subcategories': all_subcategories,
                'service_data': service_specific_data,
                'location': {
                    'latitude': latitude,
                    'longitude': longitude
                },
                'profile_complete': profile.profile_complete,
                'can_access_app': profile.can_access_app,
                'created_at': profile.created_at.isoformat() if profile.created_at else None
            }

            return provider_data

        except Exception as e:
            logger.error(f"Error building complete provider data for {profile.user.id}: {str(e)}")
            return None

    def get_mock_rating_data(self):
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

    def get_provider_service_data(self, profile):
        """Get service-specific data based on provider type"""
        if profile.user_type != 'provider' or not profile.service_type:
            return None

        try:
            if profile.service_type == 'worker':
                return self.get_worker_service_data(profile)
            elif profile.service_type == 'driver':
                return self.get_driver_service_data(profile)
            elif profile.service_type == 'properties':
                return self.get_property_service_data(profile)
            elif profile.service_type == 'SOS':
                return self.get_sos_service_data(profile)
        except Exception as e:
            logger.error(f"Error getting service data for provider {profile.user.id}: {str(e)}")
            return None

        return None

    def get_worker_service_data(self, profile):
        """Get worker-specific service data"""
        if hasattr(profile, 'work_selection') and profile.work_selection:
            work_selection = profile.work_selection
            subcategories = work_selection.selected_subcategories.all()

            return {
                'main_category_id': work_selection.main_category.category_code if work_selection.main_category else None,
                'main_category_name': work_selection.main_category.display_name if work_selection.main_category else None,
                'sub_category_ids': [sub.sub_category.subcategory_code for sub in subcategories],
                'sub_category_names': [sub.sub_category.display_name for sub in subcategories],
                'years_experience': work_selection.years_experience,
                'skills': [sub.sub_category.display_name for sub in subcategories] if subcategories else None,
                'description': work_selection.skills
            }
        return None

    def get_driver_service_data(self, profile):
        """Get driver-specific service data"""
        data = {}

        # Get category data from work selection
        if hasattr(profile, 'work_selection') and profile.work_selection:
            work_selection = profile.work_selection
            subcategories = work_selection.selected_subcategories.all()
            data.update({
                'main_category_id': work_selection.main_category.category_code if work_selection.main_category else None,
                'sub_category_ids': [sub.sub_category.subcategory_code for sub in subcategories],
                'years_experience': work_selection.years_experience,
                'skills': [sub.sub_category.display_name for sub in subcategories] if subcategories else None,
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

    def get_property_service_data(self, profile):
        """Get property-specific service data"""
        data = {}

        # Get category data from work selection
        if hasattr(profile, 'work_selection') and profile.work_selection:
            work_selection = profile.work_selection
            subcategories = work_selection.selected_subcategories.all()
            data.update({
                'main_category_id': work_selection.main_category.category_code if work_selection.main_category else None,
                'sub_category_ids': [sub.sub_category.subcategory_code for sub in subcategories],
                'years_experience': work_selection.years_experience,
                'skills': [sub.sub_category.display_name for sub in subcategories] if subcategories else None,
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

    def get_sos_service_data(self, profile):
        """Get SOS/Emergency-specific service data"""
        data = {}

        # Get category data from work selection
        if hasattr(profile, 'work_selection') and profile.work_selection:
            work_selection = profile.work_selection
            subcategories = work_selection.selected_subcategories.all()
            data.update({
                'main_category_id': work_selection.main_category.category_code if work_selection.main_category else None,
                'sub_category_ids': [sub.sub_category.subcategory_code for sub in subcategories],
                'years_experience': work_selection.years_experience,
                'skills': [sub.sub_category.display_name for sub in subcategories] if subcategories else None,
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

    @database_sync_to_async
    def get_provider_info_for_offline_notification(self, user_id, category_code):
        """Get provider info for offline notification (regardless of active status)"""
        try:
            # Get provider profile info
            from apps.profiles.models import UserProfile
            profile = UserProfile.objects.select_related('user').get(user_id=user_id)

            # Get category info
            category = WorkCategory.objects.get(category_code=category_code, is_active=True)

            # Get all subcategories this provider offers
            provider_subcategories = UserWorkSubCategory.objects.filter(
                user_work_selection__user__user__id=user_id,
                user_work_selection__main_category=category
            ).select_related('sub_category').values(
                'sub_category__subcategory_code',
                'sub_category__display_name'
            )

            all_subcategories = [
                {
                    'code': sub['sub_category__subcategory_code'],
                    'name': sub['sub_category__display_name']
                }
                for sub in provider_subcategories
            ]

            return {
                'provider_id': profile.provider_id,
                'name': profile.full_name,
                'main_category_code': category.category_code,
                'main_category_name': category.name,
                'all_subcategories': all_subcategories
            }
        except (UserProfile.DoesNotExist, WorkCategory.DoesNotExist):
            return None

    @database_sync_to_async
    def get_searching_seekers_by_provider(self, provider_user_id, category_code):
        """Get all seekers searching for subcategories that this provider has"""
        try:
            category = WorkCategory.objects.get(category_code=category_code, is_active=True)

            # Get provider's subcategories
            provider_subcategories = UserWorkSubCategory.objects.filter(
                user_work_selection__user__user__id=provider_user_id,
                user_work_selection__main_category=category
            ).values_list('sub_category', flat=True)

            # Get seekers searching for any of these subcategories
            seekers = SeekerSearchPreference.objects.filter(
                searching_category=category,
                searching_subcategory__in=provider_subcategories,
                is_searching=True
            ).select_related('user', 'searching_subcategory')

            return [{
                'user_id': seeker.user_id,
                'latitude': seeker.latitude,
                'longitude': seeker.longitude,
                'distance_radius': seeker.distance_radius,
                'searching_subcategory_code': seeker.searching_subcategory.subcategory_code,
                'searching_subcategory_name': seeker.searching_subcategory.display_name
            } for seeker in seekers]
        except WorkCategory.DoesNotExist:
            return []

    @database_sync_to_async
    def get_nearby_providers(self, seeker_lat, seeker_lng, radius, category_code, subcategory_code):
        """Get nearby active providers for a seeker's specific subcategory"""
        try:
            category = WorkCategory.objects.get(category_code=category_code, is_active=True)
            subcategory = WorkSubCategory.objects.get(
                subcategory_code=subcategory_code,
                category=category,
                is_active=True
            )

            # Get providers who are active and have this subcategory in their skills
            # First get user IDs who have this subcategory skill
            user_ids_with_subcategory = UserWorkSubCategory.objects.filter(
                sub_category=subcategory,
                user_work_selection__main_category=category
            ).values_list('user_work_selection__user__user__id', flat=True)

            providers = ProviderActiveStatus.objects.filter(
                is_active=True,
                main_category=category,
                latitude__isnull=False,
                longitude__isnull=False,
                user_id__in=user_ids_with_subcategory
            ).select_related('user__profile')

            nearby_providers = []
            for provider in providers:
                distance = calculate_distance(
                    seeker_lat, seeker_lng,
                    provider.latitude, provider.longitude
                )

                if distance <= radius:
                    nearby_providers.append({
                        'provider_id': provider.user.profile.provider_id,
                        'name': provider.user.profile.full_name,
                        'rating': 0,  # Default rating
                        'description': provider.user.profile.bio or "",  # From UserProfile.bio
                        'is_verified': False,  # Default false
                        'images': [],  # Will be populated by enhanced method
                        'subcategory': {
                            'code': subcategory.subcategory_code,
                            'name': subcategory.display_name
                        },
                        'distance_km': round(distance, 2),
                        'location': {
                            'latitude': provider.latitude,
                            'longitude': provider.longitude
                        }
                    })

            return sorted(nearby_providers, key=lambda x: x['distance_km'])
        except (WorkCategory.DoesNotExist, WorkSubCategory.DoesNotExist):
            return []

    @database_sync_to_async
    def get_user_profile(self, user_id):
        """Get user profile information"""
        try:
            profile = UserProfile.objects.get(user_id=user_id)
            return {
                'user_type': profile.user_type,
                'full_name': profile.full_name,
                'bio': profile.bio or ""
            }
        except UserProfile.DoesNotExist:
            return None

    @database_sync_to_async
    def validate_categories(self, category_code, subcategory_code):
        """Validate that category and subcategory exist and are active"""
        try:
            category = WorkCategory.objects.get(category_code=category_code, is_active=True)
            WorkSubCategory.objects.get(
                subcategory_code=subcategory_code,
                category=category,
                is_active=True
            )
            return True
        except (WorkCategory.DoesNotExist, WorkSubCategory.DoesNotExist):
            return False

    @database_sync_to_async
    def update_seeker_distance_preference(self, user_id, distance_radius, latitude, longitude, category_code, subcategory_code):
        """Update seeker's search preferences with new distance radius"""
        try:
            with transaction.atomic():
                # Get category and subcategory objects
                main_category = WorkCategory.objects.get(category_code=category_code, is_active=True)
                sub_category = WorkSubCategory.objects.get(
                    subcategory_code=subcategory_code,
                    category=main_category,
                    is_active=True
                )

                # Update or create seeker search preference
                search_preference, created = SeekerSearchPreference.objects.get_or_create(
                    user_id=user_id,
                    defaults={
                        'is_searching': True,
                        'latitude': latitude,
                        'longitude': longitude,
                        'searching_category': main_category,
                        'searching_subcategory': sub_category,
                        'distance_radius': distance_radius,
                    }
                )

                if not created:
                    search_preference.latitude = latitude
                    search_preference.longitude = longitude
                    search_preference.searching_category = main_category
                    search_preference.searching_subcategory = sub_category
                    search_preference.distance_radius = distance_radius
                    search_preference.save()

                return True
        except Exception:
            return False

    @database_sync_to_async
    def get_nearby_providers_enhanced(self, seeker_lat, seeker_lng, radius, category_code, subcategory_code):
        """Get nearby active providers with complete profile information"""
        try:
            category = WorkCategory.objects.get(category_code=category_code, is_active=True)
            subcategory = WorkSubCategory.objects.get(
                subcategory_code=subcategory_code,
                category=category,
                is_active=True
            )

            # Get providers who are active and have this subcategory in their skills
            user_ids_with_subcategory = UserWorkSubCategory.objects.filter(
                sub_category=subcategory,
                user_work_selection__main_category=category
            ).values_list('user_work_selection__user__user__id', flat=True)

            providers = ProviderActiveStatus.objects.filter(
                is_active=True,
                main_category=category,
                latitude__isnull=False,
                longitude__isnull=False,
                user_id__in=user_ids_with_subcategory
            ).select_related('user__profile')

            nearby_providers = []
            for provider in providers:
                distance = calculate_distance(
                    seeker_lat, seeker_lng,
                    provider.latitude, provider.longitude
                )

                if distance <= radius:
                    # Get complete provider data
                    provider_data = self.build_complete_provider_data(
                        provider.user.profile,
                        provider.latitude,
                        provider.longitude,
                        category,
                        subcategory
                    )

                    if provider_data:
                        provider_data['distance_km'] = round(distance, 2)
                        provider_data['subcategory'] = {
                            'code': subcategory.subcategory_code,
                            'name': subcategory.display_name
                        }
                        nearby_providers.append(provider_data)

            return sorted(nearby_providers, key=lambda x: x['distance_km'])
        except (WorkCategory.DoesNotExist, WorkSubCategory.DoesNotExist):
            return []