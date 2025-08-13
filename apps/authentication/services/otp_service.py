# services/otp_service.py

class MSG91OTPService:
    def __init__(self):
        # Fixed dummy OTP for all users
        self.dummy_otp = "123456"
    
    def generate_otp(self):
        """Generate fixed dummy OTP"""
        return self.dummy_otp
    
    def clean_mobile_number(self, mobile_number):
        """Clean and validate mobile number"""
        # Convert to string and remove all non-numeric characters except +
        mobile = str(mobile_number).strip()
        
        # Remove +91 country code if present
        if mobile.startswith('+91'):
            mobile = mobile[3:]
        elif mobile.startswith('91') and len(mobile) == 12:
            mobile = mobile[2:]
        elif mobile.startswith('0') and len(mobile) == 11:
            mobile = mobile[1:]
        
        # Remove any remaining non-numeric characters
        mobile = ''.join(filter(str.isdigit, mobile))
        
        return mobile
    
    def validate_mobile_number(self, mobile_number):
        """Validate if mobile number is 10 digits"""
        cleaned_mobile = self.clean_mobile_number(mobile_number)
        return len(cleaned_mobile) == 10 and cleaned_mobile.isdigit()
    
    def validate_otp(self, otp):
        """Validate if OTP is 6 digits"""
        return str(otp).isdigit() and len(str(otp)) == 6
    
    def send_otp_sms(self, mobile_number):
        """Send dummy OTP (no actual SMS)"""
        
        if not self.validate_mobile_number(mobile_number):
            return {"status": "error", "message": "Please enter a valid 10-digit mobile number"}
        
        mobile = self.clean_mobile_number(mobile_number)
        
        # Always return success for dummy implementation
        return {
            "status": "success",
            "message": "OTP sent successfully",
            "mobile": mobile
        }
    
    def verify_otp(self, mobile_number, entered_otp):
        """Verify the entered OTP against dummy OTP"""
        # Validate inputs
        if not self.validate_mobile_number(mobile_number):
            return {
                "status": "error",
                "message": "Please enter a valid 10-digit mobile number"
            }
        
        if not self.validate_otp(entered_otp):
            return {
                "status": "error",
                "message": "Please enter a valid 6-digit OTP"
            }
        
        # Clean mobile number
        mobile = self.clean_mobile_number(mobile_number)
        
        # Verify against dummy OTP
        if str(entered_otp) == self.dummy_otp:
            return {
                "status": "success",
                "message": "OTP verified successfully",
                "mobile": f"******{mobile[-4:]}"
            }
        else:
            return {
                "status": "error",
                "message": "Invalid OTP. Please check and try again."
            }
    
    def resend_otp(self, mobile_number):
        """Resend dummy OTP"""
        result = self.send_otp_sms(mobile_number)
        if result["status"] == "success":
            result["message"] = "OTP resent successfully to your mobile number"
        return result