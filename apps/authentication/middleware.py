# apps/authentication/middleware.py

import json
import base64
from urllib.parse import parse_qs
from asgiref.sync import sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model
from django.conf import settings

User = get_user_model()


class JWTAuthMiddleware:
    """
    Custom middleware for JWT authentication in Django Channels WebSocket connections.
    Supports Bearer token in Authorization header.
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # Only process WebSocket connections
        if scope["type"] != "websocket":
            return await self.inner(scope, receive, send)

        # Get headers from scope
        headers = dict(scope.get("headers", []))

        # Look for Authorization header
        auth_header = headers.get(b"authorization")

        if auth_header:
            try:
                # Decode header and extract token
                auth_header = auth_header.decode("utf-8")

                if auth_header.startswith("Bearer "):
                    token = auth_header.split(" ")[1]
                    user = await self.get_user_from_token(token)
                    scope["user"] = user
                else:
                    scope["user"] = AnonymousUser()
            except Exception as e:
                print(f"JWT Auth Error: {e}")
                scope["user"] = AnonymousUser()
        else:
            scope["user"] = AnonymousUser()

        return await self.inner(scope, receive, send)

    @sync_to_async
    def get_user_from_token(self, token):
        """
        Validate JWT token and return the associated user.
        Simple JWT validation without external libraries.
        """
        try:
            # Split the JWT token
            parts = token.split('.')
            if len(parts) != 3:
                return AnonymousUser()

            # Decode the payload (second part)
            payload_encoded = parts[1]

            # Add padding if needed
            padding = 4 - len(payload_encoded) % 4
            if padding != 4:
                payload_encoded += '=' * padding

            # Decode base64
            payload_bytes = base64.urlsafe_b64decode(payload_encoded)
            payload = json.loads(payload_bytes.decode('utf-8'))

            # Get user ID from payload
            user_id = payload.get('user_id')

            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                    return user
                except User.DoesNotExist:
                    return AnonymousUser()
            else:
                return AnonymousUser()

        except Exception as e:
            print(f"Token validation failed: {e}")
            return AnonymousUser()


def JWTAuthMiddlewareStack(inner):
    """
    Convenience function that wraps the JWT auth middleware.
    Similar to AuthMiddlewareStack but for JWT.
    """
    return JWTAuthMiddleware(inner)