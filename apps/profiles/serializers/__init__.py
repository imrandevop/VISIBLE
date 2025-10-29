# apps/profiles/serializers/__init__.py
"""
Profile serializers package.

This module provides backward compatibility by re-exporting all serializer classes.
"""
from .serializer_utils import FlexibleImageField, FlexibleStringField
from .profile_serializers import ProfileSetupSerializer, ProfileResponseSerializer
from .wallet_serializers import WalletSerializer, WalletTransactionSerializer
from .role_switch_serializers import RoleSwitchSerializer

__all__ = [
    'FlexibleImageField',
    'FlexibleStringField',
    'ProfileSetupSerializer',
    'ProfileResponseSerializer',
    'WalletSerializer',
    'WalletTransactionSerializer',
    'RoleSwitchSerializer',
]
