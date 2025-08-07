import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

class MSG91Service:
    BASE_URL = "https://control.msg91.com/api/v5/sms/"
    
    def __init__(self):
        self.authkey = settings.MSG91_AUTHKEY
        self.sender_id = settings.MSG91_SENDER_ID
        self.route = settings.MSG91_ROUTE
        self.country = settings.MSG91_COUNTRY
    
    def send_otp_sms(self, mobile_number, otp):
        """Send OTP SMS to mobile number"""
        message = f"Your OTP for verification is {otp}. Valid for 10 minutes. Do not share with anyone."
        
        payload = {
            'authkey': self.authkey,
            'mobiles': f"91{mobile_number}",  # Adding India country code
            'message': message,
            'sender': self.sender_id,
            'route': self.route,
            'country': self.country
        }
        
        try:
            response = requests.post(self.BASE_URL, json=payload)
            
            # Debug logging
            print(f"MSG91 Request URL: {self.BASE_URL}")
            print(f"MSG91 Request Payload: {payload}")
            print(f"MSG91 Response Status: {response.status_code}")
            print(f"MSG91 Response Body: {response.text}")
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'message': 'OTP sent successfully',
                    'response': response.text
                }
            else:
                return {
                    'success': False,
                    'message': f'Failed to send SMS. Status: {response.status_code}',
                    'error': response.text
                }
                
        except Exception as e:
            logger.error(f"SMS sending failed: {str(e)}")
            return {
                'success': False,
                'message': 'SMS service error',
                'error': str(e)
            }