# apps/authentication/views.py
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework import status

# Import your OTP service and JWT utils
from apps.authentication.services.otp_service import MSG91OTPService
from apps.authentication.utils.jwt_utils import create_jwt_response

# Initialize OTP service
otp_service = MSG91OTPService()

@api_view(['POST'])
@permission_classes([AllowAny])
def send_otp_api(request, version=None):
    """
    API endpoint to send OTP to mobile number
    This same endpoint works for both initial send and resend
    
    POST /api/1/send-otp/
    Body: {"mobile_number": "9876543210"}
    
    Response: {
        "status": "success"/"error",
        "message": "OTP sent successfully to your mobile number",
        "mobile": "9876543210"
    }
    """
    try:
        mobile_number = request.data.get('mobile_number')
        
        # You can handle different versions here
        if hasattr(request, 'version'):
            api_version = request.version
            # Example: Different logic for different versions
            if api_version == 'v2':
                # Future v2 logic can go here
                pass
        
        # Validate input
        if not mobile_number:
            return Response({
                "status": "error",
                "message": "Mobile number is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Send OTP (works for both send and resend)
        result = otp_service.send_otp_sms(mobile_number)
        
        # Return appropriate status code
        status_code = status.HTTP_200_OK if result["status"] == "success" else status.HTTP_400_BAD_REQUEST
        return Response(result, status=status_code)
        
    except Exception as e:
        return Response({
            "status": "error",
            "message": "An unexpected server error occurred. Please try again."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
def verify_otp_api(request, version=None):
    """
    API endpoint to verify OTP and create user with JWT token
    
    POST /api/1/verify-otp/
    Body: {"mobile_number": "9876543210", "otp": "123456"}
    
    Response: {
        "status": "success"/"error",
        "message": "OTP verified and user created successfully",
        "access_token": "eyJ0eXAiOiJKV1QiLCJhbGci...",
        "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGci...",
        "mobile": "9876543210",
        "is_new_user": true
    }
    """
    try:
        mobile_number = request.data.get('mobile_number')
        otp = request.data.get('otp')
        
        # Handle versioning
        if hasattr(request, 'version'):
            api_version = request.version
            # Example: v2 might return different response format
            if api_version == 'v2':
                # Future v2 logic can go here
                pass
        
        # Validate inputs
        if not mobile_number:
            return Response({
                "status": "error",
                "message": "Mobile number is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not otp:
            return Response({
                "status": "error",
                "message": "OTP is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Verify OTP
        result = otp_service.verify_otp(mobile_number, otp)
        
        if result["status"] == "success":
            # OTP verified, now create or get user
            from apps.authentication.models import User
            from apps.profiles.models import UserProfile

            # Clean mobile number for database
            clean_mobile = otp_service.clean_mobile_number(mobile_number)

            try:
                # Try to get existing user or create new one
                user, created = User.objects.get_or_create(
                    mobile_number=clean_mobile,
                    defaults={
                        'username': clean_mobile,  # Use mobile as username
                        'is_mobile_verified': True,
                    }
                )

                # If user already exists, just mark as verified
                if not created:
                    user.is_mobile_verified = True
                    user.save()

                # Check if user has profile and get profile data
                try:
                    user_profile = UserProfile.objects.get(user=user)
                    # Update profile completion status
                    user_profile.check_profile_completion()
                    profile_exists = True
                    profile_complete = user_profile.profile_complete
                    can_access_app = user_profile.can_access_app
                    user_type = user_profile.user_type
                    next_action = "proceed_to_app" if profile_complete else "complete_profile"
                except UserProfile.DoesNotExist:
                    # No profile exists - new user
                    profile_exists = False
                    profile_complete = False
                    can_access_app = False
                    user_type = None
                    next_action = "complete_profile"

                # Create JWT response with profile data
                jwt_response = create_jwt_response(
                    user,
                    is_new_user=created,
                    profile_complete=profile_complete,
                    can_access_app=can_access_app,
                    user_type=user_type,
                    next_action=next_action
                )
                return Response(jwt_response, status=status.HTTP_200_OK)
                
            except Exception as db_error:
                return Response({
                    "status": "error",
                    "message": "OTP verified but failed to create user. Please try again."
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            # OTP verification failed
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        return Response({
            "status": "error",
            "message": "An unexpected server error occurred. Please try again."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([AllowAny])
def refresh_token_api(request, version=None):
    """
    API endpoint to refresh access token using refresh token
    
    POST /api/1/refresh-token/
    Body: {"refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGci..."}
    
    Response: {
        "status": "success"/"error",
        "access_token": "eyJ0eXAiOiJKV1QiLCJhbGci...",
        "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGci..."
    }
    """
    try:
        refresh_token = request.data.get('refresh_token')
        
        # Handle versioning
        if hasattr(request, 'version'):
            api_version = request.version
            # Example: v2 might have different token refresh logic
            if api_version == 'v2':
                # Future v2 logic can go here
                pass
        
        if not refresh_token:
            return Response({
                "status": "error",
                "message": "Refresh token is required"
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Create refresh token object
            refresh = RefreshToken(refresh_token)
            
            # Get user from refresh token
            user_id = refresh['user_id']
            from apps.authentication.models import User
            user = User.objects.get(id=user_id)
            
            # Generate new tokens
            new_refresh = RefreshToken.for_user(user)
            new_refresh['mobile_number'] = user.mobile_number
            new_refresh['is_mobile_verified'] = user.is_mobile_verified
            
            return Response({
                "status": "success",
                "access_token": str(new_refresh.access_token),
                "refresh_token": str(new_refresh),
                "message": "Token refreshed successfully"
            }, status=status.HTTP_200_OK)
            
        except TokenError:
            return Response({
                "status": "error",
                "message": "Invalid or expired refresh token"
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        except User.DoesNotExist:
            return Response({
                "status": "error",
                "message": "User not found"
            }, status=status.HTTP_404_NOT_FOUND)
            
    except Exception as e:
        return Response({
            "status": "error",
            "message": "An unexpected server error occurred. Please try again."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_account_api(request, version=None):
    """
    API endpoint to delete user account permanently

    DELETE /api/1/authentication/delete-account/
    Headers:
        Authorization: Bearer <jwt_token>

    Response:
        Success (200):
        {
            "status": "success",
            "message": "Your account has been deleted successfully"
        }

        Error (401):
        {
            "status": "error",
            "message": "Authentication required"
        }

        Error (500):
        {
            "status": "error",
            "message": "Failed to delete account. Please try again."
        }
    """
    try:
        # Get authenticated user from JWT token
        user = request.user

        # Handle versioning
        if hasattr(request, 'version'):
            api_version = request.version
            # Future version-specific logic can go here
            if api_version == 'v2':
                pass

        # Store mobile number for logging (optional)
        mobile_number = user.mobile_number
        user_id = user.id

        try:
            # Import necessary models and utilities
            from apps.profiles.models import UserProfile
            import os
            from django.conf import settings

            # Delete associated media files before deleting user
            try:
                # Get user profile if exists
                if hasattr(user, 'profile'):
                    user_profile = user.profile

                    # Delete profile photo if exists
                    if user_profile.profile_photo:
                        if os.path.isfile(user_profile.profile_photo.path):
                            os.remove(user_profile.profile_photo.path)

                    # Delete portfolio images if exist
                    for portfolio_image in user_profile.service_portfolio_images.all():
                        if portfolio_image.image:
                            if os.path.isfile(portfolio_image.image.path):
                                os.remove(portfolio_image.image.path)

            except Exception as file_error:
                # Log file deletion error but continue with account deletion
                pass

            # Delete the user account (cascade will handle related data)
            # This will automatically delete:
            # - UserProfile
            # - ServicePortfolioImage
            # - DriverServiceData, PropertyServiceData, SOSServiceData
            # - Wallet and WalletTransaction
            # - ProviderRating, ProviderReview
            # - WorkOrder, WorkSession, ChatMessage
            # - CommunicationSettings
            # - And all other related models with CASCADE
            user.delete()

            return Response({
                "status": "success",
                "message": "Your account has been deleted successfully"
            }, status=status.HTTP_200_OK)

        except Exception as deletion_error:
            return Response({
                "status": "error",
                "message": "Failed to delete account. Please try again."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    except Exception as e:
        return Response({
            "status": "error",
            "message": "An unexpected server error occurred. Please try again."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



def auth_info(request):
    from django.http import JsonResponse
    return JsonResponse({
        "app": "authentication",
        "status": "active",
        "endpoints": ["send-otp", "verify-otp", "refresh-token", "delete-account"]
    })