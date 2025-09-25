# apps/authentication/utils/version_handler.py

class APIVersionHandler:
    """
    Handle version-specific logic for authentication APIs
    """
    
    @staticmethod
    def get_send_otp_response(result, version):
        """
        Format send OTP response based on API version
        """
        if version == '1':
            return result
        elif version == '2':
            # Future v2 might include additional fields
            response = result.copy()
            response['api_version'] = '2'
            response['timestamp'] = '2024-08-13T10:30:00Z'
            return response
        else:
            return result
    
    @staticmethod
    def get_verify_otp_response(jwt_response, version):
        """
        Format verify OTP response based on API version
        """
        if version == '1':
            return jwt_response
        elif version == '2':
            # Future v2 might have different response structure
            response = jwt_response.copy()
            response['api_version'] = '2'
            response['token_type'] = 'Bearer'
            # Maybe include user profile in v2
            response['user_profile'] = {
                'mobile': jwt_response['mobile'],
                'verified': True
            }
            return response
        else:
            return jwt_response
    
    @staticmethod
    def validate_otp_format(otp, version):
        """
        Validate OTP format based on API version
        """
        if version == '1':
            # 1: 6-digit OTP
            return str(otp).isdigit() and len(str(otp)) == 6
        elif version == '2':
            # Future 2 might support alphanumeric OTP
            return len(str(otp)) >= 4 and len(str(otp)) <= 8
        else:
            return str(otp).isdigit() and len(str(otp)) == 6

# Usage in views:
# from apps.authentication.utils.version_handler import APIVersionHandler
# 
# def send_otp_api(request, version=None):
#     # ... existing logic ...
#     result = otp_service.send_otp_sms(mobile_number)
#     
#     # Format response based on version
#     version = getattr(request, 'version', '1')
#     formatted_result = APIVersionHandler.get_send_otp_response(result, version)
#     
#     return Response(formatted_result, status=status_code)