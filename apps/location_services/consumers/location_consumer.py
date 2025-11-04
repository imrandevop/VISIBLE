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
WebSocket Connection URLs:



Production:
- Provider: wss://api.visibleapp.in/ws/location/provider/
- Seeker: wss://api.visibleapp.in/ws/location/seeker/
"""


class LocationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            print(f"[WEBSOCKET CONNECT] Connection attempt started")
            self.user_type = self.scope['url_route']['kwargs']['user_type']
            self.user = self.scope["user"]

            print(f"[WEBSOCKET CONNECT] User: {self.user}, Type: {self.user_type}, Is Anonymous: {isinstance(self.user, AnonymousUser)}")
            logger.info(f"WebSocket connection attempt - User: {self.user}, Type: {self.user_type}, Is Anonymous: {isinstance(self.user, AnonymousUser)}")

            if isinstance(self.user, AnonymousUser):
                print(f"[WEBSOCKET CONNECT] REJECTED - Anonymous user")
                logger.warning(f"WebSocket connection rejected - Anonymous user")
                await self.close(code=4001)
                return

            # Create user-specific group
            self.user_group_name = f'user_{self.user.id}_{self.user_type}'
            print(f"[WEBSOCKET CONNECT] User group name: {self.user_group_name}")

            # Join user group
            await self.channel_layer.group_add(
                self.user_group_name,
                self.channel_name
            )

            print(f"[WEBSOCKET CONNECT] Successfully joined group, accepting connection")
            logger.info(f"WebSocket connected successfully for user {self.user.id} ({self.user_type})")
            await self.accept()
            print(f"[WEBSOCKET CONNECT] Connection accepted for user {self.user.id}")

        except Exception as e:
            logger.error(f"WebSocket connection error: {str(e)}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': f'Connection failed: {str(e)}'
            }))
            await self.close(code=4000)

    async def disconnect(self, close_code):
        """Handle WebSocket disconnect"""
        try:
            # Leave user group
            if hasattr(self, 'user_group_name'):
                await self.channel_layer.group_discard(
                    self.user_group_name,
                    self.channel_name
                )

            logger.info(f"WebSocket disconnected for user {getattr(self, 'user', 'unknown')} (code: {close_code})")
        except Exception as e:
            logger.error(f"Error during disconnect: {str(e)}")


    async def receive(self, text_data):
        try:
            print(f"[WEBSOCKET RECEIVE] Raw data received: {text_data}")

            # Check if user and user_type are properly initialized
            if not hasattr(self, 'user') or not hasattr(self, 'user_type'):
                logger.error(f"WebSocket consumer not properly initialized")
                print(f"[WEBSOCKET ERROR] Consumer not properly initialized")
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'WebSocket connection not properly initialized'
                }))
                return

            if isinstance(self.user, AnonymousUser):
                logger.error(f"Anonymous user trying to send message")
                print(f"[WEBSOCKET ERROR] Anonymous user trying to send message")
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'Authentication required'
                }))
                return

            print(f"[WEBSOCKET RECEIVE] User ID: {self.user.id}, User type: {self.user_type}")
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
                print(f"[WEBSOCKET PING] Received ping from user {self.user.id}")
                response = {
                    'type': 'pong',
                    'message': 'WebSocket connection is active'
                }
                print(f"[WEBSOCKET PONG] Sending response: {response}")
                await self.send(text_data=json.dumps(response))
                print(f"[WEBSOCKET PONG] Response sent successfully")
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
                # Add distance to provider data
                provider_data = provider_status.copy()
                provider_data['distance_km'] = round(distance, 2)

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

            # Determine provider type (individual or business)
            provider_type = 'business' if profile.business_name else 'individual'

            # Get service-specific data (includes category info and service details)
            service_specific_data = self.get_provider_service_data(profile, main_category, current_subcategory)

            # Get mock rating data (will be replaced with real data in future)
            rating_data = self.get_mock_rating_data()

            # Build complete provider data with common fields
            provider_data = {
                'provider_id': getattr(profile, 'provider_id', f'P{profile.user.id}'),
                'mobile_number': profile.user.mobile_number if profile.user else '',
                'profile_photo': profile_photo,
                'languages': languages,
                'user_type': profile.user_type,
                'provider_type': provider_type,
                'service_type': profile.service_type,
                'service_coverage_area': profile.service_coverage_area,
                'rating': rating_data['rating'],
                'total_reviews': rating_data['total_reviews'],
                'rating_distribution': rating_data['rating_distribution'],
                'reviews': rating_data['reviews'],
                'is_verified': False,  # Default false
                'portfolio_images': portfolio_images,
                'service_data': service_specific_data,
                'location': {
                    'latitude': latitude,
                    'longitude': longitude
                },
                'profile_complete': profile.profile_complete,
                'can_access_app': profile.can_access_app,
                'created_at': profile.created_at.isoformat() if profile.created_at else None
            }

            # Add type-specific fields (matches profile setup API behavior)
            if provider_type == 'business':
                # Business providers: show business fields only
                provider_data['business_name'] = profile.business_name
                provider_data['business_location'] = profile.business_location
                provider_data['established_date'] = profile.established_date.isoformat() if profile.established_date else None
                provider_data['website'] = profile.website
            else:
                # Individual providers: show personal fields only
                provider_data['full_name'] = getattr(profile, 'full_name', 'Unknown')
                provider_data['age'] = profile.age
                provider_data['gender'] = profile.gender
                provider_data['date_of_birth'] = profile.date_of_birth.isoformat() if profile.date_of_birth else None

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

    def get_provider_service_data(self, profile, main_category=None, current_subcategory=None):
        """Get service-specific data based on provider type"""
        if profile.user_type != 'provider' or not profile.service_type:
            return None

        try:
            if profile.service_type == 'skill':
                return self.get_skill_service_data(profile, main_category, current_subcategory)
            elif profile.service_type == 'vehicle':
                return self.get_vehicle_service_data(profile, main_category, current_subcategory)
            elif profile.service_type == 'properties':
                return self.get_property_service_data(profile, main_category, current_subcategory)
            elif profile.service_type == 'SOS':
                return self.get_sos_service_data(profile, main_category, current_subcategory)
        except Exception as e:
            logger.error(f"Error getting service data for provider {profile.user.id}: {str(e)}")
            return None

        return None

    def get_skill_service_data(self, profile, main_category=None, current_subcategory=None):
        """Get skill-specific service data with category information"""
        if hasattr(profile, 'work_selection') and profile.work_selection:
            work_selection = profile.work_selection

            # Use main_category from work_selection if not provided
            if not main_category and work_selection.main_category:
                main_category = work_selection.main_category

            # Get all subcategories
            subcategories = work_selection.selected_subcategories.all()

            return {
                'main_category_id': main_category.category_code if main_category else None,
                'main_category_name': main_category.display_name if main_category else None,
                'sub_category_ids': [sub.sub_category.subcategory_code for sub in subcategories],
                'sub_category_names': [sub.sub_category.display_name for sub in subcategories],
                'years_experience': work_selection.years_experience,
                'skills': [sub.sub_category.display_name for sub in subcategories] if subcategories else None,
                'description': work_selection.skills
            }
        return None

    def get_vehicle_service_data(self, profile, main_category=None, current_subcategory=None):
        """Get vehicle-specific service data with category information"""
        data = {}

        # Get category data from work selection
        if hasattr(profile, 'work_selection') and profile.work_selection:
            work_selection = profile.work_selection

            # Use main_category from work_selection if not provided
            if not main_category and work_selection.main_category:
                main_category = work_selection.main_category

            # Get all subcategories
            subcategories = work_selection.selected_subcategories.all()

            data.update({
                'main_category_id': main_category.category_code if main_category else None,
                'main_category_name': main_category.display_name if main_category else None,
                'sub_category_ids': [sub.sub_category.subcategory_code for sub in subcategories],
                'sub_category_names': [sub.sub_category.display_name for sub in subcategories],
                'years_experience': work_selection.years_experience,
                'skills': [sub.sub_category.display_name for sub in subcategories] if subcategories else None
            })

        # Get vehicle-specific data
        if hasattr(profile, 'vehicle_service') and profile.vehicle_service:
            vehicle_data = profile.vehicle_service
            data.update({
                'license_number': vehicle_data.license_number,
                'vehicle_registration_number': vehicle_data.vehicle_registration_number,
                'description': vehicle_data.driving_experience_description,  # Use 'description' for consistency
                'service_offering_types': vehicle_data.service_offering_types.split(',') if vehicle_data.service_offering_types else []
            })

        return data if data else None

    def get_property_service_data(self, profile, main_category=None, current_subcategory=None):
        """Get property-specific service data with category information"""
        data = {}

        # Get category data from work selection
        if hasattr(profile, 'work_selection') and profile.work_selection:
            work_selection = profile.work_selection

            # Use main_category from work_selection if not provided
            if not main_category and work_selection.main_category:
                main_category = work_selection.main_category

            # Get all subcategories
            subcategories = work_selection.selected_subcategories.all()

            data.update({
                'main_category_id': main_category.category_code if main_category else None,
                'main_category_name': main_category.display_name if main_category else None,
                'sub_category_ids': [sub.sub_category.subcategory_code for sub in subcategories],
                'sub_category_names': [sub.sub_category.display_name for sub in subcategories]
            })

        # Get property-specific data
        if hasattr(profile, 'property_service') and profile.property_service:
            property_data = profile.property_service
            data.update({
                'property_title': property_data.property_title,
                'parking_availability': property_data.parking_availability,
                'furnishing_type': property_data.furnishing_type,
                'description': property_data.property_description,  # Use 'description' for consistency
                'service_offering_types': property_data.service_offering_types.split(',') if property_data.service_offering_types else []
            })

        return data if data else None

    def get_sos_service_data(self, profile, main_category=None, current_subcategory=None):
        """Get SOS/Emergency-specific service data with category information"""
        data = {}

        # Get category data from work selection
        if hasattr(profile, 'work_selection') and profile.work_selection:
            work_selection = profile.work_selection

            # Use main_category from work_selection if not provided
            if not main_category and work_selection.main_category:
                main_category = work_selection.main_category

            # Get all subcategories
            subcategories = work_selection.selected_subcategories.all()

            data.update({
                'main_category_id': main_category.category_code if main_category else None,
                'main_category_name': main_category.display_name if main_category else None,
                'sub_category_ids': [sub.sub_category.subcategory_code for sub in subcategories],
                'sub_category_names': [sub.sub_category.display_name for sub in subcategories]
            })

        # Get SOS-specific data
        if hasattr(profile, 'sos_service') and profile.sos_service:
            sos_data = profile.sos_service
            data.update({
                'contact_number': sos_data.contact_number,
                'location': sos_data.current_location,  # Use 'location' for consistency
                'description': sos_data.emergency_description  # Use 'description' for consistency
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

    # REMOVED: Auto-offline on disconnect
    # Provider status is now only controlled via API calls (/api/1/location/provider/toggle-status/)
    # @database_sync_to_async
    # def set_provider_offline_on_disconnect(self):
    #     """Set provider status to offline when WebSocket disconnects"""
    #     # This method has been disabled - providers stay active until they explicitly go offline via API

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
                        nearby_providers.append(provider_data)

            return sorted(nearby_providers, key=lambda x: x['distance_km'])
        except (WorkCategory.DoesNotExist, WorkSubCategory.DoesNotExist):
            return []