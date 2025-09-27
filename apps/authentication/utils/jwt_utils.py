# apps/authentication/utils/jwt_utils.py

from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model

User = get_user_model()

def get_tokens_for_user(user):
    """
    Generate JWT tokens for a user
    Returns access token with mobile number in payload
    """
    refresh = RefreshToken.for_user(user)
    
    # Add custom claims to the token
    refresh['mobile_number'] = user.mobile_number
    refresh['is_mobile_verified'] = user.is_mobile_verified
    
    return {
        'access_token': str(refresh.access_token),
        'refresh_token': str(refresh),  # We'll only use access_token for now
    }

def create_jwt_response(user, is_new_user=False, profile_complete=False, can_access_app=False, user_type=None, next_action="complete_profile"):
    """
    Create standardized JWT response for authentication
    """
    tokens = get_tokens_for_user(user)

    return {
        'status': 'success',
        'message': f"OTP verified and user {'created' if is_new_user else 'updated'} successfully",
        'access_token': tokens['access_token'],
        'refresh_token': tokens['refresh_token'],
        'mobile': user.mobile_number,
        'is_new_user': is_new_user,
        'profile_complete': profile_complete,
        'can_access_app': can_access_app,
        'user_type': user_type,
        'next_action': next_action
    }