import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from apps.core.models import ProviderActiveStatus, SeekerSearchPreference, calculate_distance
from apps.profiles.models import UserProfile
from apps.work_categories.models import WorkCategory


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

        if active:
            # Notify seekers in the same category who are currently searching
            await self.notify_nearby_seekers_about_new_provider(category_name)
        else:
            # Notify seekers that this provider went offline
            await self.notify_seekers_about_provider_offline(category_name)

    async def handle_seeker_search_update(self, data):
        """Handle seeker starting/stopping search"""
        if self.user_type != 'seeker':
            return

        searching = data.get('searching', False)
        category_name = data.get('category', '')

        if searching:
            # Send current nearby providers
            nearby_providers = await self.get_nearby_providers(
                data.get('latitude'),
                data.get('longitude'),
                data.get('distance_radius', 5),
                category_name
            )

            await self.send(text_data=json.dumps({
                'type': 'nearby_providers',
                'providers': nearby_providers
            }))

    async def notify_nearby_seekers_about_new_provider(self, category_name):
        """Notify seekers when a new provider comes online"""
        provider_status = await self.get_provider_status(self.user.id)

        if not provider_status:
            return

        # Get all seekers currently searching in this category
        searching_seekers = await self.get_searching_seekers(category_name)

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
                            'subcategory': provider_status['subcategory'],
                            'distance_km': round(distance, 2),
                            'location': {
                                'latitude': provider_status['latitude'],
                                'longitude': provider_status['longitude']
                            }
                        }
                    }
                )

    async def notify_seekers_about_provider_offline(self, category_name):
        """Notify seekers when a provider goes offline"""
        provider_status = await self.get_provider_status(self.user.id)

        if not provider_status:
            return

        searching_seekers = await self.get_searching_seekers(category_name)

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
    def get_searching_seekers(self, category_name):
        """Get all seekers currently searching in the given category"""
        try:
            category = WorkCategory.objects.get(name=category_name, is_active=True)
            seekers = SeekerSearchPreference.objects.filter(
                searching_category=category,
                is_searching=True
            ).select_related('user')

            return [{
                'user_id': seeker.user_id,
                'latitude': seeker.latitude,
                'longitude': seeker.longitude,
                'distance_radius': seeker.distance_radius
            } for seeker in seekers]
        except WorkCategory.DoesNotExist:
            return []

    @database_sync_to_async
    def get_nearby_providers(self, seeker_lat, seeker_lng, radius, category_name):
        """Get nearby active providers for a seeker"""
        try:
            category = WorkCategory.objects.get(name=category_name, is_active=True)
            providers = ProviderActiveStatus.objects.filter(
                is_active=True,
                main_category=category,
                latitude__isnull=False,
                longitude__isnull=False
            ).select_related('user__profile', 'sub_category')

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
                        'subcategory': provider.sub_category.display_name,
                        'distance_km': round(distance, 2),
                        'location': {
                            'latitude': provider.latitude,
                            'longitude': provider.longitude
                        }
                    })

            return sorted(nearby_providers, key=lambda x: x['distance_km'])
        except WorkCategory.DoesNotExist:
            return []