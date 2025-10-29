from django.urls import re_path
from .consumers import LocationConsumer

websocket_urlpatterns = [
    re_path(r'ws/location/(?P<user_type>provider|seeker)/$', LocationConsumer.as_asgi()),
]