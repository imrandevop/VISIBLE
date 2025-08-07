from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from .models import User, OTP
from .services import MSG91Service
import re

def validate_mobile_number(mobile):
    """Validate Indian mobile number"""
    pattern = r'^[6-9]\d{9}$'
    return re.match(pattern, mobile) is not None

@api_view(['GET'])
def test_api(request):
    """Test if API is working"""
    return Response({
        'success': True,
        'message': 'Authentication API is working!',
        'timestamp': timezone.now()
    })

@api_view(['POST'])
def send_otp(request):
    """Send OTP to mobile number"""
    mobile_number = request.data.get('mobile_number')
    
    if not mobile_number:
        return Response({
            'success': False,
            'message': 'Mobile number is required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Clean mobile number - remove spaces, dashes, etc.
    mobile_number = re.sub(r'[^\d]', '', mobile_number)
    
    # Remove country code if provided (91 for India)
    if mobile_number.startswith('91') and len(mobile_number) == 12:
        mobile_number = mobile_number[2:]
    
    # Validate mobile number format
    if not validate_mobile_number(mobile_number):
        return Response({
            'success': False,
            'message': 'Invalid mobile number. Please enter a valid 10-digit Indian mobile number starting with 6, 7, 8, or 9'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Generate OTP
        otp_code = OTP.generate_otp()
        
        # Save OTP to database
        otp_obj = OTP.objects.create(
            mobile_number=mobile_number,
            otp_code=otp_code
        )
        
        print(f"Generated OTP: {otp_code} for mobile: {mobile_number}")  # Debug log
        
        # Send SMS using MSG91
        sms_service = MSG91Service()
        result = sms_service.send_otp_sms(mobile_number, otp_code)
        
        if result['success']:
            return Response({
                'success': True,
                'message': 'OTP sent successfully to your mobile number',
                'mobile_number': mobile_number,
                'otp_id': otp_obj.id,  # Can be used for reference
                'debug_otp': otp_code  # Remove this in production!
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'message': result['message'],
                'error_details': result.get('error'),
                'debug_otp': otp_code  # For testing even if SMS fails
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    except Exception as e:
        return Response({
            'success': False,
            'message': 'Server error occurred while sending OTP',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
def verify_otp(request):
    """Verify OTP entered by user"""
    mobile_number = request.data.get('mobile_number')
    otp_code = request.data.get('otp')
    
    if not mobile_number or not otp_code:
        return Response({
            'success': False,
            'message': 'Both mobile number and OTP are required'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    # Clean mobile number
    mobile_number = re.sub(r'[^\d]', '', mobile_number)
    if mobile_number.startswith('91') and len(mobile_number) == 12:
        mobile_number = mobile_number[2:]
    
    try:
        # Find the most recent valid OTP for this mobile number
        otp_obj = OTP.objects.filter(
            mobile_number=mobile_number,
            otp_code=otp_code,
            is_verified=False
        ).latest('created_at')
        
        # Check if OTP is still valid (not expired)
        if not otp_obj.is_valid():
            return Response({
                'success': False,
                'message': 'OTP has expired. Please request a new OTP.',
                'expired': True
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Mark OTP as verified
        otp_obj.is_verified = True
        otp_obj.save()
        
        # Create or get user
        user, created = User.objects.get_or_create(
            mobile_number=mobile_number,
            defaults={
                'username': mobile_number,  # Using mobile as username
                'is_mobile_verified': True
            }
        )
        
        # If user exists but wasn't verified, mark as verified
        if not created and not user.is_mobile_verified:
            user.is_mobile_verified = True
            user.save()
        
        return Response({
            'success': True,
            'message': 'OTP verified successfully!',
            'user_id': user.id,
            'mobile_number': user.mobile_number,
            'is_new_user': created,
            'next_step': 'user_type_selection'  # Frontend knows what to show next
        }, status=status.HTTP_200_OK)
        
    except OTP.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Invalid OTP. Please check the OTP and try again.',
            'invalid_otp': True
        }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        return Response({
            'success': False,
            'message': 'Server error occurred during OTP verification',
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)