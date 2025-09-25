"""
ASGI config for VISIBLE project - Production version.

This module contains the ASGI application used by Django's development server
and any production ASGI deployments. It should expose a module-level variable
named ``application``. Django's ``runserver`` and ``runworker`` management
commands expect ``application`` in this file.
"""

import os
import django
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application

# Ensure Django is set up before importing other modules
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'VISIBLE.settings')
django.setup()

# Import routing after Django setup
from apps.location_services.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            websocket_urlpatterns
        )
    ),
})