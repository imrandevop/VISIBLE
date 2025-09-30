# apps/profiles/routing.py
from django.urls import re_path
from .work_assignment_consumers import ProviderWorkConsumer, SeekerWorkConsumer

websocket_urlpatterns = [
    re_path(r'ws/work/provider/$', ProviderWorkConsumer.as_asgi()),
    re_path(r'ws/work/seeker/$', SeekerWorkConsumer.as_asgi()),
]