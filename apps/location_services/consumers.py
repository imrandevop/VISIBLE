import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from apps.core.models import ProviderActiveStatus, SeekerSearchPreference, calculate_distance
from apps.profiles.models import UserProfile
from apps.work_categories.models import WorkCategory, WorkSubCategory, UserWorkSubCategory


class LocationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user_type = self.scope['url_route']['kwargs']['user_type']
        self.user = self.scope["user"]

        if isinstance(self.user, AnonymousUser):
            await self.close()
            return

        # Create user-specific group
        self.user_group_name = f'user_{self.user.id}_{self.user_type}'

        # Join user group
        await self.channel_layer.group_add(
            self.user_group_name,
            self.channel_name
        )

        # If provider, join category-based groups when they go active
        # If seeker, join search groups when they start searching

        await self.accept()

    async def disconnect(self, close_code):
        # Leave user group
        await self.channel_layer.group_discard(
            self.user_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        try:
            text_data_json = json.loads(text_data)
            message_type = text_data_json.get('type')

            if message_type == 'provider_status_update':
                await self.handle_provider_status_update(text_data_json)
            elif message_type == 'seeker_search_update':
                await self.handle_seeker_search_update(text_data_json)

        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'error': 'Invalid JSON'
            }))

    async def handle_provider_status_update(self, data):
        """Handle provider going active/inactive"""
        if self.user_type != 'provider':
            return

        active = data.get('active', False)
        category_name = data.get('category', '')
        category_code = data.get('category_code', '')

        if active:
            # Notify seekers in the same category who are currently searching
            await self.notify_nearby_seekers_about_new_provider(category_name, category_code)
        else:
            # Notify seekers that this provider went offline
            await self.notify_seekers_about_provider_offline(category_name, category_code)

    async def handle_seeker_search_update(self, data):
        """Handle seeker starting/stopping search"""
        if self.user_type != 'seeker':
            return

        searching = data.get('searching', False)
        category_name = data.get('category', '')
        category_code = data.get('category_code', '')
        subcategory_name = data.get('subcategory', '')
        subcategory_code = data.get('subcategory_code', '')

        if searching:
            # Send current nearby providers
            nearby_providers = await self.get_nearby_providers(
                data.get('latitude'),
                data.get('longitude'),
                data.get('distance_radius', 5),
                category_name,
                category_code,
                subcategory_name,
                subcategory_code
            )

            await self.send(text_data=json.dumps({
                'type': 'nearby_providers',
                'providers': nearby_providers
            }))

    async def notify_nearby_seekers_about_new_provider(self, category_name, category_code=None):
        """Notify seekers when a new provider comes online"""
        provider_status = await self.get_provider_status(self.user.id)

        if not provider_status:
            return

        # Get all seekers currently searching in this category
        searching_seekers = await self.get_searching_seekers_by_provider(self.user.id, category_name, category_code)

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
                            'subcategory': {
                                'code': seeker['searching_subcategory_code'],
                                'name': seeker['searching_subcategory_name']
                            },
                            'distance_km': round(distance, 2),
                            'location': {
                                'latitude': provider_status['latitude'],
                                'longitude': provider_status['longitude']
                            }
                        }
                    }
                )

    async def notify_seekers_about_provider_offline(self, category_name, category_code=None):
        """Notify seekers when a provider goes offline"""
        provider_status = await self.get_provider_status(self.user.id)

        if not provider_status:
            return

        searching_seekers = await self.get_searching_seekers_by_provider(self.user.id, category_name, category_code)

        for seeker in searching_seekers:
            await self.channel_layer.group_send(
                f'user_{seeker["user_id"]}_seeker',
                {
                    'type': 'provider_went_offline',
                    'provider_id': provider_status['provider_id']
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
            'provider_id': event['provider_id']
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
    def get_searching_seekers_by_provider(self, provider_user_id, category_name=None, category_code=None):
        """Get all seekers searching for subcategories that this provider has"""
        try:
            # Use code if provided, otherwise fallback to name
            if category_code:
                category = WorkCategory.objects.get(category_code=category_code, is_active=True)
            else:
                category = WorkCategory.objects.get(name=category_name, is_active=True)

            # Get provider's subcategories
            provider_subcategories = UserWorkSubCategory.objects.filter(
                user_work_selection__user__user_id=provider_user_id,
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
    def get_nearby_providers(self, seeker_lat, seeker_lng, radius, category_name=None, subcategory_name=None, category_id=None, subcategory_id=None):
        """Get nearby active providers for a seeker's specific subcategory"""
        try:
            # Use IDs if provided, otherwise fallback to names
            if category_id and subcategory_id:
                category = WorkCategory.objects.get(id=category_id, is_active=True)
                subcategory = WorkSubCategory.objects.get(
                    id=subcategory_id,
                    category=category,
                    is_active=True
                )
            else:
                category = WorkCategory.objects.get(name=category_name, is_active=True)
                subcategory = WorkSubCategory.objects.get(
                    name=subcategory_name,
                    category=category,
                    is_active=True
                )

            # Get providers who are active and have this subcategory in their skills
            # First get user IDs who have this subcategory skill
            user_ids_with_subcategory = UserWorkSubCategory.objects.filter(
                sub_category=subcategory,
                user_work_selection__main_category=category
            ).values_list('user_work_selection__user__user_id', flat=True)

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