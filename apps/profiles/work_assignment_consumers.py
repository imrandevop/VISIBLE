# apps/profiles/work_assignment_consumers.py
"""
WebSocket Connection URLs:


Production:
- Provider: wss://api.visibleapp.in/ws/work/provider/
- Seeker: wss://api.visibleapp.in/ws/work/seeker/
"""
import json
import asyncio
from decimal import Decimal
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from apps.core.models import calculate_distance
import logging

logger = logging.getLogger(__name__)

class ProviderWorkConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for providers to receive work assignments and send responses"""

    async def connect(self):
        """Called when WebSocket connection is established"""
        self.user = self.scope['user']
        self.distance_update_task = None  # For periodic distance updates
        self.current_session_id = None  # Track current session

        if not self.user.is_authenticated:
            logger.warning("Unauthenticated user attempted WebSocket connection")
            await self.close()
            return

        # Verify user is a provider
        is_provider = await self.check_user_is_provider()
        if not is_provider:
            logger.warning(f"Non-provider user {self.user.mobile_number} attempted provider WebSocket connection")
            await self.close()
            return

        # Create group name for this provider
        self.provider_id = self.user.id
        self.group_name = f'provider_{self.provider_id}'

        # Join provider group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()
        logger.info(f"✅ Provider {self.user.mobile_number} connected to WebSocket")

        # Send connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected successfully',
            'provider_id': self.provider_id,
            'timestamp': timezone.now().isoformat()
        }))

        # Load and send chat history if there's an active session
        chat_history = await self.get_chat_history_for_provider(self.provider_id)
        if chat_history:
            await self.send(text_data=json.dumps({
                'type': 'chat_history_loaded',
                'session_id': chat_history['session_id'],
                'messages': chat_history['messages'],
                'message_count': len(chat_history['messages']),
                'timestamp': timezone.now().isoformat()
            }))
            logger.info(f"📜 Loaded {len(chat_history['messages'])} chat messages for provider {self.user.mobile_number}")

    async def disconnect(self, close_code):
        """Called when WebSocket connection is closed"""
        # Cancel distance update task if running
        if self.distance_update_task and not self.distance_update_task.done():
            self.distance_update_task.cancel()

        # Leave provider group
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
        logger.info(f"❌ Provider {self.user.mobile_number} disconnected from WebSocket (code: {close_code})")

    async def receive(self, text_data):
        """Called when message is received from WebSocket"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'ping':
                # Heartbeat response
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': timezone.now().isoformat()
                }))

            elif message_type == 'work_response':
                # Provider accepted or rejected work
                await self.handle_work_response(data)

            elif message_type == 'location_update':
                # Provider sending location update
                await self.handle_location_update(data)

            elif message_type == 'medium_share':
                # Provider sharing their communication mediums
                await self.handle_provider_medium_share(data)

            elif message_type == 'start_chat':
                # Provider starting chat
                await self.handle_start_chat(data)

            elif message_type == 'chat_message':
                # Provider sending chat message
                await self.handle_chat_message(data)

            elif message_type == 'message_delivered':
                # Provider acknowledging message delivery
                await self.handle_message_delivered(data)

            elif message_type == 'message_read':
                # Provider marking message as read
                await self.handle_message_read(data)

            elif message_type == 'typing_indicator':
                # Provider typing status
                await self.handle_typing_indicator(data)

            elif message_type == 'cancel_connection':
                # Provider cancelling connection
                await self.handle_cancel_connection(data)

            elif message_type == 'finish_service':
                # Provider marking service as finished
                await self.handle_finish_service(data)

            else:
                logger.warning(f"Unknown message type received: {message_type}")
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': f'Unknown message type: {message_type}'
                }))

        except json.JSONDecodeError:
            logger.error("Invalid JSON received from WebSocket")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Invalid JSON format'
            }))
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Internal server error'
            }))

    async def handle_work_response(self, data):
        """Handle provider's response to work assignment"""
        try:
            work_id = data.get('work_id')
            accepted = data.get('accepted', False)

            if not work_id:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'work_id is required'
                }))
                return

            logger.info(f"📥 Provider {self.user.mobile_number} {'accepted' if accepted else 'rejected'} work #{work_id}")

            if accepted:
                # Create work session and disable search statuses
                session_data = await self.create_work_session(work_id)

                if not session_data:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'error': 'Failed to create work session'
                    }))
                    return

                # Store current session ID
                self.current_session_id = session_data['session_id']

                # Disable provider active status
                await self.disable_provider_active_status()

                # Start distance update task
                self.distance_update_task = asyncio.create_task(
                    self.periodic_distance_update(session_data['session_id'])
                )

                # Get both users' available communication mediums
                provider_mediums = await self.get_user_communication_mediums(self.user.id)
                seeker_mediums = await self.get_user_communication_mediums(session_data['seeker_id'])

                # Send confirmation to provider
                await self.send(text_data=json.dumps({
                    'type': 'work_accepted',
                    'work_id': work_id,
                    'session_id': session_data['session_id'],
                    'connection_state': 'active',
                    'message': 'Work accepted. Session is now active.',
                    'provider_available_mediums': provider_mediums,
                    'seeker_available_mediums': seeker_mediums,
                    'timestamp': timezone.now().isoformat()
                }))

                # Notify seeker of acceptance
                await self.notify_seeker_of_acceptance(work_id, session_data)

            else:
                # Update work order status to rejected
                success = await self.update_work_order_status(work_id, accepted)

                if success:
                    await self.send(text_data=json.dumps({
                        'type': 'work_rejected',
                        'work_id': work_id,
                        'message': 'Work rejected successfully',
                        'timestamp': timezone.now().isoformat()
                    }))

                    # Notify seeker of rejection
                    await self.notify_seeker_of_response(work_id, accepted)
                else:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'error': 'Failed to update work order. Order may not exist or already processed.'
                    }))

        except Exception as e:
            logger.error(f"Error handling work response: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Failed to process work response'
            }))

    async def handle_location_update(self, data):
        """Handle provider location update"""
        try:
            session_id = data.get('session_id')
            latitude = data.get('latitude')
            longitude = data.get('longitude')

            if not all([session_id, latitude, longitude]):
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'session_id, latitude, and longitude are required'
                }))
                return

            # Update provider location in session
            distance_data = await self.update_provider_location(session_id, latitude, longitude)

            if distance_data:
                # Send distance update to both users
                await self.send_distance_update_to_session(session_id, distance_data)

        except Exception as e:
            logger.error(f"Error handling location update: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Failed to update location'
            }))

    async def handle_provider_medium_share(self, data):
        """Handle provider sharing their communication mediums"""
        try:
            session_id = data.get('session_id')
            mediums = data.get('mediums', {})  # Full communication mediums with enabled status and values

            if not session_id:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'session_id is required'
                }))
                return

            # Validate mediums - now supports all 7 medium types
            valid_types = {'telegram', 'whatsapp', 'call', 'map_location', 'website', 'instagram', 'facebook'}
            if not all(k in valid_types for k in mediums.keys()):
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'Invalid medium types. Allowed: telegram, whatsapp, call, map_location, website, instagram, facebook'
                }))
                return

            # Update provider mediums in session
            success = await self.update_provider_mediums(session_id, mediums)

            if success:
                # Send confirmation to provider
                await self.send(text_data=json.dumps({
                    'type': 'mediums_shared',
                    'session_id': session_id,
                    'mediums': mediums,
                    'timestamp': timezone.now().isoformat()
                }))

                # Notify seeker about provider's mediums
                await self.notify_seeker_provider_mediums(session_id, mediums)

        except Exception as e:
            logger.error(f"Error handling provider medium share: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Failed to share mediums'
            }))

    async def handle_start_chat(self, data):
        """Handle provider starting chat"""
        try:
            session_id = data.get('session_id')

            if not session_id:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'session_id is required'
                }))
                return

            # Start chat in session
            chat_room_id = await self.start_chat_session(session_id)

            if chat_room_id:
                # Send chat_ready to both provider and seeker
                await self.send(text_data=json.dumps({
                    'type': 'chat_ready',
                    'session_id': session_id,
                    'chat_room_id': chat_room_id,
                    'message': 'Chat started successfully',
                    'timestamp': timezone.now().isoformat()
                }))

                # Notify seeker
                await self.notify_seeker_chat_ready(session_id, chat_room_id)

        except Exception as e:
            logger.error(f"Error handling start chat: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Failed to start chat'
            }))

    async def handle_chat_message(self, data):
        """Handle provider sending chat message"""
        try:
            session_id = data.get('session_id')
            message_text = data.get('message')

            if not all([session_id, message_text]):
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'session_id and message are required'
                }))
                return

            # Save message and send to seeker
            message_data = await self.save_chat_message(session_id, self.user.id, 'provider', message_text)

            if message_data:
                # Send to seeker
                await self.send_chat_message_to_seeker(session_id, message_data)

                # Send confirmation to provider
                await self.send(text_data=json.dumps({
                    'type': 'message_sent',
                    'message_id': message_data['message_id'],
                    'session_id': session_id,
                    'timestamp': timezone.now().isoformat()
                }))

        except Exception as e:
            logger.error(f"Error handling chat message: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Failed to send message'
            }))

    async def handle_message_delivered(self, data):
        """Handle provider acknowledging message delivery"""
        try:
            message_id = data.get('message_id')

            if not message_id:
                return

            # Update message delivery status
            await self.update_message_status(message_id, 'delivered')

            # Notify sender (seeker)
            await self.notify_message_status_update(message_id, 'delivered')

        except Exception as e:
            logger.error(f"Error handling message delivered: {e}")

    async def handle_message_read(self, data):
        """Handle provider marking message as read"""
        try:
            message_id = data.get('message_id')

            if not message_id:
                return

            # Update message read status
            await self.update_message_status(message_id, 'read')

            # Notify sender (seeker)
            await self.notify_message_status_update(message_id, 'read')

        except Exception as e:
            logger.error(f"Error handling message read: {e}")

    async def handle_typing_indicator(self, data):
        """Handle provider typing indicator"""
        try:
            session_id = data.get('session_id')
            is_typing = data.get('is_typing', False)

            if not session_id:
                return

            # Update typing status
            await self.update_typing_status(session_id, self.user.id, 'provider', is_typing)

            # Notify seeker
            await self.notify_typing_status(session_id, 'provider', is_typing)

        except Exception as e:
            logger.error(f"Error handling typing indicator: {e}")

    async def handle_cancel_connection(self, data):
        """Handle provider cancelling connection"""
        try:
            session_id = data.get('session_id')

            if not session_id:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'session_id is required'
                }))
                return

            # Cancel session and update work order
            success = await self.cancel_session(session_id, self.user.id)

            if success:
                # Stop distance updates
                if self.distance_update_task and not self.distance_update_task.done():
                    self.distance_update_task.cancel()

                # Re-enable provider active status
                await self.enable_provider_active_status()

                # Send confirmation to provider
                await self.send(text_data=json.dumps({
                    'type': 'connection_cancelled',
                    'session_id': session_id,
                    'message': 'Connection cancelled successfully',
                    'timestamp': timezone.now().isoformat()
                }))

                # Notify seeker
                await self.notify_connection_cancelled(session_id)

                # Close connection
                await self.close()

        except Exception as e:
            logger.error(f"Error handling cancel connection: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Failed to cancel connection'
            }))

    async def handle_finish_service(self, data):
        """Handle provider marking service as finished"""
        try:
            session_id = data.get('session_id')

            if not session_id:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'session_id is required'
                }))
                return

            # Complete session (provider cannot provide rating)
            success = await self.complete_session(session_id, self.user.id, rating_stars=None, rating_description=None)

            if success:
                # Stop distance updates
                if self.distance_update_task and not self.distance_update_task.done():
                    self.distance_update_task.cancel()

                # Send confirmation to provider
                await self.send(text_data=json.dumps({
                    'type': 'service_finished',
                    'session_id': session_id,
                    'message': 'Service marked as finished successfully',
                    'timestamp': timezone.now().isoformat()
                }))

                # Notify seeker
                await self.notify_service_finished(session_id, 'provider')

                # Close connection
                await self.close()

        except Exception as e:
            logger.error(f"Error handling finish service: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Failed to finish service'
            }))

    # Channel layer message handlers
    async def work_assignment(self, event):
        """
        Called when work is assigned to this provider
        This is triggered by channel_layer.group_send()
        """
        try:
            # Send work assignment to provider
            await self.send(text_data=json.dumps({
                'type': 'work_assigned',
                'work_id': event['work_id'],
                'seeker_name': event['seeker_name'],
                'seeker_mobile': event.get('seeker_mobile', ''),
                'service_type': event['service_type'],
                'distance': event.get('distance', ''),
                'message': event.get('message', ''),
                'seeker_profile_pic': event.get('seeker_profile_pic', ''),
                'created_at': event.get('created_at', ''),
                'timestamp': timezone.now().isoformat()
            }))
            logger.info(f"📤 Sent work assignment #{event['work_id']} to provider {self.user.mobile_number}")

            # Log WebSocket notification
            await self.log_websocket_notification(event['work_id'], 'work_assigned', 'sent')

        except Exception as e:
            logger.error(f"Error sending work assignment via WebSocket: {e}")

    async def medium_selection_update(self, event):
        """Notify provider about seeker's medium selection"""
        await self.send(text_data=json.dumps({
            'type': 'seeker_mediums_selected',
            'session_id': event['session_id'],
            'mediums': event['mediums'],
            'message': 'Seeker has selected communication mediums',
            'timestamp': timezone.now().isoformat()
        }))

    async def distance_update_event(self, event):
        """Send distance update to provider"""
        await self.send(text_data=json.dumps({
            'type': 'distance_update',
            'session_id': event['session_id'],
            'distance_meters': event['distance_meters'],
            'distance_formatted': event['distance_formatted'],
            'timestamp': timezone.now().isoformat()
        }))

    async def chat_ready_event(self, event):
        """Notify provider that chat is ready"""
        await self.send(text_data=json.dumps({
            'type': 'chat_ready',
            'session_id': event['session_id'],
            'chat_room_id': event['chat_room_id'],
            'message': 'Seeker started chat',
            'timestamp': timezone.now().isoformat()
        }))

    async def chat_message_event(self, event):
        """Send chat message to provider"""
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message_id': event['message_id'],
            'session_id': event['session_id'],
            'sender_type': event['sender_type'],
            'message': event['message'],
            'timestamp': event['timestamp']
        }))

    async def message_status_update(self, event):
        """Notify provider about message status update"""
        await self.send(text_data=json.dumps({
            'type': 'message_status_update',
            'message_id': event['message_id'],
            'status': event['status'],
            'timestamp': timezone.now().isoformat()
        }))

    async def typing_status_event(self, event):
        """Notify provider about seeker typing status"""
        await self.send(text_data=json.dumps({
            'type': 'typing_indicator',
            'session_id': event['session_id'],
            'user_type': event['user_type'],
            'is_typing': event['is_typing'],
            'timestamp': timezone.now().isoformat()
        }))

    async def connection_cancelled_event(self, event):
        """Notify provider that seeker cancelled connection"""
        await self.send(text_data=json.dumps({
            'type': 'connection_cancelled',
            'session_id': event['session_id'],
            'cancelled_by': 'seeker',
            'message': 'Seeker cancelled the connection',
            'timestamp': timezone.now().isoformat()
        }))

        # Re-enable provider active status
        await self.enable_provider_active_status()

        # Close connection
        await self.close()

    async def provider_mediums_update(self, event):
        """Notify provider about their own mediums being shared (confirmation)"""
        pass  # Already handled in handle_provider_medium_share

    async def service_finished_event(self, event):
        """Notify provider that seeker marked service as finished"""
        await self.send(text_data=json.dumps({
            'type': 'service_finished',
            'session_id': event['session_id'],
            'finished_by': 'seeker',
            'message': 'Seeker marked the service as finished',
            'timestamp': timezone.now().isoformat()
        }))

        # Close connection
        await self.close()

    # Background task for periodic distance updates
    async def periodic_distance_update(self, session_id):
        """Send distance updates every 30 seconds"""
        try:
            while True:
                await asyncio.sleep(30)  # Wait 30 seconds

                # Calculate and send distance update
                distance_data = await self.calculate_session_distance(session_id)

                if distance_data:
                    await self.send_distance_update_to_session(session_id, distance_data)

        except asyncio.CancelledError:
            logger.info(f"Distance update task cancelled for session {session_id}")
        except Exception as e:
            logger.error(f"Error in periodic distance update: {e}")

    # Database helper methods
    @database_sync_to_async
    def check_user_is_provider(self):
        """Check if user is a provider"""
        try:
            profile = self.user.profile
            return profile.user_type == 'provider'
        except:
            return False

    @database_sync_to_async
    def get_user_communication_mediums(self, user_id):
        """Get user's available communication mediums"""
        from apps.profiles.models import UserProfile
        from apps.profiles.communication_models import CommunicationSettings

        try:
            user_profile = UserProfile.objects.get(user_id=user_id)

            try:
                communication_settings = CommunicationSettings.objects.get(user_profile=user_profile)

                # Build the communication mediums dict with only enabled mediums
                mediums = {}

                if communication_settings.telegram_enabled:
                    mediums['telegram'] = {
                        "enabled": True,
                        "value": communication_settings.telegram_value or ""
                    }

                if communication_settings.whatsapp_enabled:
                    mediums['whatsapp'] = {
                        "enabled": True,
                        "value": communication_settings.whatsapp_value or ""
                    }

                if communication_settings.call_enabled:
                    mediums['call'] = {
                        "enabled": True,
                        "value": communication_settings.call_value or ""
                    }

                if communication_settings.map_location_enabled:
                    mediums['map_location'] = {
                        "enabled": True,
                        "value": communication_settings.map_location_value or ""
                    }

                if communication_settings.website_enabled:
                    mediums['website'] = {
                        "enabled": True,
                        "value": communication_settings.website_value or ""
                    }

                if communication_settings.instagram_enabled:
                    mediums['instagram'] = {
                        "enabled": True,
                        "value": communication_settings.instagram_value or ""
                    }

                if communication_settings.facebook_enabled:
                    mediums['facebook'] = {
                        "enabled": True,
                        "value": communication_settings.facebook_value or ""
                    }

                return mediums

            except CommunicationSettings.DoesNotExist:
                # No communication settings found, return empty dict
                return {}

        except UserProfile.DoesNotExist:
            logger.error(f"UserProfile not found for user_id {user_id}")
            return {}
        except Exception as e:
            logger.error(f"Error getting communication mediums for user {user_id}: {e}")
            return {}

    @database_sync_to_async
    def create_work_session(self, work_id):
        """Create work session when provider accepts work"""
        from .work_assignment_models import WorkOrder, WorkSession

        try:
            work_order = WorkOrder.objects.get(id=work_id, provider=self.user, status='pending')
            work_order.status = 'accepted'
            work_order.response_time = timezone.now()
            work_order.save()

            # Create session
            session = WorkSession.objects.create(
                work_order=work_order,
                connection_state='active',
                provider_latitude=work_order.provider_latitude,
                provider_longitude=work_order.provider_longitude,
                seeker_latitude=work_order.seeker_latitude,
                seeker_longitude=work_order.seeker_longitude,
                provider_last_location_update=timezone.now(),
                seeker_last_location_update=timezone.now()
            )

            # Set chat_room_id to session_id
            session.chat_room_id = session.session_id
            session.save()

            logger.info(f"✅ Work session created: {session.session_id}")
            return {
                'session_id': str(session.session_id),
                'work_id': work_id,
                'seeker_id': work_order.seeker.id
            }
        except WorkOrder.DoesNotExist:
            logger.error(f"❌ Work order #{work_id} not found or not in pending status")
            return None
        except Exception as e:
            logger.error(f"❌ Error creating work session: {e}")
            return None

    @database_sync_to_async
    def update_work_order_status(self, work_id, accepted):
        """Update work order status in database"""
        from .work_assignment_models import WorkOrder

        try:
            work_order = WorkOrder.objects.get(id=work_id, provider=self.user, status='pending')
            work_order.status = 'accepted' if accepted else 'rejected'
            work_order.response_time = timezone.now()
            work_order.save()

            logger.info(f"✅ Work order #{work_id} status updated to: {work_order.status}")
            return True
        except WorkOrder.DoesNotExist:
            logger.error(f"❌ Work order #{work_id} not found or not in pending status")
            return False
        except Exception as e:
            logger.error(f"❌ Error updating work order #{work_id}: {e}")
            return False

    @database_sync_to_async
    def disable_provider_active_status(self):
        """Disable provider active status when connected to a session"""
        from apps.core.models import ProviderActiveStatus

        try:
            provider_status = ProviderActiveStatus.objects.get(user=self.user)
            provider_status.is_active = False
            provider_status.save()
            logger.info(f"✅ Provider {self.user.mobile_number} active status disabled")
        except ProviderActiveStatus.DoesNotExist:
            logger.warning(f"⚠️ Provider {self.user.mobile_number} has no active status record")
        except Exception as e:
            logger.error(f"❌ Error disabling provider active status: {e}")

    @database_sync_to_async
    def enable_provider_active_status(self):
        """Re-enable provider active status after session ends"""
        from apps.core.models import ProviderActiveStatus

        try:
            provider_status = ProviderActiveStatus.objects.get(user=self.user)
            provider_status.is_active = True
            provider_status.save()
            logger.info(f"✅ Provider {self.user.mobile_number} active status re-enabled")
        except ProviderActiveStatus.DoesNotExist:
            logger.warning(f"⚠️ Provider {self.user.mobile_number} has no active status record")
        except Exception as e:
            logger.error(f"❌ Error enabling provider active status: {e}")

    @database_sync_to_async
    def update_provider_location(self, session_id, latitude, longitude):
        """Update provider location in session and calculate distance"""
        from .work_assignment_models import WorkSession

        try:
            session = WorkSession.objects.get(session_id=session_id)

            # Check if location changed significantly (>50 meters)
            old_lat = float(session.provider_latitude) if session.provider_latitude else None
            old_lng = float(session.provider_longitude) if session.provider_longitude else None

            if old_lat and old_lng:
                distance_change = calculate_distance(old_lat, old_lng, float(latitude), float(longitude)) * 1000  # Convert to meters

                # Only update if change is significant
                if distance_change < 50:
                    return None

            # Update location
            session.provider_latitude = Decimal(str(latitude))
            session.provider_longitude = Decimal(str(longitude))
            session.provider_last_location_update = timezone.now()

            # Calculate distance between seeker and provider
            if session.seeker_latitude and session.seeker_longitude:
                distance_km = calculate_distance(
                    float(session.seeker_latitude),
                    float(session.seeker_longitude),
                    float(latitude),
                    float(longitude)
                )
                session.current_distance_meters = distance_km * 1000
                session.last_distance_update = timezone.now()

            session.save()

            return {
                'distance_meters': session.current_distance_meters,
                'distance_formatted': session.get_formatted_distance()
            }

        except WorkSession.DoesNotExist:
            logger.error(f"Session {session_id} not found")
            return None
        except Exception as e:
            logger.error(f"Error updating provider location: {e}")
            return None

    @database_sync_to_async
    def update_provider_mediums(self, session_id, mediums):
        """Update provider communication mediums in session"""
        from .work_assignment_models import WorkSession

        try:
            session = WorkSession.objects.get(session_id=session_id)
            session.provider_selected_mediums = mediums
            session.save()

            logger.info(f"✅ Provider mediums updated for session {session_id}")
            return True
        except WorkSession.DoesNotExist:
            logger.error(f"Session {session_id} not found")
            return False
        except Exception as e:
            logger.error(f"Error updating provider mediums: {e}")
            return False

    @database_sync_to_async
    def start_chat_session(self, session_id):
        """Start chat in session"""
        from .work_assignment_models import WorkSession

        try:
            session = WorkSession.objects.get(session_id=session_id)

            if not session.chat_started_at:
                session.chat_started_at = timezone.now()
                session.save()

            return str(session.chat_room_id)
        except WorkSession.DoesNotExist:
            logger.error(f"Session {session_id} not found")
            return None
        except Exception as e:
            logger.error(f"Error starting chat: {e}")
            return None

    @database_sync_to_async
    def save_chat_message(self, session_id, sender_id, sender_type, message_text):
        """Save chat message to database"""
        from .work_assignment_models import WorkSession, ChatMessage

        try:
            session = WorkSession.objects.get(session_id=session_id)

            message = ChatMessage.objects.create(
                session=session,
                sender_id=sender_id,
                sender_type=sender_type,
                message_text=message_text,
                delivery_status='sent'
            )

            return {
                'message_id': str(message.message_id),
                'sender_type': sender_type,
                'message': message_text,
                'timestamp': message.created_at.isoformat()
            }
        except WorkSession.DoesNotExist:
            logger.error(f"Session {session_id} not found")
            return None
        except Exception as e:
            logger.error(f"Error saving chat message: {e}")
            return None

    @database_sync_to_async
    def update_message_status(self, message_id, status):
        """Update message delivery/read status"""
        from .work_assignment_models import ChatMessage

        try:
            message = ChatMessage.objects.get(message_id=message_id)
            message.delivery_status = status

            if status == 'delivered':
                message.delivered_at = timezone.now()
            elif status == 'read':
                message.read_at = timezone.now()

            message.save()
            return True
        except ChatMessage.DoesNotExist:
            logger.error(f"Message {message_id} not found")
            return False
        except Exception as e:
            logger.error(f"Error updating message status: {e}")
            return False

    @database_sync_to_async
    def get_chat_history_for_provider(self, provider_id):
        """Get chat history for provider's most recent active session"""
        from .work_assignment_models import WorkSession, ChatMessage

        try:
            # Get most recent active session for this provider
            session = WorkSession.objects.filter(
                work_order__provider_id=provider_id,
                connection_state='active'
            ).order_by('-created_at').first()

            if not session:
                return None

            # Get all messages for this session, ordered by creation time
            messages = ChatMessage.objects.filter(
                session=session
            ).order_by('created_at')

            # Serialize messages
            message_list = []
            for msg in messages:
                message_list.append({
                    'message_id': str(msg.message_id),
                    'sender_type': msg.sender_type,
                    'message': msg.message_text,
                    'delivery_status': msg.delivery_status,
                    'delivered_at': msg.delivered_at.isoformat() if msg.delivered_at else None,
                    'read_at': msg.read_at.isoformat() if msg.read_at else None,
                    'timestamp': msg.created_at.isoformat()
                })

            return {
                'session_id': str(session.session_id),
                'messages': message_list
            }

        except Exception as e:
            logger.error(f"Error getting chat history for provider: {e}")
            return None

    @database_sync_to_async
    def update_typing_status(self, session_id, user_id, user_type, is_typing):
        """Update typing indicator status"""
        from .work_assignment_models import WorkSession, TypingIndicator

        try:
            session = WorkSession.objects.get(session_id=session_id)

            indicator, created = TypingIndicator.objects.get_or_create(
                session=session,
                user_id=user_id,
                defaults={'user_type': user_type, 'is_typing': is_typing}
            )

            if not created:
                indicator.is_typing = is_typing
                indicator.save()

            return True
        except WorkSession.DoesNotExist:
            logger.error(f"Session {session_id} not found")
            return False
        except Exception as e:
            logger.error(f"Error updating typing status: {e}")
            return False

    @database_sync_to_async
    def cancel_session(self, session_id, cancelled_by_user_id):
        """Cancel work session"""
        from .work_assignment_models import WorkSession, WorkOrder, ChatMessage
        from datetime import timedelta

        try:
            session = WorkSession.objects.get(session_id=session_id)
            session.connection_state = 'cancelled'
            session.cancelled_by_id = cancelled_by_user_id
            session.cancelled_at = timezone.now()
            session.save()

            # Update work order status
            work_order = session.work_order
            work_order.status = 'cancelled'
            work_order.save()

            # Set expiry for chat messages (24 hours from now)
            expiry_time = timezone.now() + timedelta(hours=24)
            ChatMessage.objects.filter(session=session).update(expires_at=expiry_time)

            logger.info(f"✅ Session {session_id} cancelled")
            return True
        except WorkSession.DoesNotExist:
            logger.error(f"Session {session_id} not found")
            return False
        except Exception as e:
            logger.error(f"Error cancelling session: {e}")
            return False

    @database_sync_to_async
    def calculate_session_distance(self, session_id):
        """Calculate current distance between users in session"""
        from .work_assignment_models import WorkSession

        try:
            session = WorkSession.objects.get(session_id=session_id)

            if all([session.seeker_latitude, session.seeker_longitude,
                   session.provider_latitude, session.provider_longitude]):

                distance_km = calculate_distance(
                    float(session.seeker_latitude),
                    float(session.seeker_longitude),
                    float(session.provider_latitude),
                    float(session.provider_longitude)
                )

                session.current_distance_meters = distance_km * 1000
                session.last_distance_update = timezone.now()
                session.save()

                return {
                    'distance_meters': session.current_distance_meters,
                    'distance_formatted': session.get_formatted_distance()
                }

            return None
        except WorkSession.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Error calculating session distance: {e}")
            return None

    @database_sync_to_async
    def log_websocket_notification(self, work_id, notification_type, status):
        """Log WebSocket notification in database"""
        from .work_assignment_models import WorkOrder, WorkAssignmentNotification

        try:
            work_order = WorkOrder.objects.get(id=work_id)
            WorkAssignmentNotification.objects.create(
                work_order=work_order,
                recipient=self.user,
                notification_type=notification_type,
                delivery_method='websocket',
                delivery_status=status,
                sent_at=timezone.now()
            )
        except Exception as e:
            logger.error(f"Error logging WebSocket notification: {e}")

    @database_sync_to_async
    def complete_session(self, session_id, completed_by_user_id, rating_stars=None, rating_description=None):
        """Complete work session and optionally add rating"""
        from .work_assignment_models import WorkSession, WorkOrder, ChatMessage
        from datetime import timedelta

        try:
            session = WorkSession.objects.get(session_id=session_id)

            # Check if already completed
            if session.connection_state == 'completed':
                logger.warning(f"Session {session_id} already completed")
                return False

            session.connection_state = 'completed'
            session.completed_by_id = completed_by_user_id
            session.completed_at = timezone.now()

            # Add rating if provided (only from seeker)
            if rating_stars is not None:
                session.rating_stars = rating_stars
                session.rating_description = rating_description or ''
                session.rated_at = timezone.now()

            session.save()

            # Update work order status
            work_order = session.work_order
            work_order.status = 'completed'
            work_order.completion_time = timezone.now()
            work_order.save()

            # Set expiry for chat messages (24 hours from now)
            expiry_time = timezone.now() + timedelta(hours=24)
            ChatMessage.objects.filter(session=session).update(expires_at=expiry_time)

            logger.info(f"✅ Session {session_id} completed by user {completed_by_user_id}")
            return True
        except WorkSession.DoesNotExist:
            logger.error(f"Session {session_id} not found")
            return False
        except Exception as e:
            logger.error(f"Error completing session: {e}")
            return False

    @database_sync_to_async
    def get_work_order_data(self, work_id):
        """Get work order data for seeker notification"""
        from .work_assignment_models import WorkOrder

        try:
            work_order = WorkOrder.objects.select_related('seeker__profile', 'provider__profile').get(id=work_id)
            return {
                'seeker_id': work_order.seeker.id,
                'provider_name': work_order.provider_profile.full_name,
                'provider_mobile': work_order.provider.mobile_number,
                'service_type': work_order.service_type,
                'seeker_profile': work_order.seeker_profile
            }
        except WorkOrder.DoesNotExist:
            return None

    # Notification methods to other users
    async def notify_seeker_of_acceptance(self, work_id, session_data):
        """Send notification to seeker about provider acceptance"""
        try:
            seeker_group = f'seeker_{session_data["seeker_id"]}'

            # Get both users' available communication mediums
            provider_mediums = await self.get_user_communication_mediums(self.user.id)
            seeker_mediums = await self.get_user_communication_mediums(session_data['seeker_id'])

            await self.channel_layer.group_send(
                seeker_group,
                {
                    'type': 'work_accepted_event',
                    'work_id': work_id,
                    'session_id': session_data['session_id'],
                    'connection_state': 'active',
                    'message': 'Provider accepted your request. Session is now active.',
                    'provider_available_mediums': provider_mediums,
                    'seeker_available_mediums': seeker_mediums
                }
            )

            # Disable seeker search preference
            await self.disable_seeker_search_preference(session_data['seeker_id'])

        except Exception as e:
            logger.error(f"Error notifying seeker of acceptance: {e}")

    async def notify_seeker_of_response(self, work_id, accepted):
        """Send notification to seeker about provider's response"""
        try:
            # Get work order and seeker info
            work_order_data = await self.get_work_order_data(work_id)
            if not work_order_data:
                return

            seeker_id = work_order_data['seeker_id']
            seeker_group = f'seeker_{seeker_id}'

            # Send WebSocket message to seeker
            await self.channel_layer.group_send(
                seeker_group,
                {
                    'type': 'work_response_notification',
                    'work_id': work_id,
                    'accepted': accepted,
                    'provider_name': work_order_data['provider_name'],
                    'provider_mobile': work_order_data['provider_mobile'],
                    'service_type': work_order_data['service_type'],
                    'response_time': timezone.now().isoformat()
                }
            )

        except Exception as e:
            logger.error(f"Error notifying seeker of response: {e}")

    async def send_distance_update_to_session(self, session_id, distance_data):
        """Send distance update to both seeker and provider"""
        try:
            session_info = await self.get_session_users(session_id)

            if not session_info:
                return

            # Send to provider
            await self.channel_layer.group_send(
                f'provider_{session_info["provider_id"]}',
                {
                    'type': 'distance_update_event',
                    'session_id': session_id,
                    'distance_meters': distance_data['distance_meters'],
                    'distance_formatted': distance_data['distance_formatted']
                }
            )

            # Send to seeker
            await self.channel_layer.group_send(
                f'seeker_{session_info["seeker_id"]}',
                {
                    'type': 'distance_update_event',
                    'session_id': session_id,
                    'distance_meters': distance_data['distance_meters'],
                    'distance_formatted': distance_data['distance_formatted']
                }
            )

        except Exception as e:
            logger.error(f"Error sending distance update: {e}")

    async def notify_seeker_provider_mediums(self, session_id, mediums):
        """Notify seeker about provider's communication mediums"""
        try:
            session_info = await self.get_session_users(session_id)

            if not session_info:
                return

            await self.channel_layer.group_send(
                f'seeker_{session_info["seeker_id"]}',
                {
                    'type': 'provider_mediums_update',
                    'session_id': session_id,
                    'mediums': mediums
                }
            )

        except Exception as e:
            logger.error(f"Error notifying seeker of provider mediums: {e}")

    async def notify_seeker_chat_ready(self, session_id, chat_room_id):
        """Notify seeker that chat is ready"""
        try:
            session_info = await self.get_session_users(session_id)

            if not session_info:
                return

            await self.channel_layer.group_send(
                f'seeker_{session_info["seeker_id"]}',
                {
                    'type': 'chat_ready_event',
                    'session_id': session_id,
                    'chat_room_id': chat_room_id
                }
            )

        except Exception as e:
            logger.error(f"Error notifying seeker chat ready: {e}")

    async def send_chat_message_to_seeker(self, session_id, message_data):
        """Send chat message to seeker"""
        try:
            session_info = await self.get_session_users(session_id)

            if not session_info:
                return

            await self.channel_layer.group_send(
                f'seeker_{session_info["seeker_id"]}',
                {
                    'type': 'chat_message_event',
                    'session_id': session_id,
                    **message_data
                }
            )

        except Exception as e:
            logger.error(f"Error sending chat message to seeker: {e}")

    async def notify_message_status_update(self, message_id, status):
        """Notify message sender about status update"""
        try:
            sender_info = await self.get_message_sender(message_id)

            if not sender_info:
                return

            user_type = sender_info['sender_type']
            user_id = sender_info['sender_id']

            await self.channel_layer.group_send(
                f'{user_type}_{user_id}',
                {
                    'type': 'message_status_update',
                    'message_id': message_id,
                    'status': status
                }
            )

        except Exception as e:
            logger.error(f"Error notifying message status update: {e}")

    async def notify_typing_status(self, session_id, user_type, is_typing):
        """Notify other user about typing status"""
        try:
            session_info = await self.get_session_users(session_id)

            if not session_info:
                return

            # Send to seeker (since provider is typing)
            await self.channel_layer.group_send(
                f'seeker_{session_info["seeker_id"]}',
                {
                    'type': 'typing_status_event',
                    'session_id': session_id,
                    'user_type': user_type,
                    'is_typing': is_typing
                }
            )

        except Exception as e:
            logger.error(f"Error notifying typing status: {e}")

    async def notify_connection_cancelled(self, session_id):
        """Notify seeker that provider cancelled connection"""
        try:
            session_info = await self.get_session_users(session_id)

            if not session_info:
                return

            await self.channel_layer.group_send(
                f'seeker_{session_info["seeker_id"]}',
                {
                    'type': 'connection_cancelled_event',
                    'session_id': session_id
                }
            )

            # Re-enable seeker search preference
            await self.enable_seeker_search_preference(session_info['seeker_id'])

        except Exception as e:
            logger.error(f"Error notifying connection cancelled: {e}")

    async def notify_service_finished(self, session_id, finished_by):
        """Notify other user that service has been finished"""
        try:
            session_info = await self.get_session_users(session_id)

            if not session_info:
                return

            # Notify seeker if provider finished
            await self.channel_layer.group_send(
                f'seeker_{session_info["seeker_id"]}',
                {
                    'type': 'service_finished_event',
                    'session_id': session_id,
                    'finished_by': finished_by
                }
            )

        except Exception as e:
            logger.error(f"Error notifying service finished: {e}")

    @database_sync_to_async
    def get_session_users(self, session_id):
        """Get seeker and provider IDs from session"""
        from .work_assignment_models import WorkSession

        try:
            session = WorkSession.objects.select_related('work_order').get(session_id=session_id)
            return {
                'seeker_id': session.work_order.seeker.id,
                'provider_id': session.work_order.provider.id
            }
        except WorkSession.DoesNotExist:
            return None

    @database_sync_to_async
    def get_message_sender(self, message_id):
        """Get message sender info"""
        from .work_assignment_models import ChatMessage

        try:
            message = ChatMessage.objects.get(message_id=message_id)
            return {
                'sender_id': message.sender.id,
                'sender_type': message.sender_type
            }
        except ChatMessage.DoesNotExist:
            return None

    @database_sync_to_async
    def disable_seeker_search_preference(self, seeker_id):
        """Disable seeker search preference when connected to a session"""
        from apps.core.models import SeekerSearchPreference

        try:
            seeker_pref = SeekerSearchPreference.objects.get(user_id=seeker_id)
            seeker_pref.is_searching = False
            seeker_pref.save()
            logger.info(f"✅ Seeker {seeker_id} search preference disabled")
        except SeekerSearchPreference.DoesNotExist:
            logger.warning(f"⚠️ Seeker {seeker_id} has no search preference record")
        except Exception as e:
            logger.error(f"❌ Error disabling seeker search preference: {e}")

    @database_sync_to_async
    def enable_seeker_search_preference(self, seeker_id):
        """Re-enable seeker search preference after session ends"""
        from apps.core.models import SeekerSearchPreference

        try:
            seeker_pref = SeekerSearchPreference.objects.get(user_id=seeker_id)
            seeker_pref.is_searching = True
            seeker_pref.save()
            logger.info(f"✅ Seeker {seeker_id} search preference re-enabled")
        except SeekerSearchPreference.DoesNotExist:
            logger.warning(f"⚠️ Seeker {seeker_id} has no search preference record")
        except Exception as e:
            logger.error(f"❌ Error enabling seeker search preference: {e}")


class SeekerWorkConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for seekers to receive work response notifications"""

    async def connect(self):
        """Called when WebSocket connection is established"""
        self.user = self.scope['user']
        self.distance_update_task = None
        self.current_session_id = None

        if not self.user.is_authenticated:
            await self.close()
            return

        # Create group name for this seeker
        self.seeker_id = self.user.id
        self.group_name = f'seeker_{self.seeker_id}'

        # Join seeker group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()
        logger.info(f"✅ Seeker {self.user.mobile_number} connected to WebSocket")

        # Load and send chat history if there's an active session
        chat_history = await self.get_chat_history_for_seeker(self.seeker_id)
        if chat_history:
            await self.send(text_data=json.dumps({
                'type': 'chat_history_loaded',
                'session_id': chat_history['session_id'],
                'messages': chat_history['messages'],
                'message_count': len(chat_history['messages']),
                'timestamp': timezone.now().isoformat()
            }))
            logger.info(f"📜 Loaded {len(chat_history['messages'])} chat messages for seeker {self.user.mobile_number}")

    async def disconnect(self, close_code):
        """Called when WebSocket connection is closed"""
        # Cancel distance update task if running
        if self.distance_update_task and not self.distance_update_task.done():
            self.distance_update_task.cancel()

        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
        logger.info(f"❌ Seeker {self.user.mobile_number} disconnected from WebSocket")

    async def receive(self, text_data):
        """Handle messages from seeker"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')

            if message_type == 'ping':
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': timezone.now().isoformat()
                }))

            elif message_type == 'location_update':
                await self.handle_location_update(data)

            elif message_type == 'medium_selection':
                await self.handle_medium_selection(data)

            elif message_type == 'start_chat':
                await self.handle_start_chat(data)

            elif message_type == 'chat_message':
                await self.handle_chat_message(data)

            elif message_type == 'message_delivered':
                await self.handle_message_delivered(data)

            elif message_type == 'message_read':
                await self.handle_message_read(data)

            elif message_type == 'typing_indicator':
                await self.handle_typing_indicator(data)

            elif message_type == 'cancel_connection':
                await self.handle_cancel_connection(data)

            elif message_type == 'finish_service':
                # Seeker marking service as finished
                await self.handle_finish_service(data)

            else:
                logger.warning(f"Unknown message type received: {message_type}")

        except json.JSONDecodeError:
            logger.error("Invalid JSON received from WebSocket")
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}")

    async def handle_location_update(self, data):
        """Handle seeker location update"""
        try:
            session_id = data.get('session_id')
            latitude = data.get('latitude')
            longitude = data.get('longitude')

            if not all([session_id, latitude, longitude]):
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'session_id, latitude, and longitude are required'
                }))
                return

            # Update seeker location in session
            distance_data = await self.update_seeker_location(session_id, latitude, longitude)

            if distance_data:
                # Send distance update to both users
                await self.send_distance_update_to_session(session_id, distance_data)

        except Exception as e:
            logger.error(f"Error handling location update: {e}")

    async def handle_medium_selection(self, data):
        """Handle seeker selecting communication mediums"""
        try:
            session_id = data.get('session_id')
            mediums = data.get('mediums', {})

            if not session_id:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'session_id is required'
                }))
                return

            # Validate mediums - now supports all 7 medium types
            valid_types = {'telegram', 'whatsapp', 'call', 'map_location', 'website', 'instagram', 'facebook'}
            if not all(k in valid_types for k in mediums.keys()):
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'Invalid mediums. Allowed: telegram, whatsapp, call, map_location, website, instagram, facebook'
                }))
                return

            # Update seeker mediums and change state to active
            success = await self.update_seeker_mediums(session_id, mediums)

            if success:
                self.current_session_id = session_id

                # Start distance update task
                self.distance_update_task = asyncio.create_task(
                    self.periodic_distance_update(session_id)
                )

                # Send confirmation to seeker
                await self.send(text_data=json.dumps({
                    'type': 'mediums_selected',
                    'session_id': session_id,
                    'mediums': mediums,
                    'timestamp': timezone.now().isoformat()
                }))

                # Notify provider
                await self.notify_provider_medium_selection(session_id, mediums)

        except Exception as e:
            logger.error(f"Error handling medium selection: {e}")

    async def handle_start_chat(self, data):
        """Handle seeker starting chat"""
        try:
            session_id = data.get('session_id')

            if not session_id:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'session_id is required'
                }))
                return

            # Start chat in session
            chat_room_id = await self.start_chat_session(session_id)

            if chat_room_id:
                # Send chat_ready to seeker
                await self.send(text_data=json.dumps({
                    'type': 'chat_ready',
                    'session_id': session_id,
                    'chat_room_id': chat_room_id,
                    'message': 'Chat started successfully',
                    'timestamp': timezone.now().isoformat()
                }))

                # Notify provider
                await self.notify_provider_chat_ready(session_id, chat_room_id)

        except Exception as e:
            logger.error(f"Error handling start chat: {e}")

    async def handle_chat_message(self, data):
        """Handle seeker sending chat message"""
        try:
            session_id = data.get('session_id')
            message_text = data.get('message')

            if not all([session_id, message_text]):
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'session_id and message are required'
                }))
                return

            # Save message
            message_data = await self.save_chat_message(session_id, self.user.id, 'seeker', message_text)

            if message_data:
                # Send to provider
                await self.send_chat_message_to_provider(session_id, message_data)

                # Send confirmation to seeker
                await self.send(text_data=json.dumps({
                    'type': 'message_sent',
                    'message_id': message_data['message_id'],
                    'session_id': session_id,
                    'timestamp': timezone.now().isoformat()
                }))

        except Exception as e:
            logger.error(f"Error handling chat message: {e}")

    async def handle_message_delivered(self, data):
        """Handle seeker acknowledging message delivery"""
        try:
            message_id = data.get('message_id')
            if not message_id:
                return

            await self.update_message_status(message_id, 'delivered')
            await self.notify_message_status_update(message_id, 'delivered')

        except Exception as e:
            logger.error(f"Error handling message delivered: {e}")

    async def handle_message_read(self, data):
        """Handle seeker marking message as read"""
        try:
            message_id = data.get('message_id')
            if not message_id:
                return

            await self.update_message_status(message_id, 'read')
            await self.notify_message_status_update(message_id, 'read')

        except Exception as e:
            logger.error(f"Error handling message read: {e}")

    async def handle_typing_indicator(self, data):
        """Handle seeker typing indicator"""
        try:
            session_id = data.get('session_id')
            is_typing = data.get('is_typing', False)

            if not session_id:
                return

            await self.update_typing_status(session_id, self.user.id, 'seeker', is_typing)
            await self.notify_typing_status(session_id, 'seeker', is_typing)

        except Exception as e:
            logger.error(f"Error handling typing indicator: {e}")

    async def handle_cancel_connection(self, data):
        """Handle seeker cancelling connection"""
        try:
            session_id = data.get('session_id')

            if not session_id:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'session_id is required'
                }))
                return

            # Cancel session
            success = await self.cancel_session(session_id, self.user.id)

            if success:
                # Stop distance updates
                if self.distance_update_task and not self.distance_update_task.done():
                    self.distance_update_task.cancel()

                # Re-enable seeker search preference
                await self.enable_seeker_search_preference()

                # Send confirmation
                await self.send(text_data=json.dumps({
                    'type': 'connection_cancelled',
                    'session_id': session_id,
                    'message': 'Connection cancelled successfully',
                    'timestamp': timezone.now().isoformat()
                }))

                # Notify provider
                await self.notify_connection_cancelled(session_id)

                # Close connection
                await self.close()

        except Exception as e:
            logger.error(f"Error handling cancel connection: {e}")

    async def handle_finish_service(self, data):
        """Handle seeker marking service as finished (with optional rating)"""
        try:
            session_id = data.get('session_id')
            rating_stars = data.get('rating_stars')  # Optional: 1-5
            rating_description = data.get('rating_description', '')  # Optional

            if not session_id:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'session_id is required'
                }))
                return

            # Validate rating if provided
            if rating_stars is not None:
                if not isinstance(rating_stars, int) or rating_stars < 1 or rating_stars > 5:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'error': 'rating_stars must be an integer between 1 and 5'
                    }))
                    return

            # Complete session with optional rating
            success = await self.complete_session(session_id, self.user.id, rating_stars, rating_description)

            if success:
                # Stop distance updates
                if self.distance_update_task and not self.distance_update_task.done():
                    self.distance_update_task.cancel()

                # Send confirmation to seeker
                await self.send(text_data=json.dumps({
                    'type': 'service_finished',
                    'session_id': session_id,
                    'message': 'Service marked as finished successfully',
                    'timestamp': timezone.now().isoformat()
                }))

                # Notify provider
                await self.notify_service_finished(session_id, 'seeker')

                # Close connection
                await self.close()

        except Exception as e:
            logger.error(f"Error handling finish service: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Failed to finish service'
            }))

    # Channel layer event handlers
    async def work_response_notification(self, event):
        """Called when provider responds to work assignment"""
        await self.send(text_data=json.dumps({
            'type': 'work_response',
            'work_id': event['work_id'],
            'accepted': event['accepted'],
            'provider_name': event['provider_name'],
            'provider_mobile': event['provider_mobile'],
            'service_type': event['service_type'],
            'response_time': event['response_time']
        }))
        logger.info(f"📤 Sent work response notification to seeker {self.user.mobile_number}")

    async def work_accepted_event(self, event):
        """Notify seeker that provider accepted"""
        await self.send(text_data=json.dumps({
            'type': 'work_accepted',
            'work_id': event['work_id'],
            'session_id': event['session_id'],
            'connection_state': event['connection_state'],
            'message': event['message'],
            'provider_available_mediums': event.get('provider_available_mediums', {}),
            'seeker_available_mediums': event.get('seeker_available_mediums', {}),
            'timestamp': timezone.now().isoformat()
        }))

    async def distance_update_event(self, event):
        """Send distance update to seeker"""
        await self.send(text_data=json.dumps({
            'type': 'distance_update',
            'session_id': event['session_id'],
            'distance_meters': event['distance_meters'],
            'distance_formatted': event['distance_formatted'],
            'timestamp': timezone.now().isoformat()
        }))

    async def provider_mediums_update(self, event):
        """Notify seeker about provider's mediums"""
        await self.send(text_data=json.dumps({
            'type': 'provider_mediums_shared',
            'session_id': event['session_id'],
            'mediums': event['mediums'],
            'timestamp': timezone.now().isoformat()
        }))

    async def chat_ready_event(self, event):
        """Notify seeker that chat is ready"""
        await self.send(text_data=json.dumps({
            'type': 'chat_ready',
            'session_id': event['session_id'],
            'chat_room_id': event['chat_room_id'],
            'message': 'Provider started chat',
            'timestamp': timezone.now().isoformat()
        }))

    async def chat_message_event(self, event):
        """Send chat message to seeker"""
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message_id': event['message_id'],
            'session_id': event['session_id'],
            'sender_type': event['sender_type'],
            'message': event['message'],
            'timestamp': event['timestamp']
        }))

    async def message_status_update(self, event):
        """Notify seeker about message status update"""
        await self.send(text_data=json.dumps({
            'type': 'message_status_update',
            'message_id': event['message_id'],
            'status': event['status'],
            'timestamp': timezone.now().isoformat()
        }))

    async def typing_status_event(self, event):
        """Notify seeker about provider typing status"""
        await self.send(text_data=json.dumps({
            'type': 'typing_indicator',
            'session_id': event['session_id'],
            'user_type': event['user_type'],
            'is_typing': event['is_typing'],
            'timestamp': timezone.now().isoformat()
        }))

    async def connection_cancelled_event(self, event):
        """Notify seeker that provider cancelled connection"""
        await self.send(text_data=json.dumps({
            'type': 'connection_cancelled',
            'session_id': event['session_id'],
            'cancelled_by': 'provider',
            'message': 'Provider cancelled the connection',
            'timestamp': timezone.now().isoformat()
        }))

        # Re-enable seeker search preference
        await self.enable_seeker_search_preference()

        # Close connection
        await self.close()

    async def service_finished_event(self, event):
        """Notify seeker that provider marked service as finished"""
        await self.send(text_data=json.dumps({
            'type': 'service_finished',
            'session_id': event['session_id'],
            'finished_by': 'provider',
            'message': 'Provider marked the service as finished',
            'timestamp': timezone.now().isoformat()
        }))

        # Close connection
        await self.close()

    # Background task
    async def periodic_distance_update(self, session_id):
        """Send distance updates every 30 seconds"""
        try:
            while True:
                await asyncio.sleep(30)
                distance_data = await self.calculate_session_distance(session_id)
                if distance_data:
                    await self.send_distance_update_to_session(session_id, distance_data)
        except asyncio.CancelledError:
            logger.info(f"Distance update task cancelled for session {session_id}")
        except Exception as e:
            logger.error(f"Error in periodic distance update: {e}")

    # Database methods (reused from ProviderWorkConsumer)
    @database_sync_to_async
    def get_user_communication_mediums(self, user_id):
        """Get user's available communication mediums"""
        from apps.profiles.models import UserProfile
        from apps.profiles.communication_models import CommunicationSettings

        try:
            user_profile = UserProfile.objects.get(user_id=user_id)

            try:
                communication_settings = CommunicationSettings.objects.get(user_profile=user_profile)

                # Build the communication mediums dict with only enabled mediums
                mediums = {}

                if communication_settings.telegram_enabled:
                    mediums['telegram'] = {
                        "enabled": True,
                        "value": communication_settings.telegram_value or ""
                    }

                if communication_settings.whatsapp_enabled:
                    mediums['whatsapp'] = {
                        "enabled": True,
                        "value": communication_settings.whatsapp_value or ""
                    }

                if communication_settings.call_enabled:
                    mediums['call'] = {
                        "enabled": True,
                        "value": communication_settings.call_value or ""
                    }

                if communication_settings.map_location_enabled:
                    mediums['map_location'] = {
                        "enabled": True,
                        "value": communication_settings.map_location_value or ""
                    }

                if communication_settings.website_enabled:
                    mediums['website'] = {
                        "enabled": True,
                        "value": communication_settings.website_value or ""
                    }

                if communication_settings.instagram_enabled:
                    mediums['instagram'] = {
                        "enabled": True,
                        "value": communication_settings.instagram_value or ""
                    }

                if communication_settings.facebook_enabled:
                    mediums['facebook'] = {
                        "enabled": True,
                        "value": communication_settings.facebook_value or ""
                    }

                return mediums

            except CommunicationSettings.DoesNotExist:
                # No communication settings found, return empty dict
                return {}

        except UserProfile.DoesNotExist:
            logger.error(f"UserProfile not found for user_id {user_id}")
            return {}
        except Exception as e:
            logger.error(f"Error getting communication mediums for user {user_id}: {e}")
            return {}

    @database_sync_to_async
    def update_seeker_location(self, session_id, latitude, longitude):
        """Update seeker location in session"""
        from .work_assignment_models import WorkSession

        try:
            session = WorkSession.objects.get(session_id=session_id)

            # Check if location changed significantly
            old_lat = float(session.seeker_latitude) if session.seeker_latitude else None
            old_lng = float(session.seeker_longitude) if session.seeker_longitude else None

            if old_lat and old_lng:
                distance_change = calculate_distance(old_lat, old_lng, float(latitude), float(longitude)) * 1000
                if distance_change < 50:
                    return None

            # Update location
            session.seeker_latitude = Decimal(str(latitude))
            session.seeker_longitude = Decimal(str(longitude))
            session.seeker_last_location_update = timezone.now()

            # Calculate distance
            if session.provider_latitude and session.provider_longitude:
                distance_km = calculate_distance(
                    float(latitude),
                    float(longitude),
                    float(session.provider_latitude),
                    float(session.provider_longitude)
                )
                session.current_distance_meters = distance_km * 1000
                session.last_distance_update = timezone.now()

            session.save()

            return {
                'distance_meters': session.current_distance_meters,
                'distance_formatted': session.get_formatted_distance()
            }

        except WorkSession.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Error updating seeker location: {e}")
            return None

    @database_sync_to_async
    def update_seeker_mediums(self, session_id, mediums):
        """Update seeker communication mediums"""
        from .work_assignment_models import WorkSession

        try:
            session = WorkSession.objects.get(session_id=session_id)
            session.seeker_selected_mediums = mediums
            session.mediums_shared_at = timezone.now()
            session.save()

            logger.info(f"✅ Seeker mediums updated for session {session_id}")
            return True
        except WorkSession.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"Error updating seeker mediums: {e}")
            return False

    @database_sync_to_async
    def start_chat_session(self, session_id):
        """Start chat in session"""
        from .work_assignment_models import WorkSession

        try:
            session = WorkSession.objects.get(session_id=session_id)
            if not session.chat_started_at:
                session.chat_started_at = timezone.now()
                session.save()
            return str(session.chat_room_id)
        except WorkSession.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Error starting chat: {e}")
            return None

    @database_sync_to_async
    def save_chat_message(self, session_id, sender_id, sender_type, message_text):
        """Save chat message to database"""
        from .work_assignment_models import WorkSession, ChatMessage

        try:
            session = WorkSession.objects.get(session_id=session_id)
            message = ChatMessage.objects.create(
                session=session,
                sender_id=sender_id,
                sender_type=sender_type,
                message_text=message_text,
                delivery_status='sent'
            )
            return {
                'message_id': str(message.message_id),
                'sender_type': sender_type,
                'message': message_text,
                'timestamp': message.created_at.isoformat()
            }
        except WorkSession.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Error saving chat message: {e}")
            return None

    @database_sync_to_async
    def update_message_status(self, message_id, status):
        """Update message delivery/read status"""
        from .work_assignment_models import ChatMessage

        try:
            message = ChatMessage.objects.get(message_id=message_id)
            message.delivery_status = status
            if status == 'delivered':
                message.delivered_at = timezone.now()
            elif status == 'read':
                message.read_at = timezone.now()
            message.save()
            return True
        except ChatMessage.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"Error updating message status: {e}")
            return False

    @database_sync_to_async
    def get_chat_history_for_seeker(self, seeker_id):
        """Get chat history for seeker's most recent active session"""
        from .work_assignment_models import WorkSession, ChatMessage

        try:
            # Get most recent active session for this seeker
            session = WorkSession.objects.filter(
                work_order__seeker_id=seeker_id,
                connection_state='active'
            ).order_by('-created_at').first()

            if not session:
                return None

            # Get all messages for this session, ordered by creation time
            messages = ChatMessage.objects.filter(
                session=session
            ).order_by('created_at')

            # Serialize messages
            message_list = []
            for msg in messages:
                message_list.append({
                    'message_id': str(msg.message_id),
                    'sender_type': msg.sender_type,
                    'message': msg.message_text,
                    'delivery_status': msg.delivery_status,
                    'delivered_at': msg.delivered_at.isoformat() if msg.delivered_at else None,
                    'read_at': msg.read_at.isoformat() if msg.read_at else None,
                    'timestamp': msg.created_at.isoformat()
                })

            return {
                'session_id': str(session.session_id),
                'messages': message_list
            }

        except Exception as e:
            logger.error(f"Error getting chat history for seeker: {e}")
            return None

    @database_sync_to_async
    def update_typing_status(self, session_id, user_id, user_type, is_typing):
        """Update typing indicator status"""
        from .work_assignment_models import WorkSession, TypingIndicator

        try:
            session = WorkSession.objects.get(session_id=session_id)
            indicator, created = TypingIndicator.objects.get_or_create(
                session=session,
                user_id=user_id,
                defaults={'user_type': user_type, 'is_typing': is_typing}
            )
            if not created:
                indicator.is_typing = is_typing
                indicator.save()
            return True
        except WorkSession.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"Error updating typing status: {e}")
            return False

    @database_sync_to_async
    def cancel_session(self, session_id, cancelled_by_user_id):
        """Cancel work session"""
        from .work_assignment_models import WorkSession, WorkOrder, ChatMessage
        from datetime import timedelta

        try:
            session = WorkSession.objects.get(session_id=session_id)
            session.connection_state = 'cancelled'
            session.cancelled_by_id = cancelled_by_user_id
            session.cancelled_at = timezone.now()
            session.save()

            # Update work order
            work_order = session.work_order
            work_order.status = 'cancelled'
            work_order.save()

            # Set message expiry
            expiry_time = timezone.now() + timedelta(hours=24)
            ChatMessage.objects.filter(session=session).update(expires_at=expiry_time)

            logger.info(f"✅ Session {session_id} cancelled by seeker")
            return True
        except WorkSession.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"Error cancelling session: {e}")
            return False

    @database_sync_to_async
    def complete_session(self, session_id, completed_by_user_id, rating_stars=None, rating_description=None):
        """Complete work session and optionally add rating"""
        from .work_assignment_models import WorkSession, ChatMessage
        from datetime import timedelta

        try:
            session = WorkSession.objects.get(session_id=session_id)

            # Check if already completed
            if session.connection_state == 'completed':
                logger.warning(f"Session {session_id} already completed")
                return False

            session.connection_state = 'completed'
            session.completed_by_id = completed_by_user_id
            session.completed_at = timezone.now()

            # Add rating if provided (only from seeker)
            if rating_stars is not None:
                session.rating_stars = rating_stars
                session.rating_description = rating_description or ''
                session.rated_at = timezone.now()

            session.save()

            # Update work order status
            work_order = session.work_order
            work_order.status = 'completed'
            work_order.completion_time = timezone.now()
            work_order.save()

            # Set expiry for chat messages (24 hours from now)
            expiry_time = timezone.now() + timedelta(hours=24)
            ChatMessage.objects.filter(session=session).update(expires_at=expiry_time)

            logger.info(f"✅ Session {session_id} completed by user {completed_by_user_id}")
            return True
        except WorkSession.DoesNotExist:
            logger.error(f"Session {session_id} not found")
            return False
        except Exception as e:
            logger.error(f"Error completing session: {e}")
            return False

    @database_sync_to_async
    def calculate_session_distance(self, session_id):
        """Calculate current distance between users"""
        from .work_assignment_models import WorkSession

        try:
            session = WorkSession.objects.get(session_id=session_id)
            if all([session.seeker_latitude, session.seeker_longitude,
                   session.provider_latitude, session.provider_longitude]):
                distance_km = calculate_distance(
                    float(session.seeker_latitude),
                    float(session.seeker_longitude),
                    float(session.provider_latitude),
                    float(session.provider_longitude)
                )
                session.current_distance_meters = distance_km * 1000
                session.last_distance_update = timezone.now()
                session.save()
                return {
                    'distance_meters': session.current_distance_meters,
                    'distance_formatted': session.get_formatted_distance()
                }
            return None
        except WorkSession.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Error calculating distance: {e}")
            return None

    @database_sync_to_async
    def enable_seeker_search_preference(self):
        """Re-enable seeker search preference"""
        from apps.core.models import SeekerSearchPreference

        try:
            seeker_pref = SeekerSearchPreference.objects.get(user=self.user)
            seeker_pref.is_searching = True
            seeker_pref.save()
            logger.info(f"✅ Seeker {self.user.mobile_number} search re-enabled")
        except SeekerSearchPreference.DoesNotExist:
            logger.warning(f"⚠️ Seeker {self.user.mobile_number} has no search preference")
        except Exception as e:
            logger.error(f"❌ Error enabling seeker search: {e}")

    @database_sync_to_async
    def get_session_users(self, session_id):
        """Get session user IDs"""
        from .work_assignment_models import WorkSession

        try:
            session = WorkSession.objects.select_related('work_order').get(session_id=session_id)
            return {
                'seeker_id': session.work_order.seeker.id,
                'provider_id': session.work_order.provider.id
            }
        except WorkSession.DoesNotExist:
            return None

    @database_sync_to_async
    def get_message_sender(self, message_id):
        """Get message sender info"""
        from .work_assignment_models import ChatMessage

        try:
            message = ChatMessage.objects.get(message_id=message_id)
            return {
                'sender_id': message.sender.id,
                'sender_type': message.sender_type
            }
        except ChatMessage.DoesNotExist:
            return None

    # Notification methods
    async def send_distance_update_to_session(self, session_id, distance_data):
        """Send distance update to both users"""
        try:
            session_info = await self.get_session_users(session_id)
            if not session_info:
                return

            await self.channel_layer.group_send(
                f'provider_{session_info["provider_id"]}',
                {
                    'type': 'distance_update_event',
                    'session_id': session_id,
                    'distance_meters': distance_data['distance_meters'],
                    'distance_formatted': distance_data['distance_formatted']
                }
            )

            await self.channel_layer.group_send(
                f'seeker_{session_info["seeker_id"]}',
                {
                    'type': 'distance_update_event',
                    'session_id': session_id,
                    'distance_meters': distance_data['distance_meters'],
                    'distance_formatted': distance_data['distance_formatted']
                }
            )
        except Exception as e:
            logger.error(f"Error sending distance update: {e}")

    async def notify_provider_medium_selection(self, session_id, mediums):
        """Notify provider about seeker's medium selection"""
        try:
            session_info = await self.get_session_users(session_id)
            if not session_info:
                return

            await self.channel_layer.group_send(
                f'provider_{session_info["provider_id"]}',
                {
                    'type': 'medium_selection_update',
                    'session_id': session_id,
                    'mediums': mediums
                }
            )
        except Exception as e:
            logger.error(f"Error notifying provider of medium selection: {e}")

    async def notify_provider_chat_ready(self, session_id, chat_room_id):
        """Notify provider that chat is ready"""
        try:
            session_info = await self.get_session_users(session_id)
            if not session_info:
                return

            await self.channel_layer.group_send(
                f'provider_{session_info["provider_id"]}',
                {
                    'type': 'chat_ready_event',
                    'session_id': session_id,
                    'chat_room_id': chat_room_id
                }
            )
        except Exception as e:
            logger.error(f"Error notifying provider chat ready: {e}")

    async def send_chat_message_to_provider(self, session_id, message_data):
        """Send chat message to provider"""
        try:
            session_info = await self.get_session_users(session_id)
            if not session_info:
                return

            await self.channel_layer.group_send(
                f'provider_{session_info["provider_id"]}',
                {
                    'type': 'chat_message_event',
                    'session_id': session_id,
                    **message_data
                }
            )
        except Exception as e:
            logger.error(f"Error sending chat message to provider: {e}")

    async def notify_message_status_update(self, message_id, status):
        """Notify sender about message status"""
        try:
            sender_info = await self.get_message_sender(message_id)
            if not sender_info:
                return

            await self.channel_layer.group_send(
                f'{sender_info["sender_type"]}_{sender_info["sender_id"]}',
                {
                    'type': 'message_status_update',
                    'message_id': message_id,
                    'status': status
                }
            )
        except Exception as e:
            logger.error(f"Error notifying message status: {e}")

    async def notify_typing_status(self, session_id, user_type, is_typing):
        """Notify provider about seeker typing"""
        try:
            session_info = await self.get_session_users(session_id)
            if not session_info:
                return

            await self.channel_layer.group_send(
                f'provider_{session_info["provider_id"]}',
                {
                    'type': 'typing_status_event',
                    'session_id': session_id,
                    'user_type': user_type,
                    'is_typing': is_typing
                }
            )
        except Exception as e:
            logger.error(f"Error notifying typing status: {e}")

    async def notify_connection_cancelled(self, session_id):
        """Notify provider that seeker cancelled"""
        try:
            session_info = await self.get_session_users(session_id)
            if not session_info:
                return

            await self.channel_layer.group_send(
                f'provider_{session_info["provider_id"]}',
                {
                    'type': 'connection_cancelled_event',
                    'session_id': session_id
                }
            )
        except Exception as e:
            logger.error(f"Error notifying connection cancelled: {e}")

    async def notify_service_finished(self, session_id, finished_by):
        """Notify provider that service has been finished"""
        try:
            session_info = await self.get_session_users(session_id)

            if not session_info:
                return

            # Notify provider if seeker finished
            await self.channel_layer.group_send(
                f'provider_{session_info["provider_id"]}',
                {
                    'type': 'service_finished_event',
                    'session_id': session_id,
                    'finished_by': finished_by
                }
            )

        except Exception as e:
            logger.error(f"Error notifying service finished: {e}")
