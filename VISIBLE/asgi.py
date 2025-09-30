import os
import django
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'VISIBLE.settings')
django.setup()

from apps.location_services.routing import websocket_urlpatterns as location_patterns
from apps.profiles.routing import websocket_urlpatterns as work_patterns
from apps.authentication.middleware import JWTAuthMiddlewareStack

# Combine all WebSocket URL patterns
all_websocket_urlpatterns = location_patterns + work_patterns

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": JWTAuthMiddlewareStack(
        URLRouter(
            all_websocket_urlpatterns
        )
    ),
})