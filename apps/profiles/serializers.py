# apps/profiles/serializers.py
from rest_framework import serializers
from django.db import transaction
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
import requests
import os
import hashlib
from urllib.parse import urlparse

from apps.profiles.models import (
    UserProfile, DriverServiceData, PropertyServiceData,
    SOSServiceData, ServicePortfolioImage, Wallet, WalletTransaction
)
from apps.work_categories.models import (
    WorkCategory, WorkSubCategory, UserWorkSelection,
    UserWorkSubCategory, WorkPortfolioImage
)
from apps.verification.models import AadhaarVerification, LicenseVerification


class FlexibleImageField(serializers.Field):
    """
    Custom field that accepts:
    - File uploads (ImageField behavior)
    - None/null values
    - Dict objects with 'index' and 'image' keys
    - URL strings
    """
    def to_internal_value(self, data):
        # Allow None
        if data is None or data == '':
            return None

        # Allow dict objects (for indexed operations)
        if isinstance(data, dict):
            return data

        # Allow file uploads
        if hasattr(data, 'read'):
            return data

        # Allow URL strings
        if isinstance(data, str):
            return data

        # Unknown type - return as is and let parent serializer handle
        return data

    def to_representation(self, value):
        # Not used for input, but required
        return value


class FlexibleStringField(serializers.Field):
    """
    Custom field that accepts:
    - String values
    - None/null values
    - Dict objects with 'index' and value keys (for indexed operations)

    Used for languages and sub_category_ids to support add/replace/delete operations
    """
    def to_internal_value(self, data):
        # Allow None
        if data is None or data == '':
            return None

        # Allow dict objects (for indexed operations like {"index": 0, "language": "English"})
        if isinstance(data, dict):
            return data

        # Allow string values
        if isinstance(data, str):
            return data

        # Unknown type - return as is and let parent serializer handle
        return data

    def to_representation(self, value):
        # Not used for input, but required
        return value


def download_image_from_url(url, timeout=10):
    """
    Download image from URL and return ContentFile

    Args:
        url: Image URL to download
        timeout: Request timeout in seconds

    Returns:
        ContentFile object or None if download fails
    """
    try:
        response = requests.get(url, timeout=timeout, stream=True)
        response.raise_for_status()

        # Get filename from URL
        parsed_url = urlparse(url)
        filename = os.path.basename(parsed_url.path)

        # If no filename, generate one
        if not filename or '.' not in filename:
            content_type = response.headers.get('content-type', '')
            ext = content_type.split('/')[-1] if '/' in content_type else 'jpg'
            filename = f'downloaded_image.{ext}'

        # Create ContentFile from response content
        return ContentFile(response.content, name=filename)
    except Exception as e:
        print(f"Error downloading image from {url}: {str(e)}")
        return None


def is_url_string(value):
    """Check if value is a URL string"""
    if isinstance(value, str):
        return value.startswith('http://') or value.startswith('https://')
    return False


def get_existing_image_url(profile, image_field='profile_photo'):
    """Get existing image URL for comparison"""
    if image_field == 'profile_photo':
        if profile and profile.profile_photo:
            return profile.profile_photo.url
    return None


def get_existing_portfolio_urls(profile):
    """Get all existing portfolio image URLs"""
    if not profile:
        return []

    portfolio_images = profile.service_portfolio_images.all().order_by('image_order')
    return [img.image.url for img in portfolio_images]


def calculate_file_hash(file_obj, chunk_size=8192):
    """
    Calculate MD5 hash of a file object

    Args:
        file_obj: File object to hash
        chunk_size: Size of chunks to read

    Returns:
        MD5 hash string or None if error
    """
    try:
        # Save current position
        current_position = file_obj.tell() if hasattr(file_obj, 'tell') else 0

        # Reset to beginning
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)

        # Calculate hash
        md5_hash = hashlib.md5()
        while True:
            chunk = file_obj.read(chunk_size)
            if not chunk:
                break
            md5_hash.update(chunk)

        # Restore position
        if hasattr(file_obj, 'seek'):
            file_obj.seek(current_position)

        return md5_hash.hexdigest()
    except Exception as e:
        print(f"Error calculating file hash: {str(e)}")
        return None


def files_are_same(file1, file2):
    """
    Compare two file objects by their MD5 hash

    Args:
        file1: First file object
        file2: Second file object

    Returns:
        True if files have same content, False otherwise
    """
    if not file1 or not file2:
        return False

    hash1 = calculate_file_hash(file1)
    hash2 = calculate_file_hash(file2)

    return hash1 == hash2 if hash1 and hash2 else False


def parse_multipart_array_fields(data):
    """
    Convert Flutter's multipart form data format to nested structures.

    Flutter sends:
        portfolio_images[0][index] = 1
        portfolio_images[0][image] = null
        portfolio_images[1] = file
        languages[0] = "English"
        sub_category_ids[0][index] = 1
        sub_category_ids[0][sub_category_id] = "SS0001"

    Converts to:
        portfolio_images = [{"index": 1, "image": null}, file]
        languages = ["English"]
        sub_category_ids = [{"index": 1, "sub_category_id": "SS0001"}]
    """
    result = {}

    # Track which fields need processing
    array_fields = {}  # {field_name: {index: value or {key: value}}}

    # Iterate through all keys in the data
    all_keys = list(data.keys())

    for key in all_keys:
        # Check if it matches array pattern: field[index] or field[index][key]
        if '[' in key and ']' in key:
            # Parse the key structure
            parts = key.replace('[', '|').replace(']', '').split('|')

            if len(parts) == 2:
                # Simple array: field[0] = value
                field_name, index_str = parts
                try:
                    index = int(index_str)
                    if field_name not in array_fields:
                        array_fields[field_name] = {}

                    # Get the value (could be file, string, etc.)
                    value = data.get(key)

                    # Check if this index already has a dict (from nested keys)
                    if index in array_fields[field_name] and isinstance(array_fields[field_name][index], dict):
                        # Already has dict structure from nested keys, skip simple value
                        continue

                    array_fields[field_name][index] = value
                except ValueError:
                    continue

            elif len(parts) == 3:
                # Nested dict: field[0][key] = value
                field_name, index_str, dict_key = parts
                try:
                    index = int(index_str)
                    if field_name not in array_fields:
                        array_fields[field_name] = {}

                    # Initialize as dict if not present or if it was a simple value
                    if index not in array_fields[field_name] or not isinstance(array_fields[field_name][index], dict):
                        array_fields[field_name][index] = {}

                    # Handle special cases for image/file fields
                    value = data.get(key)
                    if value == '' or value == 'null':
                        value = None

                    array_fields[field_name][index][dict_key] = value
                except ValueError:
                    continue

    # Convert indexed dicts to sorted lists
    for field_name, indexed_values in array_fields.items():
        sorted_indices = sorted(indexed_values.keys())
        result[field_name] = [indexed_values[i] for i in sorted_indices]

    return result


class ProfileSetupSerializer(serializers.Serializer):
    """
    Comprehensive serializer for complete profile setup
    Handles provider (worker, driver, properties, SOS) and seeker profiles
    Supports both file uploads and URLs for images (profile_photo and portfolio_images)
    """

    # Basic Profile Fields (Required only on first create)
    user_type = serializers.ChoiceField(choices=['provider', 'seeker'], required=False, allow_null=True)
    service_type = serializers.ChoiceField(
        choices=['worker', 'driver', 'properties', 'SOS'],
        required=False,
        allow_null=True,
        help_text="Required for providers on first create"
    )
    full_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    gender = serializers.ChoiceField(choices=['male', 'female'], required=False, allow_null=True)
    # Supports both file and URL (handled in to_internal_value)
    profile_photo = serializers.ImageField(required=False, allow_null=True)
    # Languages - supports add/replace/delete operations with indices
    # Format: ["English", "Hindi"] for adding, or [{"index": 0, "language": "Spanish"}] for replace/delete
    languages = serializers.ListField(
        child=FlexibleStringField(),
        required=False,
        allow_empty=True,
        help_text="Array of languages spoken, supports indexed operations"
    )

    # Portfolio Images (Required for all providers, max 3)
    # Supports both files and URLs (handled in to_internal_value)
    # Uses custom FlexibleImageField to accept files, URLs, dicts, and null values
    portfolio_images = serializers.ListField(
        child=FlexibleImageField(),
        required=False,
        allow_empty=True,
        max_length=3
    )

    # Worker-specific Fields
    main_category_id = serializers.CharField(required=False, allow_null=True)
    # Sub-category IDs - supports add/replace/delete operations with indices
    # Format: ["SS0001", "SS0002"] for adding, or [{"index": 0, "sub_category_id": "SS0003"}] for replace/delete
    sub_category_ids = serializers.ListField(
        child=FlexibleStringField(),
        required=False,
        allow_empty=True
    )
    years_experience = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    skills = serializers.CharField(required=False, allow_blank=True)

    # Driver-specific Fields
    vehicle_types = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True
    )
    license_number = serializers.CharField(required=False, allow_blank=True, max_length=50)
    vehicle_registration_number = serializers.CharField(required=False, allow_blank=True, max_length=20)
    driving_experience_description = serializers.CharField(required=False, allow_blank=True)

    # Property-specific Fields
    property_types = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True
    )
    property_title = serializers.CharField(required=False, allow_blank=True, max_length=200)
    parking_availability = serializers.ChoiceField(
        choices=['Yes', 'No'],
        required=False,
        allow_blank=True,
        allow_null=True
    )
    furnishing_type = serializers.ChoiceField(
        choices=['Fully Furnished', 'Semi Furnished', 'Unfurnished'],
        required=False,
        allow_blank=True,
        allow_null=True
    )
    property_description = serializers.CharField(required=False, allow_blank=True)

    # SOS/Emergency-specific Fields
    emergency_service_types = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True
    )
    contact_number = serializers.CharField(required=False, allow_blank=True, max_length=15)
    current_location = serializers.CharField(required=False, allow_blank=True)
    emergency_description = serializers.CharField(required=False, allow_blank=True)

    # Verification Fields (Optional)
    aadhaar_number = serializers.CharField(required=False, allow_blank=True, max_length=12)
    license_type = serializers.ChoiceField(
        choices=['driving', 'commercial', 'other'],
        required=False,
        allow_blank=True
    )

    def to_internal_value(self, data):
        """
        Override to handle both file and URL for images
        Convert URLs to files if needed, or keep existing images
        Also handles Flutter's multipart form data format
        """
        try:
            # Make a mutable copy of data
            if hasattr(data, '_mutable'):
                data._mutable = True

            # Parse multipart array fields from Flutter (portfolio_images[0][index], languages[0], etc.)
            parsed_arrays = parse_multipart_array_fields(data)

            # Store parsed arrays in a separate dict to avoid QueryDict issues
            # We'll access these directly instead of through data['field_name']
            data._parsed_arrays = parsed_arrays

            # Debug logging
            for field_name, field_value in parsed_arrays.items():
                if field_name in ['portfolio_images', 'languages', 'sub_category_ids']:
                    print(f"DEBUG: Parsed {field_name} from multipart: {field_value}")
                    print(f"DEBUG: {field_name} types: {[type(item).__name__ for item in field_value]}")

            user = self.context['request'].user

            # Get existing profile if it exists
            try:
                existing_profile = UserProfile.objects.get(user=user)
            except UserProfile.DoesNotExist:
                existing_profile = None
        except Exception as e:
            print(f"ERROR in to_internal_value initialization: {str(e)}")
            import traceback
            traceback.print_exc()
            raise

        # Handle profile_photo (can be file or URL)
        if 'profile_photo' in data and data['profile_photo']:
            profile_photo_value = data['profile_photo']

            # Check if it's a file object (already uploaded)
            if hasattr(profile_photo_value, 'read'):
                # It's a file, check if same as existing file
                if existing_profile and existing_profile.profile_photo:
                    try:
                        # Compare uploaded file with existing file
                        if files_are_same(profile_photo_value, existing_profile.profile_photo):
                            # Files are identical, keep existing
                            data['_keep_profile_photo'] = True
                            data['profile_photo'] = None
                        else:
                            # Files are different, will upload new
                            data['_keep_profile_photo'] = False
                    except Exception as e:
                        # If comparison fails, upload as new
                        print(f"Error comparing profile photos: {str(e)}")
                        data['_keep_profile_photo'] = False
                else:
                    # No existing profile photo, upload as new
                    data['_keep_profile_photo'] = False
            elif is_url_string(profile_photo_value):
                # It's a URL string
                existing_url = get_existing_image_url(existing_profile, 'profile_photo')

                # Compare URLs (normalize them for comparison)
                if existing_url and profile_photo_value.endswith(existing_url):
                    # URL matches existing image, mark to keep it
                    data['_keep_profile_photo'] = True
                    data['profile_photo'] = None  # Will be handled in create()
                else:
                    # URL is different, download and re-upload
                    downloaded_file = download_image_from_url(profile_photo_value)
                    if downloaded_file:
                        data['profile_photo'] = downloaded_file
                        data['_keep_profile_photo'] = False
                    else:
                        raise serializers.ValidationError({
                            'profile_photo': 'Failed to download image from provided URL'
                        })

        # Handle portfolio_images (can be files, URLs, or dict operations)
        # Check if we have parsed arrays from multipart format
        if hasattr(data, '_parsed_arrays') and 'portfolio_images' in data._parsed_arrays:
            try:
                # Use the pre-parsed array data directly
                portfolio_images_data = data._parsed_arrays['portfolio_images']

                print(f"DEBUG: Processing {len(portfolio_images_data)} portfolio images")
                for idx, img in enumerate(portfolio_images_data):
                    print(f"DEBUG: Image {idx} - Type: {type(img)}, IsDict: {isinstance(img, dict)}, HasRead: {hasattr(img, 'read')}")
                    if isinstance(img, dict):
                        print(f"DEBUG: Dict keys: {img.keys()}, index={img.get('index')}, image type={type(img.get('image'))}")

                if portfolio_images_data:
                    existing_portfolio_urls = get_existing_portfolio_urls(existing_profile)
                    existing_portfolio_objs = []

                    # Get existing portfolio file objects for comparison
                    if existing_profile:
                        existing_portfolio_objs = list(existing_profile.service_portfolio_images.all().order_by('image_order'))

                    processed_images = []

                    for img_value in portfolio_images_data:
                        # Case 1: Dict with 'index' key (replace/delete operation)
                        if isinstance(img_value, dict) and 'index' in img_value:
                            # Convert index to int if it's a string
                            index = img_value.get('index')
                            if isinstance(index, str):
                                index = int(index)
                            image_data = img_value.get('image')

                            # Process the image field within the dict
                            if image_data is None or image_data == '':
                                # Delete operation
                                processed_images.append({'index': index, 'image': None})
                            elif hasattr(image_data, 'read'):
                                # File object - replace operation
                                processed_images.append({'index': index, 'image': image_data})
                            elif is_url_string(image_data):
                                # URL string - download and replace
                                downloaded_file = download_image_from_url(image_data)
                                if downloaded_file:
                                    processed_images.append({'index': index, 'image': downloaded_file})
                                else:
                                    raise serializers.ValidationError({
                                        'portfolio_images': f'Failed to download image from URL for index {index}'
                                    })
                            else:
                                # Unknown image type in dict
                                processed_images.append({'index': index, 'image': None})

                        # Case 2: None/null value (ignore - not valid for add operation)
                        elif img_value is None or img_value == '':
                            # Skip null values that aren't in dict format
                            continue

                        # Case 3: File object (add operation)
                        elif hasattr(img_value, 'read'):
                            # Check if file matches existing (avoid duplicate uploads)
                            file_matches_existing = False
                            for existing_img_obj in existing_portfolio_objs:
                                try:
                                    if files_are_same(img_value, existing_img_obj.image):
                                        # File is identical to existing, skip it
                                        file_matches_existing = True
                                        break
                                except Exception as e:
                                    print(f"Error comparing portfolio image: {str(e)}")
                                    continue

                            if not file_matches_existing:
                                # New file - add it
                                processed_images.append(img_value)

                        # Case 4: URL string (add operation)
                        elif is_url_string(img_value):
                            # Check if URL matches existing
                            url_matches_existing = any(img_value.endswith(existing_url) for existing_url in existing_portfolio_urls)

                            if not url_matches_existing:
                                # URL doesn't match, download and add it
                                downloaded_file = download_image_from_url(img_value)
                                if downloaded_file:
                                    processed_images.append(downloaded_file)
                                else:
                                    raise serializers.ValidationError({
                                        'portfolio_images': 'Failed to download image from provided URL'
                                    })

                    # Set the processed images back into data so DRF can validate them
                    data['portfolio_images'] = processed_images
                    print(f"DEBUG: Set data['portfolio_images'] to {len(processed_images)} items")
            except Exception as e:
                print(f"ERROR processing portfolio_images: {str(e)}")
                import traceback
                traceback.print_exc()
                raise
        elif 'portfolio_images' in data:
            # Standard portfolio images (not from multipart parser)
            # Let DRF handle it normally with getlist
            pass

        # Call parent to_internal_value
        result = super().to_internal_value(data)

        # If we had parsed arrays, manually set them in the result
        # This ensures they're not lost or corrupted by DRF's processing
        if hasattr(data, '_parsed_arrays'):
            if 'portfolio_images' in data._parsed_arrays:
                # Override the result with our pre-processed images
                result['portfolio_images'] = data['portfolio_images']
                print(f"DEBUG: Overriding result['portfolio_images'] with {len(data['portfolio_images'])} pre-processed items")

        # Preserve custom flags
        if '_keep_profile_photo' in data:
            result['_keep_profile_photo'] = data['_keep_profile_photo']

        return result

    def validate(self, attrs):
        """Custom validation for business rules - smart validation for create vs update"""
        user = self.context['request'].user

        # Check if profile already exists (update mode vs create mode)
        try:
            existing_profile = UserProfile.objects.get(user=user)
            is_update = True
        except UserProfile.DoesNotExist:
            existing_profile = None
            is_update = False

        # Store mode in attrs for later use
        attrs['_is_update'] = is_update
        attrs['_existing_profile'] = existing_profile

        # Get user_type from attrs or existing profile
        user_type = attrs.get('user_type')
        if not user_type and existing_profile:
            user_type = existing_profile.user_type

        # Get service_type from attrs or existing profile
        service_type = attrs.get('service_type')
        if not service_type and existing_profile:
            service_type = existing_profile.service_type

        # CREATE MODE: Validate required fields
        if not is_update:
            # Basic required fields for first-time setup
            required_basic_fields = {
                'user_type': 'User type is required for profile setup',
                'full_name': 'Full name is required for profile setup',
                'date_of_birth': 'Date of birth is required for profile setup',
                'gender': 'Gender is required for profile setup'
            }

            for field, message in required_basic_fields.items():
                if not attrs.get(field):
                    raise serializers.ValidationError({field: message})

            # Provider-specific validation for create
            if user_type == 'provider':
                if not service_type:
                    raise serializers.ValidationError({
                        'service_type': 'Service type is required for providers'
                    })

                # Portfolio images are no longer required
                portfolio_images = attrs.get('portfolio_images', [])

                # Category fields required on create
                self._validate_category_fields(attrs, is_required=True)

                # Service-specific validation
                if service_type == 'worker':
                    self._validate_worker_fields(attrs, is_required=True)
                elif service_type == 'driver':
                    self._validate_driver_fields(attrs, is_required=True)
                elif service_type == 'properties':
                    self._validate_property_fields(attrs, is_required=True)
                elif service_type == 'SOS':
                    self._validate_sos_fields(attrs, is_required=True)

        # UPDATE MODE: Validate only provided fields
        else:
            # If user tries to change user_type or service_type, validate it's allowed
            # (Currently allowed as per your requirement #2: no protected fields)

            # If provider and updating category/service fields, validate them
            if user_type == 'provider':
                # Only validate category fields if they're being updated
                if 'main_category_id' in attrs or 'sub_category_ids' in attrs:
                    self._validate_category_fields(attrs, is_required=False)

                # Only validate service-specific fields if they're being updated
                if service_type == 'worker' and any(k in attrs for k in ['years_experience', 'skills']):
                    self._validate_worker_fields(attrs, is_required=False)
                elif service_type == 'driver' and any(k in attrs for k in ['vehicle_types', 'license_number', 'vehicle_registration_number', 'driving_experience_description']):
                    self._validate_driver_fields(attrs, is_required=False)
                elif service_type == 'properties' and any(k in attrs for k in ['property_types', 'property_title', 'property_description']):
                    self._validate_property_fields(attrs, is_required=False)
                elif service_type == 'SOS' and any(k in attrs for k in ['emergency_service_types', 'contact_number', 'current_location', 'emergency_description']):
                    self._validate_sos_fields(attrs, is_required=False)

        # Aadhaar validation (applies to both create and update)
        aadhaar_number = attrs.get('aadhaar_number')
        if aadhaar_number:
            if len(aadhaar_number) != 12 or not aadhaar_number.isdigit():
                raise serializers.ValidationError({
                    'aadhaar_number': 'Aadhaar number must be exactly 12 digits'
                })

        return attrs

    def _validate_category_fields(self, attrs, is_required=True):
        """Validate category fields required for all provider types"""
        if is_required:
            required_fields = {
                'main_category_id': 'Main category is required for all providers',
                'sub_category_ids': 'Subcategories are required for all providers'
            }

            for field, message in required_fields.items():
                value = attrs.get(field)
                # Check for None, empty string, or empty list
                if not value or (isinstance(value, list) and len(value) == 0):
                    raise serializers.ValidationError({field: message})

        # Validate main category exists (only if provided)
        main_category_id = attrs.get('main_category_id')
        if main_category_id:
            try:
                main_category = WorkCategory.objects.get(category_code=main_category_id, is_active=True)
                attrs['_main_category'] = main_category
            except WorkCategory.DoesNotExist:
                raise serializers.ValidationError({
                    'main_category_id': f'Invalid main category: {main_category_id}'
                })

            # Validate subcategories (only if provided)
            sub_category_ids = attrs.get('sub_category_ids', [])
            if sub_category_ids:
                # Extract sub_category_id strings from the list (handling both dicts and strings)
                codes_to_validate = []
                for item in sub_category_ids:
                    if isinstance(item, dict):
                        # Dict format: {"index": 0, "sub_category_id": "SS0001"}
                        sub_id = item.get('sub_category_id')
                        if sub_id and sub_id != '':
                            codes_to_validate.append(sub_id)
                    elif isinstance(item, str):
                        # Simple string format: "SS0001"
                        codes_to_validate.append(item)

                # Validate the extracted codes
                if codes_to_validate:
                    valid_subcategories = WorkSubCategory.objects.filter(
                        category=main_category,
                        subcategory_code__in=codes_to_validate,
                        is_active=True
                    )
                    found_codes = [sub.subcategory_code for sub in valid_subcategories]
                    invalid_codes = [code for code in codes_to_validate if code not in found_codes]

                    if invalid_codes:
                        raise serializers.ValidationError({
                            'sub_category_ids': f'Invalid subcategories: {", ".join(invalid_codes)}'
                        })

                    # Store validated subcategories with their codes for later use
                    attrs['_subcategories'] = sub_category_ids  # Keep original format (may include dicts)
                    attrs['_validated_subcategory_objects'] = {sub.subcategory_code: sub for sub in valid_subcategories}

    def _validate_worker_fields(self, attrs, is_required=True):
        """Validate worker-specific required fields"""
        if is_required:
            required_fields = {
                'years_experience': 'Years of experience is required for workers',
                'skills': 'Skills description is required for workers'
            }

            for field, message in required_fields.items():
                value = attrs.get(field)
                if not value and value != 0:  # Allow 0 for years_experience
                    raise serializers.ValidationError({field: message})

    def _validate_driver_fields(self, attrs, is_required=True):
        """Validate driver-specific required fields"""
        if is_required:
            required_fields = {
                'vehicle_types': 'Vehicle types are required for drivers',
                'license_number': 'License number is required for drivers',
                'vehicle_registration_number': 'Vehicle registration number is required for drivers',
                'years_experience': 'Years of experience is required for drivers',
                'driving_experience_description': 'Driving experience description is required for drivers'
            }

            for field, message in required_fields.items():
                if not attrs.get(field):
                    raise serializers.ValidationError({field: message})

    def _validate_property_fields(self, attrs, is_required=True):
        """Validate property-specific required fields"""
        if is_required:
            required_fields = {
                'property_types': 'Property types are required for property services',
                'property_title': 'Property title is required for property services',
                'property_description': 'Property description is required for property services'
            }

            for field, message in required_fields.items():
                if not attrs.get(field):
                    raise serializers.ValidationError({field: message})

    def _validate_sos_fields(self, attrs, is_required=True):
        """Validate SOS/Emergency-specific required fields"""
        if is_required:
            required_fields = {
                'emergency_service_types': 'Emergency service types are required for SOS services',
                'contact_number': 'Contact number is required for SOS services',
                'current_location': 'Current location is required for SOS services',
                'emergency_description': 'Emergency description is required for SOS services'
            }

            for field, message in required_fields.items():
                if not attrs.get(field):
                    raise serializers.ValidationError({field: message})
    
    @transaction.atomic
    def create(self, validated_data):
        """Create or update profile with partial data support"""
        user = self.context['request'].user

        # Check if this is an update
        is_update = validated_data.pop('_is_update', False)
        existing_profile = validated_data.pop('_existing_profile', None)

        # Extract data that needs special handling
        main_category = validated_data.pop('_main_category', None)
        subcategories = validated_data.pop('_subcategories', [])
        portfolio_images = validated_data.pop('portfolio_images', [])
        keep_profile_photo = validated_data.pop('_keep_profile_photo', False)

        # Get user_type and service_type (from validated_data or existing profile)
        user_type = validated_data.get('user_type')
        if not user_type and existing_profile:
            user_type = existing_profile.user_type

        service_type = validated_data.get('service_type')
        if not service_type and existing_profile:
            service_type = existing_profile.service_type

        # Prepare defaults dict for update_or_create
        # For update mode: only include fields that are actually in validated_data
        # For create mode: all fields are required and present
        defaults = {}

        if 'full_name' in validated_data:
            defaults['full_name'] = validated_data['full_name']
        elif existing_profile:
            defaults['full_name'] = existing_profile.full_name

        if 'date_of_birth' in validated_data:
            defaults['date_of_birth'] = validated_data['date_of_birth']
        elif existing_profile:
            defaults['date_of_birth'] = existing_profile.date_of_birth

        if 'gender' in validated_data:
            defaults['gender'] = validated_data['gender']
        elif existing_profile:
            defaults['gender'] = existing_profile.gender

        # Handle profile photo
        if keep_profile_photo and existing_profile and existing_profile.profile_photo:
            defaults['profile_photo'] = existing_profile.profile_photo
        elif 'profile_photo' in validated_data and validated_data['profile_photo']:
            defaults['profile_photo'] = validated_data['profile_photo']
        elif existing_profile and existing_profile.profile_photo:
            defaults['profile_photo'] = existing_profile.profile_photo

        # user_type and service_type
        defaults['user_type'] = user_type
        defaults['service_type'] = service_type

        # Languages - handle indexed operations (add/replace/delete)
        if 'languages' in validated_data:
            languages_data = validated_data.get('languages', [])

            # Get existing languages as a list
            existing_languages = []
            if existing_profile and existing_profile.languages:
                existing_languages = [lang.strip() for lang in existing_profile.languages.split(',') if lang.strip()]

            # Separate operations: replace/delete (with index) vs add (without index)
            replace_delete_operations = []
            add_languages = []

            for lang_data in languages_data:
                if isinstance(lang_data, dict) and 'index' in lang_data:
                    # Operation with index: replace or delete
                    replace_delete_operations.append(lang_data)
                elif lang_data and not isinstance(lang_data, dict):
                    # Simple string without index: add new language
                    add_languages.append(lang_data)

            # Step 1: Process replace/delete operations (with indices)
            for operation in replace_delete_operations:
                index = operation.get('index')
                new_language = operation.get('language')

                if 0 <= index < len(existing_languages):
                    if new_language is None or new_language == '':
                        # Delete operation: remove language at this index
                        existing_languages.pop(index)
                    else:
                        # Replace operation: update language at this index
                        existing_languages[index] = new_language
                elif new_language and new_language != '':
                    # Index doesn't exist, add new language (append)
                    existing_languages.append(new_language)

            # Step 2: Add new languages (without indices, avoiding duplicates)
            for new_language in add_languages:
                if new_language not in existing_languages:
                    existing_languages.append(new_language)

            # Convert back to comma-separated string
            defaults['languages'] = ','.join(existing_languages) if existing_languages else ''
        elif existing_profile:
            defaults['languages'] = existing_profile.languages

        # These are always set
        defaults['profile_complete'] = False  # Will be updated after service data creation
        defaults['can_access_app'] = False

        # Create or update UserProfile
        profile, created = UserProfile.objects.update_or_create(
            user=user,
            defaults=defaults
        )

        # Handle service-specific data for providers
        if user_type == 'provider':
            # Update work selection data only if category fields are provided
            if main_category is not None or subcategories:
                self._create_worker_data(profile, validated_data, main_category, subcategories)

            # Update service-specific data only if relevant fields are provided
            if service_type == 'driver':
                # Check if any driver fields are provided
                driver_fields = ['vehicle_types', 'license_number', 'vehicle_registration_number', 'years_experience', 'driving_experience_description']
                if any(field in validated_data for field in driver_fields):
                    self._create_driver_data(profile, validated_data)
            elif service_type == 'properties':
                # Check if any property fields are provided
                property_fields = ['property_types', 'property_title', 'parking_availability', 'furnishing_type', 'property_description']
                if any(field in validated_data for field in property_fields):
                    self._create_property_data(profile, validated_data)
            elif service_type == 'SOS':
                # Check if any SOS fields are provided
                sos_fields = ['emergency_service_types', 'contact_number', 'current_location', 'emergency_description']
                if any(field in validated_data for field in sos_fields):
                    self._create_sos_data(profile, validated_data)

            # Handle portfolio images only if they are provided
            if portfolio_images:
                # Get existing portfolio images ordered by image_order
                existing_imgs = []
                if existing_profile:
                    existing_imgs = list(existing_profile.service_portfolio_images.all().order_by('image_order'))

                # Separate operations: replace/delete (with index) vs add (without index)
                replace_delete_operations = []
                add_images = []

                for img_data in portfolio_images:
                    if isinstance(img_data, dict) and 'index' in img_data:
                        # Operation with index: replace or delete
                        replace_delete_operations.append(img_data)
                    elif img_data is not None:
                        # Simple file without index: add new image
                        add_images.append(img_data)

                # Step 1: Process replace/delete operations (with indices)
                for operation in replace_delete_operations:
                    index = operation.get('index')
                    new_image = operation.get('image')

                    print(f"DEBUG: Processing operation - index={index}, image type={type(new_image)}")

                    # Find existing image at this index
                    existing_at_index = next((img for img in existing_imgs if img.image_order == index), None)

                    if new_image is None and existing_at_index:
                        # Delete operation: remove image at this index
                        print(f"DEBUG: Deleting image at index {index}")
                        existing_at_index.delete()
                        existing_imgs.remove(existing_at_index)  # Remove from our tracking list
                    elif new_image is not None and existing_at_index:
                        # Replace operation: update image at this index
                        # Verify new_image is actually a file object
                        if hasattr(new_image, 'read') or hasattr(new_image, 'file'):
                            print(f"DEBUG: Replacing image at index {index}")
                            existing_at_index.image = new_image
                            existing_at_index.save()
                        else:
                            print(f"ERROR: new_image at index {index} is not a valid file: {type(new_image)}")
                    elif new_image is not None and not existing_at_index:
                        # Index doesn't exist, create new image with specified index
                        # Verify new_image is actually a file object
                        if hasattr(new_image, 'read') or hasattr(new_image, 'file'):
                            print(f"DEBUG: Creating new image at index {index}")
                            ServicePortfolioImage.objects.create(
                                user_profile=profile,
                                image=new_image,
                                image_order=index
                            )
                        else:
                            print(f"ERROR: new_image for new index {index} is not a valid file: {type(new_image)}")

                # Step 2: Add new images (without indices)
                # Calculate next available order
                if existing_imgs:
                    # Get the maximum order from remaining images
                    max_order = max(img.image_order for img in existing_imgs)
                    next_order = max_order + 1
                else:
                    # No existing images, start from 0
                    next_order = 0

                for new_image in add_images:
                    ServicePortfolioImage.objects.create(
                        user_profile=profile,
                        image=new_image,
                        image_order=next_order
                    )
                    next_order += 1

        # Handle verification data
        self._handle_verification_data(profile, validated_data, service_type)

        # Update profile completion status
        profile.check_profile_completion()

        return profile

    def _create_worker_data(self, profile, validated_data, main_category, subcategories):
        """Create worker-specific data"""
        work_selection, _ = UserWorkSelection.objects.update_or_create(
            user=profile,
            defaults={
                'main_category': main_category,
                'years_experience': validated_data.get('years_experience', 0),
                'skills': validated_data.get('skills', '')
            }
        )

        # Get the validated subcategory objects mapping
        validated_subcategory_objects = validated_data.get('_validated_subcategory_objects', {})

        # Check if we have subcategory indices for targeted updates
        has_indices = False
        subcategory_indices = {}

        # Process subcategories with indices if they're in dict format
        for sub_data in subcategories:
            if isinstance(sub_data, dict) and 'index' in sub_data:
                has_indices = True
                index = sub_data.get('index')
                sub_category_id = sub_data.get('sub_category_id')

                # Get the subcategory object from validated objects
                if sub_category_id and sub_category_id in validated_subcategory_objects:
                    subcategory = validated_subcategory_objects[sub_category_id]
                elif sub_category_id is None or sub_category_id == '':
                    subcategory = None
                else:
                    continue  # Invalid subcategory, skip

                subcategory_indices[index] = subcategory

        if has_indices:
            # Handle indexed subcategories (replace, add, or delete)
            existing_subs = list(UserWorkSubCategory.objects.filter(user_work_selection=work_selection).order_by('id'))

            for index, subcategory in subcategory_indices.items():
                if index < len(existing_subs):
                    # Index exists
                    if subcategory is None:
                        # Delete subcategory at this index
                        existing_subs[index].delete()
                    else:
                        # Replace subcategory at this index
                        existing_subs[index].sub_category = subcategory
                        existing_subs[index].save()
                elif subcategory is not None:
                    # Add new subcategory
                    UserWorkSubCategory.objects.create(
                        user_work_selection=work_selection,
                        sub_category=subcategory
                    )
        else:
            # No indices specified, add new subcategories without replacing existing ones
            existing_sub_ids = set(UserWorkSubCategory.objects.filter(
                user_work_selection=work_selection
            ).values_list('sub_category_id', flat=True))

            # Process simple string subcategories (add new ones only)
            for sub_data in subcategories:
                if isinstance(sub_data, str):
                    # Get the subcategory object from validated objects
                    if sub_data in validated_subcategory_objects:
                        subcategory = validated_subcategory_objects[sub_data]
                        if subcategory.id not in existing_sub_ids:
                            UserWorkSubCategory.objects.create(
                                user_work_selection=work_selection,
                                sub_category=subcategory
                            )

    def _create_driver_data(self, profile, validated_data):
        """Create driver-specific data"""
        DriverServiceData.objects.update_or_create(
            user_profile=profile,
            defaults={
                'vehicle_types': ','.join(validated_data.get('vehicle_types', [])),
                'license_number': validated_data.get('license_number', ''),
                'vehicle_registration_number': validated_data.get('vehicle_registration_number', ''),
                'years_experience': validated_data.get('years_experience', 0),
                'driving_experience_description': validated_data.get('driving_experience_description', '')
            }
        )

    def _create_property_data(self, profile, validated_data):
        """Create property-specific data"""
        PropertyServiceData.objects.update_or_create(
            user_profile=profile,
            defaults={
                'property_types': ','.join(validated_data.get('property_types', [])),
                'property_title': validated_data.get('property_title', ''),
                'parking_availability': validated_data.get('parking_availability'),
                'furnishing_type': validated_data.get('furnishing_type'),
                'property_description': validated_data.get('property_description', '')
            }
        )

    def _create_sos_data(self, profile, validated_data):
        """Create SOS/Emergency-specific data"""
        SOSServiceData.objects.update_or_create(
            user_profile=profile,
            defaults={
                'emergency_service_types': ','.join(validated_data.get('emergency_service_types', [])),
                'contact_number': validated_data.get('contact_number', ''),
                'current_location': validated_data.get('current_location', ''),
                'emergency_description': validated_data.get('emergency_description', '')
            }
        )

    def _handle_verification_data(self, profile, validated_data, service_type):
        """Handle verification data creation"""
        aadhaar_number = validated_data.get('aadhaar_number')
        if aadhaar_number:
            AadhaarVerification.objects.update_or_create(
                user=profile,
                defaults={
                    'aadhaar_number': aadhaar_number,
                    'status': 'pending',
                    'can_skip': True
                }
            )

        license_number = validated_data.get('license_number')
        if license_number:
            is_driver = service_type == 'driver'
            LicenseVerification.objects.update_or_create(
                user=profile,
                defaults={
                    'license_number': license_number,
                    'license_type': validated_data.get('license_type', 'driving'),
                    'status': 'pending',
                    'is_required': is_driver
                }
            )


class ProfileResponseSerializer(serializers.ModelSerializer):
    """Serializer for profile response data"""
    age = serializers.ReadOnlyField()
    mobile_number = serializers.ReadOnlyField()
    profile_photo = serializers.SerializerMethodField()
    portfolio_images = serializers.SerializerMethodField()

    # Service-specific data fields
    service_data = serializers.SerializerMethodField()

    # Add languages as method field
    languages = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = [
            'id', 'full_name', 'user_type', 'service_type', 'gender', 'date_of_birth', 'age',
            'profile_photo', 'profile_complete', 'can_access_app',
            'mobile_number', 'languages', 'provider_id',
            'portfolio_images', 'service_data',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'age', 'mobile_number', 'provider_id', 'created_at', 'updated_at']

    def get_languages(self, obj):
        """Convert comma-separated languages to array"""
        if obj.languages:
            return [lang.strip() for lang in obj.languages.split(',') if lang.strip()]
        return []

    def get_profile_photo(self, obj):
        """Get full URL for profile photo"""
        if obj.profile_photo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.profile_photo.url)
            return obj.profile_photo.url
        return None

    def get_portfolio_images(self, obj):
        """Get portfolio images URLs"""
        images = obj.service_portfolio_images.all().order_by('image_order')
        request = self.context.get('request')

        image_urls = []
        for img in images:
            if request:
                image_urls.append(request.build_absolute_uri(img.image.url))
            else:
                image_urls.append(img.image.url)
        return image_urls

    def get_service_data(self, obj):
        """Get service-specific data based on service type"""
        if obj.user_type != 'provider' or not obj.service_type:
            return None

        if obj.service_type == 'worker':
            return self._get_worker_data(obj)
        elif obj.service_type == 'driver':
            return self._get_driver_data(obj)
        elif obj.service_type == 'properties':
            return self._get_property_data(obj)
        elif obj.service_type == 'SOS':
            return self._get_sos_data(obj)

        return None

    def _get_worker_data(self, obj):
        """Get worker-specific data"""
        if hasattr(obj, 'work_selection') and obj.work_selection:
            work_selection = obj.work_selection
            subcategories = work_selection.selected_subcategories.all()

            return {
                'main_category_id': work_selection.main_category.category_code,
                'main_category_name': work_selection.main_category.display_name,
                'sub_category_ids': [sub.sub_category.subcategory_code for sub in subcategories],
                'sub_category_names': [sub.sub_category.display_name for sub in subcategories],
                'years_experience': work_selection.years_experience,
                'skills': work_selection.skills
            }
        return None

    def _get_driver_data(self, obj):
        """Get driver-specific data including category data"""
        data = {}

        # Get category data from work selection
        if hasattr(obj, 'work_selection') and obj.work_selection:
            work_selection = obj.work_selection
            subcategories = work_selection.selected_subcategories.all()
            data.update({
                'main_category_id': work_selection.main_category.category_code,
                'sub_category_ids': [sub.sub_category.subcategory_code for sub in subcategories],
                'years_experience': work_selection.years_experience,
                'skills': work_selection.skills
            })

        # Get driver-specific data
        if hasattr(obj, 'driver_service') and obj.driver_service:
            driver_data = obj.driver_service
            data.update({
                'vehicle_types': driver_data.vehicle_types.split(',') if driver_data.vehicle_types else [],
                'license_number': driver_data.license_number,
                'vehicle_registration_number': driver_data.vehicle_registration_number,
                'driving_experience_description': driver_data.driving_experience_description
            })

        return data if data else None

    def _get_property_data(self, obj):
        """Get property-specific data including category data"""
        data = {}

        # Get category data from work selection
        if hasattr(obj, 'work_selection') and obj.work_selection:
            work_selection = obj.work_selection
            subcategories = work_selection.selected_subcategories.all()
            data.update({
                'main_category_id': work_selection.main_category.category_code,
                'sub_category_ids': [sub.sub_category.subcategory_code for sub in subcategories],
                'years_experience': work_selection.years_experience,
                'skills': work_selection.skills
            })

        # Get property-specific data
        if hasattr(obj, 'property_service') and obj.property_service:
            property_data = obj.property_service
            data.update({
                'property_types': property_data.property_types.split(',') if property_data.property_types else [],
                'property_title': property_data.property_title,
                'parking_availability': property_data.parking_availability,
                'furnishing_type': property_data.furnishing_type,
                'property_description': property_data.property_description
            })

        return data if data else None

    def _get_sos_data(self, obj):
        """Get SOS/Emergency-specific data including category data"""
        data = {}

        # Get category data from work selection
        if hasattr(obj, 'work_selection') and obj.work_selection:
            work_selection = obj.work_selection
            subcategories = work_selection.selected_subcategories.all()
            data.update({
                'main_category_id': work_selection.main_category.category_code,
                'sub_category_ids': [sub.sub_category.subcategory_code for sub in subcategories],
                'years_experience': work_selection.years_experience,
                'skills': work_selection.skills
            })

        # Get SOS-specific data
        if hasattr(obj, 'sos_service') and obj.sos_service:
            sos_data = obj.sos_service
            data.update({
                'emergency_service_types': sos_data.emergency_service_types.split(',') if sos_data.emergency_service_types else [],
                'contact_number': sos_data.contact_number,
                'current_location': sos_data.current_location,
                'emergency_description': sos_data.emergency_description
            })

        return data if data else None


class WalletTransactionSerializer(serializers.ModelSerializer):
    """Serializer for wallet transaction details"""

    class Meta:
        model = WalletTransaction
        fields = [
            'id',
            'transaction_type',
            'amount',
            'description',
            'balance_after',
            'created_at'
        ]
        read_only_fields = fields


class WalletSerializer(serializers.ModelSerializer):
    """Serializer for wallet details"""
    is_online_subscription_active = serializers.SerializerMethodField()
    online_subscription_time_remaining = serializers.SerializerMethodField()
    recent_transactions = serializers.SerializerMethodField()

    class Meta:
        model = Wallet
        fields = [
            'id',
            'balance',
            'currency',
            'last_online_payment_at',
            'online_subscription_expires_at',
            'is_online_subscription_active',
            'online_subscription_time_remaining',
            'recent_transactions',
            'created_at',
            'updated_at'
        ]
        read_only_fields = fields

    def get_is_online_subscription_active(self, obj):
        """Check if online subscription is currently active"""
        return obj.is_online_subscription_active()

    def get_online_subscription_time_remaining(self, obj):
        """Get time remaining in 'Xh Ym' format for online subscription, or None if expired/not active"""
        from django.utils import timezone

        if obj.online_subscription_expires_at:
            now = timezone.now()
            if now < obj.online_subscription_expires_at:
                time_diff = obj.online_subscription_expires_at - now
                total_seconds = int(time_diff.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                return f"{hours}h {minutes}m"
        return None

    def get_recent_transactions(self, obj):
        """Get recent transactions (last 10)"""
        transactions = obj.transactions.all()[:10]
        return WalletTransactionSerializer(transactions, many=True).data


class RoleSwitchSerializer(serializers.Serializer):
    """
    Serializer for switching user roles between seeker and provider.

    Validates and processes role switching requests while ensuring:
    - User has no active work orders
    - User is not currently active for work (if provider)
    - Target role is valid
    - Only requires new_user_type field
    """
    new_user_type = serializers.ChoiceField(
        choices=['seeker', 'provider'],
        required=True,
        help_text="Target user type to switch to"
    )

    def validate(self, attrs):
        """Validate role switch request"""
        from apps.profiles.utils import can_switch_role

        request = self.context.get('request')
        user_profile = request.user.profile

        new_user_type = attrs.get('new_user_type')

        # Check if switching to same role
        if user_profile.user_type == new_user_type:
            raise serializers.ValidationError({'error': f'You are already a {new_user_type}.'})

        # Validate new_user_type value
        if new_user_type not in ['seeker', 'provider']:
            raise serializers.ValidationError({'error': 'Invalid user type. Must be either seeker or provider.'})

        # Check if user can switch roles (no active work orders, etc.)
        can_switch, reason = can_switch_role(user_profile)
        if not can_switch:
            raise serializers.ValidationError({'error': reason})

        # Store user_profile in validated data for use in save()
        attrs['user_profile'] = user_profile

        return attrs

    def save(self):
        """Perform the role switch"""
        from django.utils import timezone
        from apps.profiles.models import RoleSwitchHistory, Wallet

        user_profile = self.validated_data['user_profile']
        new_user_type = self.validated_data['new_user_type']

        # Store previous role
        previous_user_type = user_profile.user_type

        # Update user profile
        user_profile.previous_user_type = previous_user_type
        user_profile.user_type = new_user_type
        user_profile.role_switch_count += 1
        user_profile.last_role_switch_date = timezone.now()

        # Handle provider-specific setup
        if new_user_type == 'provider':
            # Keep existing service_type (it's preserved from when they were provider before)
            # Generate provider_id if not exists (will be auto-generated by save method)
            # Create wallet if it doesn't exist
            if not hasattr(user_profile, 'wallet'):
                Wallet.objects.create(user_profile=user_profile)

        # Set is_active_for_work to False when switching roles
        user_profile.is_active_for_work = False

        # Profile completion will need to be re-evaluated
        # Don't auto-set to False - let check_profile_completion handle it
        user_profile.save()

        # Re-check profile completion status
        user_profile.check_profile_completion()

        # Create history record
        RoleSwitchHistory.objects.create(
            user_profile=user_profile,
            from_user_type=previous_user_type,
            to_user_type=new_user_type
        )

        return user_profile