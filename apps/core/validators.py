from django.core.exceptions import ValidationError
import re

def validate_aadhaar_number(value):
    """Validate Aadhaar number format"""
    # Remove spaces and check if it's 12 digits
    aadhaar = re.sub(r'\s+', '', value)
    if not re.match(r'^\d{12}$', aadhaar):
        raise ValidationError('Aadhaar number must be 12 digits.')
    return aadhaar

def validate_license_number(value):
    """Basic license number validation"""
    if len(value.strip()) < 5:
        raise ValidationError('License number must be at least 5 characters.')