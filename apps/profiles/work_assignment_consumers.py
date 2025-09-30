# apps/profiles/work_assignment_consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

class ProviderWorkConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for providers to receive work assignments and send responses"""

    async def connect(self):
        """Called when WebSocket connection is established"""
        self.user = self.scope['user']

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

    async def disconnect(self, close_code):
        """Called when WebSocket connection is closed"""
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

            elif message_type == 'provider_status_update':
                # Provider updated their active status
                await self.handle_status_update(data)

            elif message_type == 'location_update':
                # Provider updated their location (optional)
                await self.handle_location_update(data)

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

            # Update work order status in database
            success = await self.update_work_order_status(work_id, accepted)

            if success:
                # Send confirmation
                await self.send(text_data=json.dumps({
                    'type': 'work_response_confirmation',
                    'work_id': work_id,
                    'accepted': accepted,
                    'message': 'Response received successfully',
                    'timestamp': timezone.now().isoformat()
                }))

                # Send notification to seeker
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

    async def handle_status_update(self, data):
        """Handle provider status update"""
        try:
            active = data.get('active', False)
            service_type = data.get('service_type', '')

            logger.info(f"📍 Provider {self.user.mobile_number} status: {'active' if active else 'inactive'}")

            # Update profile in database
            await self.update_provider_status(active, service_type)

            # Send confirmation
            await self.send(text_data=json.dumps({
                'type': 'status_update_confirmation',
                'active': active,
                'service_type': service_type,
                'message': 'Status updated successfully',
                'timestamp': timezone.now().isoformat()
            }))

        except Exception as e:
            logger.error(f"Error handling status update: {e}")

    async def handle_location_update(self, data):
        """Handle provider location update (optional feature)"""
        try:
            latitude = data.get('latitude')
            longitude = data.get('longitude')

            if latitude and longitude:
                # You can store location in database if needed
                logger.info(f"📍 Provider {self.user.mobile_number} location updated: {latitude}, {longitude}")

                await self.send(text_data=json.dumps({
                    'type': 'location_update_confirmation',
                    'latitude': latitude,
                    'longitude': longitude,
                    'timestamp': timezone.now().isoformat()
                }))

        except Exception as e:
            logger.error(f"Error handling location update: {e}")

    @database_sync_to_async
    def check_user_is_provider(self):
        """Check if user is a provider"""
        try:
            profile = self.user.profile
            return profile.user_type == 'provider'
        except:
            return False

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
    def update_provider_status(self, active, service_type):
        """Update provider status in database"""
        try:
            profile = self.user.profile
            profile.is_active_for_work = active
            if service_type:
                profile.service_type = service_type
            profile.save(update_fields=['is_active_for_work', 'service_type'])
            logger.info(f"✅ Provider {self.user.mobile_number} status updated")
        except Exception as e:
            logger.error(f"❌ Error updating provider status: {e}")

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

            # Also send FCM notification to seeker
            await self.send_fcm_to_seeker(work_order_data, accepted)

        except Exception as e:
            logger.error(f"Error notifying seeker of response: {e}")

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

    @database_sync_to_async
    def send_fcm_to_seeker(self, work_order_data, accepted):
        """Send FCM notification to seeker"""
        try:
            from .notification_services import send_work_response_notification
            from .work_assignment_models import WorkOrder

            work_order = WorkOrder.objects.get(id=work_order_data['work_id'])
            send_work_response_notification(
                work_order_data['seeker_profile'],
                work_order,
                accepted
            )
        except Exception as e:
            logger.error(f"Error sending FCM to seeker: {e}")


class SeekerWorkConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer for seekers to receive work response notifications"""

    async def connect(self):
        """Called when WebSocket connection is established"""
        self.user = self.scope['user']

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

    async def disconnect(self, close_code):
        """Called when WebSocket connection is closed"""
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
        logger.info(f"❌ Seeker {self.user.mobile_number} disconnected from WebSocket")

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