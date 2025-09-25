# apps/authentication/views.py
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
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
                
                # Create JWT response
                jwt_response = create_jwt_response(user, is_new_user=created)
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
    


def auth_info(request):
    from django.http import JsonResponse
    return JsonResponse({
        "app": "authentication",
        "status": "active",
        "endpoints": ["send-otp", "verify-otp", "refresh-token"]
    })