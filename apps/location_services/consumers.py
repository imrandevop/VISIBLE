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
                # Notify this seeker about the new provider
                await self.channel_layer.group_send(
                    f'user_{seeker["user_id"]}_seeker',
                    {
                        'type': 'new_provider_available',
                        'provider': {
                            'provider_id': provider_status['provider_id'],
                            'name': provider_status['name'],
                            'rating': provider_status.get('rating', 0),
                            'description': provider_status.get('description', ''),
                            'is_verified': provider_status.get('is_verified', False),
                            'images': provider_status.get('images', []),
                            'main_category': {
                                'code': provider_status['main_category_code'],
                                'name': provider_status['main_category_name']
                            },
                            'subcategory': {
                                'code': seeker['searching_subcategory_code'],
                                'name': seeker['searching_subcategory_name']
                            },
                            'all_subcategories': provider_status['all_subcategories'],
                            'distance_km': round(distance, 2),
                            'location': {
                                'latitude': provider_status['latitude'],
                                'longitude': provider_status['longitude']
                            }
                        }
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
        """Get enhanced provider status details with all subcategories and complete profile info"""
        try:
            provider_status = ProviderActiveStatus.objects.select_related(
                'user__profile', 'sub_category', 'main_category'
            ).get(user_id=user_id, is_active=True)

            # Get all subcategories this provider offers
            provider_subcategories = UserWorkSubCategory.objects.filter(
                user_work_selection__user__user__id=user_id,
                user_work_selection__main_category=provider_status.main_category
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

            # Get portfolio images from both sources
            portfolio_images = []
            try:
                from django.conf import settings

                # Determine base URL for images
                if hasattr(settings, 'ALLOWED_HOSTS') and settings.ALLOWED_HOSTS:
                    # Use the first production domain, fallback to localhost
                    production_hosts = [host for host in settings.ALLOWED_HOSTS if host not in ['localhost', '127.0.0.1']]
                    base_domain = production_hosts[0] if production_hosts else 'localhost:8000'
                else:
                    base_domain = 'localhost:8000'

                base_url = f"https://{base_domain}" if base_domain != 'localhost:8000' else f"http://{base_domain}"

                # Try work-specific portfolio images first
                if hasattr(provider_status.user, 'profile') and hasattr(provider_status.user.profile, 'work_selection'):
                    work_selection = provider_status.user.profile.work_selection
                    if work_selection:
                        work_portfolio_images = [
                            f"{base_url}{img.image.url}" for img in work_selection.portfolio_images.all()
                        ]
                        portfolio_images.extend(work_portfolio_images)

                # Also get general service portfolio images
                if hasattr(provider_status.user, 'profile'):
                    service_portfolio_images = [
                        f"{base_url}{img.image.url}" for img in provider_status.user.profile.service_portfolio_images.all()
                    ]
                    portfolio_images.extend(service_portfolio_images)

            except Exception as e:
                logger.warning(f"Error getting portfolio images for provider {user_id}: {str(e)}")
                portfolio_images = []

            # Get description from skills or other available fields
            description = ""
            try:
                if hasattr(provider_status.user, 'profile') and hasattr(provider_status.user.profile, 'work_selection'):
                    work_selection = provider_status.user.profile.work_selection
                    if work_selection and work_selection.skills:
                        description = work_selection.skills
            except Exception as e:
                logger.warning(f"Error getting description for provider {user_id}: {str(e)}")
                description = ""

            return {
                'provider_id': provider_status.user.profile.provider_id,
                'name': provider_status.user.profile.full_name,
                'rating': 0,  # Default rating as requested
                'description': description,  # From UserWorkSelection.skills
                'is_verified': False,  # Default false as requested
                'images': portfolio_images,  # Portfolio images array from both sources
                'main_category_code': provider_status.main_category.category_code,
                'main_category_name': provider_status.main_category.name,
                'subcategory': provider_status.sub_category.display_name,
                'all_subcategories': all_subcategories,
                'latitude': provider_status.latitude,
                'longitude': provider_status.longitude
            }
        except ProviderActiveStatus.DoesNotExist:
            return None

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
        """Get nearby active providers with enhanced information including portfolio images"""
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
            ).select_related('user__profile').prefetch_related('user__profile__work_selection__portfolio_images')

            nearby_providers = []
            for provider in providers:
                distance = calculate_distance(
                    seeker_lat, seeker_lng,
                    provider.latitude, provider.longitude
                )

                if distance <= radius:
                    # Get portfolio images safely
                    portfolio_images = []
                    try:
                        if hasattr(provider.user, 'profile') and hasattr(provider.user.profile, 'work_selection'):
                            work_selection = provider.user.profile.work_selection
                            if work_selection:
                                portfolio_images = [
                                    img.image.url for img in work_selection.portfolio_images.all()
                                ]
                    except Exception as e:
                        logger.warning(f"Error getting portfolio images for provider {provider.user.id}: {str(e)}")
                        portfolio_images = []

                    nearby_providers.append({
                        'provider_id': provider.user.profile.provider_id,
                        'name': provider.user.profile.full_name,
                        'rating': 0,  # Default rating as requested
                        'description': provider.user.profile.bio or "",  # From UserProfile.bio
                        'is_verified': False,  # Default false as requested
                        'images': portfolio_images,  # Portfolio images array
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