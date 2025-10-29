# apps/location_services/consumers/__init__.py
"""
Location services consumers package.

This module provides backward compatibility by re-exporting the LocationConsumer.
"""
from .location_consumer import LocationConsumer

__all__ = ['LocationConsumer']
