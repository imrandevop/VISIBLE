# apps/profiles/consumers/__init__.py
"""
WebSocket consumers for work assignment system.

This module provides backward compatibility by re-exporting all consumer classes.
"""
from .provider_work_consumer import ProviderWorkConsumer
from .seeker_work_consumer import SeekerWorkConsumer

__all__ = ['ProviderWorkConsumer', 'SeekerWorkConsumer']
