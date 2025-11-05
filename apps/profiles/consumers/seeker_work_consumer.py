# apps/profiles/consumers/seeker_work_consumer.py
"""
WebSocket consumer for seekers to manage work requests and communication.

Production URL: wss://api.visibleapp.in/ws/work/seeker/
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

            # Notify provider that seeker is online
            await self.notify_user_presence(chat_history['session_id'], 'seeker', 'online')

    async def disconnect(self, close_code):
        """Called when WebSocket connection is closed"""
        # Notify provider that seeker is offline (if there's an active session)
        if hasattr(self, 'current_session_id') and self.current_session_id:
            await self.notify_user_presence(self.current_session_id, 'seeker', 'offline')

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

            elif message_type == 'request_chat_history':
                # Seeker requesting chat history
                await self.handle_request_chat_history(data)

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

            # Validate mediums - now supports all 9 fields (7 medium types + land_mark + upi_ID)
            valid_types = {'telegram', 'whatsapp', 'call', 'map_location', 'website', 'instagram', 'facebook', 'land_mark', 'upi_ID'}
            if not all(k in valid_types for k in mediums.keys()):
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'error': 'Invalid mediums. Allowed: telegram, whatsapp, call, map_location, website, instagram, facebook, land_mark, upi_ID'
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
                # Send to provider via WebSocket
                await self.send_chat_message_to_provider(session_id, message_data)

                # Send FCM notification to provider
                await self.send_chat_fcm_to_provider(session_id, message_text, message_data['message_id'])

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

    async def handle_request_chat_history(self, data):
        """Handle seeker requesting chat history"""
        try:
            session_id = data.get('session_id')

            # Load chat history for this seeker
            chat_history = await self.get_chat_history_for_seeker(self.seeker_id)

            if chat_history:
                # If session_id was provided, verify it matches
                if session_id and chat_history['session_id'] != session_id:
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'error': 'Session ID does not match active session'
                    }))
                    return

                # Send chat history
                await self.send(text_data=json.dumps({
                    'type': 'chat_history_loaded',
                    'session_id': chat_history['session_id'],
                    'messages': chat_history['messages'],
                    'message_count': len(chat_history['messages']),
                    'timestamp': timezone.now().isoformat()
                }))
                logger.info(f"📜 Loaded {len(chat_history['messages'])} messages for seeker {self.user.mobile_number}")
            else:
                # No active session or no messages
                await self.send(text_data=json.dumps({
                    'type': 'chat_history_loaded',
                    'session_id': session_id,
                    'messages': [],
                    'message_count': 0,
                    'timestamp': timezone.now().isoformat()
                }))
                logger.info(f"📜 No chat history found for seeker {self.user.mobile_number}")

        except Exception as e:
            logger.error(f"Error handling request chat history: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'error': 'Failed to load chat history'
            }))

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
            'provider': event.get('provider', {}),
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

    async def user_presence_event(self, event):
        """Notify seeker about provider online/offline status"""
        await self.send(text_data=json.dumps({
            'type': 'user_presence',
            'user_type': event['user_type'],
            'status': event['status'],
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

                # Add land_mark and upi_ID to all medium responses
                mediums['land_mark'] = communication_settings.land_mark or ""
                mediums['upi_ID'] = communication_settings.upi_ID or ""

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
        from apps.profiles.work_assignment_models import WorkSession

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
        from apps.profiles.work_assignment_models import WorkSession

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
        from apps.profiles.work_assignment_models import WorkSession

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
        from apps.profiles.work_assignment_models import WorkSession, ChatMessage

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
        from apps.profiles.work_assignment_models import ChatMessage

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
    def send_chat_fcm_to_provider(self, session_id, message_text, message_id):
        """
        Send FCM push notification to provider for chat message

        Args:
            session_id: UUID of the work session
            message_text: str - The chat message content
            message_id: UUID - The message ID
        """
        from apps.profiles.work_assignment_models import WorkSession
        from apps.profiles.notification_services import send_chat_message_notification

        try:
            session = WorkSession.objects.select_related(
                'work_order__seeker__profile',
                'work_order__provider__profile'
            ).get(session_id=session_id)

            provider_profile = session.work_order.provider.profile
            seeker_profile = session.work_order.seeker.profile

            # Send FCM notification
            success, fcm_message_id, error = send_chat_message_notification(
                recipient_profile=provider_profile,
                sender_profile=seeker_profile,
                session=session,
                message_text=message_text,
                message_id=message_id
            )

            if success:
                logger.info(f"✅ Chat FCM notification sent to provider for session {session_id}")
            else:
                logger.warning(f"⚠️ Failed to send chat FCM to provider for session {session_id}: {error}")

            return success

        except WorkSession.DoesNotExist:
            logger.error(f"❌ Work session {session_id} not found when sending chat FCM")
            return False
        except Exception as e:
            logger.error(f"❌ Error sending chat FCM notification for session {session_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    @database_sync_to_async
    def get_chat_history_for_seeker(self, seeker_id):
        """Get chat history for seeker's most recent active session"""
        from apps.profiles.work_assignment_models import WorkSession, ChatMessage

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
        from apps.profiles.work_assignment_models import WorkSession, TypingIndicator

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
        from apps.profiles.work_assignment_models import WorkSession, WorkOrder, ChatMessage
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
        from apps.profiles.work_assignment_models import WorkSession, ChatMessage
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
        from apps.profiles.work_assignment_models import WorkSession

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
        from apps.profiles.work_assignment_models import WorkSession

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
        from apps.profiles.work_assignment_models import ChatMessage

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

    async def notify_user_presence(self, session_id, user_type, status):
        """Notify other user about online/offline presence"""
        try:
            session_info = await self.get_session_users(session_id)

            if not session_info:
                return

            # Determine recipient based on who's presence changed
            if user_type == 'provider':
                # Provider status changed, notify seeker
                recipient_group = f'seeker_{session_info["seeker_id"]}'
            else:
                # Seeker status changed, notify provider
                recipient_group = f'provider_{session_info["provider_id"]}'

            await self.channel_layer.group_send(
                recipient_group,
                {
                    'type': 'user_presence_event',
                    'user_type': user_type,
                    'status': status
                }
            )

        except Exception as e:
            logger.error(f"Error notifying user presence: {e}")

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
