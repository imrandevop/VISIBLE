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
    SOSServiceData, ServicePortfolioImage
)
from apps.work_categories.models import (
    WorkCategory, WorkSubCategory, UserWorkSelection,
    UserWorkSubCategory, WorkPortfolioImage
)
from apps.verification.models import AadhaarVerification, LicenseVerification


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
        while chunk := file_obj.read(chunk_size):
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


class ProfileSetupSerializer(serializers.Serializer):
    """
    Comprehensive serializer for complete profile setup
    Handles provider (worker, driver, properties, SOS) and seeker profiles
    Supports both file uploads and URLs for images (profile_photo and portfolio_images)
    """

    # Basic Profile Fields (Required for all)
    user_type = serializers.ChoiceField(choices=['provider', 'seeker'])
    service_type = serializers.ChoiceField(
        choices=['worker', 'driver', 'properties', 'SOS'],
        required=False,
        allow_null=True,
        help_text="Required for providers"
    )
    full_name = serializers.CharField(max_length=100)
    date_of_birth = serializers.DateField()
    gender = serializers.ChoiceField(choices=['male', 'female'])
    # Changed to support both file and URL string
    profile_photo = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    languages = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Array of languages spoken"
    )

    # Portfolio Images (Required for all providers, max 3)
    # Changed to support both files and URL strings
    portfolio_images = serializers.ListField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        allow_empty=True,
        max_length=3
    )

    # Worker-specific Fields
    main_category_id = serializers.CharField(required=False, allow_null=True)
    sub_category_ids = serializers.ListField(
        child=serializers.CharField(),
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
        """
        # Make a mutable copy of data
        if hasattr(data, '_mutable'):
            data._mutable = True

        user = self.context['request'].user

        # Get existing profile if it exists
        try:
            existing_profile = UserProfile.objects.get(user=user)
        except UserProfile.DoesNotExist:
            existing_profile = None

        # Handle profile_photo (can be file or URL)
        if 'profile_photo' in data and data['profile_photo']:
            profile_photo_value = data['profile_photo']

            # Check if it's a file object (already uploaded)
            if hasattr(profile_photo_value, 'read'):
                # It's a file, keep as is
                pass
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

        # Handle portfolio_images (can be files or URLs)
        if 'portfolio_images' in data:
            portfolio_images_data = data.getlist('portfolio_images') if hasattr(data, 'getlist') else data.get('portfolio_images', [])

            if portfolio_images_data:
                existing_portfolio_urls = get_existing_portfolio_urls(existing_profile)
                processed_images = []
                keep_indices = []

                for index, img_value in enumerate(portfolio_images_data):
                    # Check if it's a file object
                    if hasattr(img_value, 'read'):
                        processed_images.append(img_value)
                    elif is_url_string(img_value):
                        # It's a URL string
                        url_matches_existing = False

                        # Check if this URL matches any existing portfolio image
                        for existing_url in existing_portfolio_urls:
                            if img_value.endswith(existing_url):
                                url_matches_existing = True
                                keep_indices.append(index)
                                processed_images.append(None)  # Placeholder for existing image
                                break

                        if not url_matches_existing:
                            # URL doesn't match, download it
                            downloaded_file = download_image_from_url(img_value)
                            if downloaded_file:
                                processed_images.append(downloaded_file)
                            else:
                                raise serializers.ValidationError({
                                    'portfolio_images': f'Failed to download image from URL at index {index}'
                                })

                data['portfolio_images'] = processed_images
                data['_keep_portfolio_indices'] = keep_indices
                data['_existing_portfolio_urls'] = existing_portfolio_urls

        # Call parent to_internal_value
        # Need to temporarily change field types to handle files properly
        original_profile_photo_field = self.fields['profile_photo']
        original_portfolio_field = self.fields['portfolio_images']

        # Temporarily replace with ImageField for proper validation
        self.fields['profile_photo'] = serializers.ImageField(required=False, allow_null=True)
        self.fields['portfolio_images'] = serializers.ListField(
            child=serializers.ImageField(),
            required=False,
            allow_empty=True,
            max_length=3
        )

        try:
            result = super().to_internal_value(data)
        finally:
            # Restore original fields
            self.fields['profile_photo'] = original_profile_photo_field
            self.fields['portfolio_images'] = original_portfolio_field

        # Preserve custom flags
        if '_keep_profile_photo' in data:
            result['_keep_profile_photo'] = data['_keep_profile_photo']
        if '_keep_portfolio_indices' in data:
            result['_keep_portfolio_indices'] = data['_keep_portfolio_indices']
        if '_existing_portfolio_urls' in data:
            result['_existing_portfolio_urls'] = data['_existing_portfolio_urls']

        return result

    def validate(self, attrs):
        """Custom validation for business rules"""
        user_type = attrs.get('user_type')
        service_type = attrs.get('service_type')

        # Provider validation
        if user_type == 'provider':
            # Service type is required for providers
            if not service_type:
                raise serializers.ValidationError({
                    'service_type': 'Service type is required for providers'
                })

            # Portfolio images required for all provider types
            portfolio_images = attrs.get('portfolio_images', [])
            if not portfolio_images:
                raise serializers.ValidationError({
                    'portfolio_images': 'At least one portfolio image is required for all providers'
                })

            # All provider types need category validation
            self._validate_category_fields(attrs)

            # Service-specific validation
            if service_type == 'worker':
                self._validate_worker_fields(attrs)
            elif service_type == 'driver':
                self._validate_driver_fields(attrs)
            elif service_type == 'properties':
                self._validate_property_fields(attrs)
            elif service_type == 'SOS':
                self._validate_sos_fields(attrs)

        # Aadhaar validation
        aadhaar_number = attrs.get('aadhaar_number')
        if aadhaar_number:
            if len(aadhaar_number) != 12 or not aadhaar_number.isdigit():
                raise serializers.ValidationError({
                    'aadhaar_number': 'Aadhaar number must be exactly 12 digits'
                })

        return attrs

    def _validate_category_fields(self, attrs):
        """Validate category fields required for all provider types"""
        required_fields = {
            'main_category_id': 'Main category is required for all providers',
            'sub_category_ids': 'Subcategories are required for all providers'
        }

        for field, message in required_fields.items():
            value = attrs.get(field)
            # Check for None, empty string, or empty list
            if not value or (isinstance(value, list) and len(value) == 0):
                raise serializers.ValidationError({field: message})

        # Validate main category exists
        main_category_id = attrs.get('main_category_id')
        try:
            main_category = WorkCategory.objects.get(category_code=main_category_id, is_active=True)
            attrs['_main_category'] = main_category
        except WorkCategory.DoesNotExist:
            raise serializers.ValidationError({
                'main_category_id': f'Invalid main category: {main_category_id}'
            })

        # Validate subcategories
        sub_category_ids = attrs.get('sub_category_ids', [])
        if sub_category_ids:
            valid_subcategories = WorkSubCategory.objects.filter(
                category=main_category,
                subcategory_code__in=sub_category_ids,
                is_active=True
            )
            found_codes = [sub.subcategory_code for sub in valid_subcategories]
            invalid_codes = [code for code in sub_category_ids if code not in found_codes]

            if invalid_codes:
                raise serializers.ValidationError({
                    'sub_category_ids': f'Invalid subcategories: {", ".join(invalid_codes)}'
                })
            attrs['_subcategories'] = valid_subcategories

    def _validate_worker_fields(self, attrs):
        """Validate worker-specific required fields"""



















        required_fields = {
            'years_experience': 'Years of experience is required for workers',
            'skills': 'Skills description is required for workers'
        }

        for field, message in required_fields.items():
            value = attrs.get(field)
            if not value:
                raise serializers.ValidationError({field: message})

    def _validate_driver_fields(self, attrs):
        """Validate driver-specific required fields"""
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

    def _validate_property_fields(self, attrs):
        """Validate property-specific required fields"""
        required_fields = {
            'property_types': 'Property types are required for property services',
            'property_title': 'Property title is required for property services',
            'property_description': 'Property description is required for property services'
        }

        for field, message in required_fields.items():
            if not attrs.get(field):
                raise serializers.ValidationError({field: message})

    def _validate_sos_fields(self, attrs):
        """Validate SOS/Emergency-specific required fields"""
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
        """Create complete profile with all related data"""
        user = self.context['request'].user
        user_type = validated_data['user_type']
        service_type = validated_data.get('service_type')

        # Extract data that needs special handling
        main_category = validated_data.pop('_main_category', None)
        subcategories = validated_data.pop('_subcategories', [])
        portfolio_images = validated_data.pop('portfolio_images', [])
        keep_profile_photo = validated_data.pop('_keep_profile_photo', False)
        keep_portfolio_indices = validated_data.pop('_keep_portfolio_indices', [])
        existing_portfolio_urls = validated_data.pop('_existing_portfolio_urls', [])

        # Get existing profile to preserve photo if needed
        try:
            existing_profile = UserProfile.objects.get(user=user)
            existing_profile_photo = existing_profile.profile_photo if keep_profile_photo else None
        except UserProfile.DoesNotExist:
            existing_profile = None
            existing_profile_photo = None

        # Prepare profile_photo value
        profile_photo_value = validated_data.get('profile_photo')
        if keep_profile_photo and existing_profile_photo:
            profile_photo_value = existing_profile_photo

        # Create or update UserProfile
        profile, created = UserProfile.objects.update_or_create(
            user=user,
            defaults={
                'full_name': validated_data['full_name'],
                'date_of_birth': validated_data['date_of_birth'],
                'gender': validated_data['gender'],
                'profile_photo': profile_photo_value,
                'user_type': user_type,
                'service_type': service_type,
                'languages': ','.join(validated_data.get('languages', [])),
                'profile_complete': False,  # Will be updated after service data creation
                'can_access_app': False
            }
        )

        # Handle service-specific data for providers
        if user_type == 'provider':
            # All providers need work selection data
            self._create_worker_data(profile, validated_data, main_category, subcategories)

            # Create service-specific data
            if service_type == 'driver':
                self._create_driver_data(profile, validated_data)
            elif service_type == 'properties':
                self._create_property_data(profile, validated_data)
            elif service_type == 'SOS':
                self._create_sos_data(profile, validated_data)

            # Handle portfolio images for all provider types
            # Get existing portfolio images if we need to keep any
            existing_portfolio_objs = {}
            if keep_portfolio_indices and existing_profile:
                existing_imgs = list(existing_profile.service_portfolio_images.all().order_by('image_order'))
                for idx in keep_portfolio_indices:
                    if idx < len(existing_imgs):
                        existing_portfolio_objs[idx] = existing_imgs[idx]

            # Delete all existing portfolio images
            ServicePortfolioImage.objects.filter(user_profile=profile).delete()

            # Recreate portfolio images (mix of kept and new)
            for index, image in enumerate(portfolio_images, 1):
                if image is None and (index - 1) in existing_portfolio_objs:
                    # This is a kept image, recreate it with existing file
                    kept_img = existing_portfolio_objs[index - 1]
                    ServicePortfolioImage.objects.create(
                        user_profile=profile,
                        image=kept_img.image,
                        image_order=index
                    )
                elif image is not None:
                    # This is a new image
                    ServicePortfolioImage.objects.create(
                        user_profile=profile,
                        image=image,
                        image_order=index
                    )

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

        # Clear existing subcategories and add new ones
        UserWorkSubCategory.objects.filter(user_work_selection=work_selection).delete()
        for subcategory in subcategories:
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