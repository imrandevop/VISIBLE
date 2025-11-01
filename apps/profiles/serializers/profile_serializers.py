# apps/profiles/serializers/profile_serializers.py
"""
Profile setup and response serializers.
"""
from rest_framework import serializers
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from .serializer_utils import (
    FlexibleImageField, FlexibleStringField,
    download_image_from_url, is_url_string, get_existing_image_url,
    get_existing_portfolio_urls, files_are_same, parse_multipart_array_fields
)
from apps.profiles.models import (
    UserProfile, VehicleServiceData, PropertyServiceData,
    SOSServiceData, ServicePortfolioImage
)
from apps.work_categories.models import (
    WorkCategory, WorkSubCategory, UserWorkSelection,
    UserWorkSubCategory, WorkPortfolioImage
)
from apps.verification.models import AadhaarVerification, LicenseVerification


# ========================================================================================
# BASE SERIALIZER WITH SHARED LOGIC
# ========================================================================================

class BaseProfileSerializer(serializers.Serializer):
    """
    Base serializer with shared logic for common profile fields.
    Used by both SeekerProfileSetupSerializer and ProviderProfileSetupSerializer.
    """

    # Common Profile Fields
    full_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    gender = serializers.ChoiceField(choices=['male', 'female'], required=False, allow_null=True)
    profile_photo = serializers.ImageField(required=False, allow_null=True)
    languages = serializers.ListField(
        child=FlexibleStringField(),
        required=False,
        allow_empty=True,
        help_text="Array of languages spoken, supports indexed operations"
    )

    def _handle_profile_photo(self, data, existing_profile):
        """
        Shared logic to handle profile photo (file or URL).
        Returns True if photo should be kept, False if new photo should be uploaded.
        """
        if 'profile_photo' in data and data['profile_photo']:
            profile_photo_value = data['profile_photo']

            # Check if it's a file object
            if hasattr(profile_photo_value, 'read'):
                if existing_profile and existing_profile.profile_photo:
                    try:
                        if files_are_same(profile_photo_value, existing_profile.profile_photo):
                            data['_keep_profile_photo'] = True
                            data['profile_photo'] = None
                            return
                    except Exception as e:
                        print(f"Error comparing profile photos: {str(e)}")
                data['_keep_profile_photo'] = False

            elif is_url_string(profile_photo_value):
                existing_url = get_existing_image_url(existing_profile, 'profile_photo')
                if existing_url and profile_photo_value.endswith(existing_url):
                    data['_keep_profile_photo'] = True
                    data['profile_photo'] = None
                else:
                    downloaded_file = download_image_from_url(profile_photo_value)
                    if downloaded_file:
                        data['profile_photo'] = downloaded_file
                        data['_keep_profile_photo'] = False
                    else:
                        raise serializers.ValidationError({
                            'profile_photo': 'Failed to download image from provided URL'
                        })

    def _validate_common_fields(self, attrs, is_update):
        """
        Validate common fields required for profile setup.
        In create mode, all basic fields are required.
        In update mode, only validate provided fields.
        """
        if not is_update:
            required_basic_fields = {
                'full_name': 'Full name is required for profile setup',
                'date_of_birth': 'Date of birth is required for profile setup',
                'gender': 'Gender is required for profile setup'
            }

            for field, message in required_basic_fields.items():
                if not attrs.get(field):
                    raise serializers.ValidationError({field: message})

    def _handle_languages(self, validated_data, existing_profile):
        """
        Handle languages with indexed operations (add/replace/delete).
        Returns the updated languages string.
        """
        if 'languages' not in validated_data:
            if existing_profile:
                return existing_profile.languages
            return ''

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
                replace_delete_operations.append(lang_data)
            elif lang_data and not isinstance(lang_data, dict):
                add_languages.append(lang_data)

        # Process replace/delete operations
        for operation in replace_delete_operations:
            index = operation.get('index')
            new_language = operation.get('language')

            if 0 <= index < len(existing_languages):
                if new_language is None or new_language == '':
                    existing_languages.pop(index)
                else:
                    existing_languages[index] = new_language
            elif new_language and new_language != '':
                existing_languages.append(new_language)

        # Add new languages (avoiding duplicates)
        for new_language in add_languages:
            if new_language not in existing_languages:
                existing_languages.append(new_language)

        return ','.join(existing_languages) if existing_languages else ''

    def _build_profile_defaults(self, validated_data, existing_profile, keep_profile_photo):
        """
        Build the defaults dict for UserProfile.objects.update_or_create().
        """
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

        # Handle languages
        defaults['languages'] = self._handle_languages(validated_data, existing_profile)

        return defaults


# ========================================================================================
# SEEKER PROFILE SERIALIZER
# ========================================================================================

class SeekerProfileSetupSerializer(BaseProfileSerializer):
    """
    Serializer for seeker profile setup and updates.
    Handles both individual and business seeker types.

    Individual seekers: require full_name, date_of_birth, gender, seeker_type
    Business seekers: require seeker_type, business_name, business_location, established_date
    """

    user_type = serializers.HiddenField(default='seeker')

    # Seeker Type (required)
    seeker_type = serializers.ChoiceField(
        choices=['individual', 'business'],
        required=False,
        allow_null=True,
        help_text="Type of seeker (individual or business)"
    )

    # Remove languages field for seekers (override parent field)
    languages = None

    # Seeker Business Profile Fields
    business_name = serializers.CharField(
        max_length=200,
        required=False,
        allow_blank=True,
        help_text="Business name for business-type seekers"
    )
    business_location = serializers.CharField(
        max_length=300,
        required=False,
        allow_blank=True,
        help_text="Business location/address"
    )
    established_date = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Date when business was established"
    )
    website = serializers.CharField(
        max_length=300,
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Business website (optional, no validation)"
    )

    def to_internal_value(self, data):
        """Override to handle file and URL for images"""
        try:
            # Make a mutable copy
            if hasattr(data, '_mutable'):
                data._mutable = True

            # Parse multipart array fields
            parsed_arrays = parse_multipart_array_fields(data)
            data._parsed_arrays = parsed_arrays

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

        # Handle profile photo
        self._handle_profile_photo(data, existing_profile)

        # Call parent to_internal_value
        result = super().to_internal_value(data)

        # Preserve custom flags
        if '_keep_profile_photo' in data:
            result['_keep_profile_photo'] = data['_keep_profile_photo']

        return result

    def validate(self, attrs):
        """Custom validation for seeker profiles"""
        user = self.context['request'].user

        # Check if profile already exists
        try:
            existing_profile = UserProfile.objects.get(user=user)
            is_update = True
        except UserProfile.DoesNotExist:
            existing_profile = None
            is_update = False

        attrs['_is_update'] = is_update
        attrs['_existing_profile'] = existing_profile

        # Get seeker_type
        seeker_type = attrs.get('seeker_type')
        if not seeker_type and existing_profile:
            seeker_type = existing_profile.seeker_type

        # CREATE MODE: Validate based on seeker_type
        if not is_update:
            # seeker_type is required on create
            if not seeker_type:
                raise serializers.ValidationError({
                    'seeker_type': 'Seeker type is required (individual or business)'
                })

            if seeker_type == 'individual':
                # Individual seekers require: full_name, date_of_birth, gender
                required_individual_fields = {
                    'full_name': 'Full name is required for individual seekers',
                    'date_of_birth': 'Date of birth is required for individual seekers',
                    'gender': 'Gender is required for individual seekers'
                }
                for field, message in required_individual_fields.items():
                    if not attrs.get(field):
                        raise serializers.ValidationError({field: message})

            elif seeker_type == 'business':
                # Business seekers require: business_name, business_location, established_date, profile_photo
                required_business_fields = {
                    'business_name': 'Business name is required for business-type seekers',
                    'business_location': 'Business location is required for business-type seekers',
                    'established_date': 'Established date is required for business-type seekers',
                    'profile_photo': 'Profile photo is required for business-type seekers'
                }
                for field, message in required_business_fields.items():
                    if not attrs.get(field):
                        raise serializers.ValidationError({field: message})

        # UPDATE MODE: Validate based on seeker_type
        else:
            if seeker_type == 'individual':
                # If updating individual fields, validate they're complete
                if any(k in attrs for k in ['full_name', 'date_of_birth', 'gender']):
                    for field in ['full_name', 'date_of_birth', 'gender']:
                        value = attrs.get(field) or (getattr(existing_profile, field, None) if existing_profile else None)
                        if not value:
                            raise serializers.ValidationError({
                                field: f'{field.replace("_", " ").title()} is required for individual seekers'
                            })

            elif seeker_type == 'business':
                # If updating business fields, validate they're complete
                if any(k in attrs for k in ['business_name', 'business_location', 'established_date', 'website', 'profile_photo']):
                    for field in ['business_name', 'business_location', 'established_date', 'profile_photo']:
                        value = attrs.get(field) or (getattr(existing_profile, field, None) if existing_profile else None)
                        if not value:
                            raise serializers.ValidationError({
                                field: f'{field.replace("_", " ").title()} is required for business-type seekers'
                            })

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """Create or update seeker profile"""
        user = self.context['request'].user

        is_update = validated_data.pop('_is_update', False)
        existing_profile = validated_data.pop('_existing_profile', None)
        keep_profile_photo = validated_data.pop('_keep_profile_photo', False)

        # Get seeker_type
        seeker_type = validated_data.get('seeker_type')
        if not seeker_type and existing_profile:
            seeker_type = existing_profile.seeker_type

        # Build defaults dict differently based on seeker_type
        defaults = {}
        defaults['user_type'] = 'seeker'
        defaults['service_type'] = None
        defaults['languages'] = ''  # Seekers don't have languages

        # Set seeker_type
        if 'seeker_type' in validated_data:
            defaults['seeker_type'] = validated_data['seeker_type']
        elif existing_profile:
            defaults['seeker_type'] = existing_profile.seeker_type

        # Handle fields based on seeker_type
        if seeker_type == 'individual':
            # Individual seekers: set personal fields
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

            # Handle profile photo for individual
            if keep_profile_photo and existing_profile and existing_profile.profile_photo:
                defaults['profile_photo'] = existing_profile.profile_photo
            elif 'profile_photo' in validated_data and validated_data['profile_photo']:
                defaults['profile_photo'] = validated_data['profile_photo']
            elif existing_profile and existing_profile.profile_photo:
                defaults['profile_photo'] = existing_profile.profile_photo

            # Clear business fields for individual seekers
            defaults['business_name'] = None
            defaults['business_location'] = None
            defaults['established_date'] = None
            defaults['website'] = None

        elif seeker_type == 'business':
            # Business seekers: set business fields
            if 'business_name' in validated_data:
                defaults['business_name'] = validated_data['business_name']
            elif existing_profile:
                defaults['business_name'] = existing_profile.business_name

            if 'business_location' in validated_data:
                defaults['business_location'] = validated_data['business_location']
            elif existing_profile:
                defaults['business_location'] = existing_profile.business_location

            if 'established_date' in validated_data:
                defaults['established_date'] = validated_data['established_date']
            elif existing_profile:
                defaults['established_date'] = existing_profile.established_date

            if 'website' in validated_data:
                defaults['website'] = validated_data['website']
            elif existing_profile:
                defaults['website'] = existing_profile.website

            # Handle profile photo for business
            if keep_profile_photo and existing_profile and existing_profile.profile_photo:
                defaults['profile_photo'] = existing_profile.profile_photo
            elif 'profile_photo' in validated_data and validated_data['profile_photo']:
                defaults['profile_photo'] = validated_data['profile_photo']
            elif existing_profile and existing_profile.profile_photo:
                defaults['profile_photo'] = existing_profile.profile_photo

            # Map business fields to personal fields (required for DB constraints)
            # Use business_name as full_name
            defaults['full_name'] = defaults.get('business_name', existing_profile.business_name if existing_profile else 'Business User')
            # Use established_date as date_of_birth
            defaults['date_of_birth'] = defaults.get('established_date', existing_profile.established_date if existing_profile else None)
            # Set gender to 'male' as placeholder (not applicable for business)
            defaults['gender'] = 'male'

        defaults['profile_complete'] = False
        defaults['can_access_app'] = False

        # Create or update UserProfile
        profile, created = UserProfile.objects.update_or_create(
            user=user,
            defaults=defaults
        )

        # Update profile completion status
        profile.check_profile_completion()

        return profile


# ========================================================================================
# PROVIDER PROFILE SERIALIZER
# ========================================================================================

class ProviderProfileSetupSerializer(BaseProfileSerializer):
    """
    Serializer for provider profile setup and updates.
    Handles skill, vehicle, properties, and SOS service types.

    Individual providers: require full_name, date_of_birth, gender, provider_type
    Business providers: require provider_type, business_name, business_location, established_date
    """

    user_type = serializers.HiddenField(default='provider')

    # Provider Type (required)
    provider_type = serializers.ChoiceField(
        choices=['individual', 'business'],
        required=False,
        allow_null=True,
        help_text="Type of provider (individual or business)"
    )

    service_type = serializers.ChoiceField(
        choices=['skill', 'vehicle', 'properties', 'SOS'],
        required=False,
        allow_null=True,
        help_text="Required for providers on first create"
    )

    # Provider Business Profile Fields
    business_name = serializers.CharField(
        max_length=200,
        required=False,
        allow_blank=True,
        help_text="Business name for business-type providers"
    )
    business_location = serializers.CharField(
        max_length=300,
        required=False,
        allow_blank=True,
        help_text="Business location/address"
    )
    established_date = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Date when business was established"
    )
    website = serializers.URLField(
        max_length=300,
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Business website (optional)"
    )

    # Provider Service Coverage Area
    service_coverage_area = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        help_text="Service coverage area in kilometers"
    )

    # Portfolio Images (max 3)
    portfolio_images = serializers.ListField(
        child=FlexibleImageField(),
        required=False,
        allow_empty=True,
        max_length=3
    )

    # Category Fields (required for all providers)
    main_category_id = serializers.CharField(required=False, allow_null=True)
    sub_category_ids = serializers.ListField(
        child=FlexibleStringField(),
        required=False,
        allow_empty=True
    )
    years_experience = serializers.IntegerField(required=False, allow_null=True, min_value=0)

    # Common Service Fields
    description = serializers.CharField(required=False, allow_blank=True, help_text="Description for skill, vehicle, or property provider")

    # Vehicle-specific Fields
    license_number = serializers.CharField(required=False, allow_blank=True, max_length=50)
    vehicle_registration_number = serializers.CharField(required=False, allow_blank=True, max_length=20)
    vehicle_service_offering_types = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Service offering types for vehicles (rent, sale, lease, all)"
    )

    # Property-specific Fields
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
    property_service_offering_types = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Service offering types for properties (rent, sale)"
    )

    # SOS/Emergency-specific Fields
    contact_number = serializers.CharField(required=False, allow_blank=True, max_length=15)
    location = serializers.CharField(required=False, allow_blank=True, help_text="Service location for SOS providers")

    # Verification Fields (Optional)
    aadhaar_number = serializers.CharField(required=False, allow_blank=True, max_length=12)
    license_type = serializers.ChoiceField(
        choices=['driving', 'commercial', 'other'],
        required=False,
        allow_blank=True
    )

    def to_internal_value(self, data):
        """Override to handle files and URLs for images"""
        try:
            # Make a mutable copy
            if hasattr(data, '_mutable'):
                data._mutable = True

            # Parse multipart array fields
            parsed_arrays = parse_multipart_array_fields(data)
            data._parsed_arrays = parsed_arrays

            # Debug logging
            for field_name, field_value in parsed_arrays.items():
                if field_name in ['portfolio_images', 'languages', 'sub_category_ids']:
                    print(f"DEBUG: Parsed {field_name} from multipart: {field_value}")

            user = self.context['request'].user

            # Get existing profile
            try:
                existing_profile = UserProfile.objects.get(user=user)
            except UserProfile.DoesNotExist:
                existing_profile = None
        except Exception as e:
            print(f"ERROR in to_internal_value initialization: {str(e)}")
            import traceback
            traceback.print_exc()
            raise

        # Handle profile photo
        self._handle_profile_photo(data, existing_profile)

        # Handle portfolio images (same logic as original ProfileSetupSerializer)
        if hasattr(data, '_parsed_arrays') and 'portfolio_images' in data._parsed_arrays:
            try:
                portfolio_images_data = data._parsed_arrays['portfolio_images']

                if portfolio_images_data:
                    existing_portfolio_urls = get_existing_portfolio_urls(existing_profile)
                    existing_portfolio_objs = []

                    if existing_profile:
                        existing_portfolio_objs = list(existing_profile.service_portfolio_images.all().order_by('image_order'))

                    processed_images = []

                    for img_value in portfolio_images_data:
                        # Dict with index (replace/delete)
                        if isinstance(img_value, dict) and 'index' in img_value:
                            index = img_value.get('index')
                            if isinstance(index, str):
                                index = int(index)
                            image_data = img_value.get('image')

                            if image_data is None or image_data == '':
                                processed_images.append({'index': index, 'image': None})
                            elif hasattr(image_data, 'read'):
                                processed_images.append({'index': index, 'image': image_data})
                            elif is_url_string(image_data):
                                downloaded_file = download_image_from_url(image_data)
                                if downloaded_file:
                                    processed_images.append({'index': index, 'image': downloaded_file})
                                else:
                                    raise serializers.ValidationError({
                                        'portfolio_images': f'Failed to download image from URL for index {index}'
                                    })
                            else:
                                processed_images.append({'index': index, 'image': None})

                        # None/null value
                        elif img_value is None or img_value == '':
                            continue

                        # File object (add)
                        elif hasattr(img_value, 'read'):
                            file_matches_existing = False
                            for existing_img_obj in existing_portfolio_objs:
                                try:
                                    if files_are_same(img_value, existing_img_obj.image):
                                        file_matches_existing = True
                                        break
                                except Exception as e:
                                    print(f"Error comparing portfolio image: {str(e)}")
                                    continue

                            if not file_matches_existing:
                                processed_images.append(img_value)

                        # URL string (add)
                        elif is_url_string(img_value):
                            url_matches_existing = any(img_value.endswith(existing_url) for existing_url in existing_portfolio_urls)

                            if not url_matches_existing:
                                downloaded_file = download_image_from_url(img_value)
                                if downloaded_file:
                                    processed_images.append(downloaded_file)
                                else:
                                    raise serializers.ValidationError({
                                        'portfolio_images': 'Failed to download image from provided URL'
                                    })

                    data['portfolio_images'] = processed_images
            except Exception as e:
                print(f"ERROR processing portfolio_images: {str(e)}")
                import traceback
                traceback.print_exc()
                raise
        elif 'portfolio_images' in data:
            pass

        # Call parent to_internal_value
        result = super().to_internal_value(data)

        # If we had parsed arrays, manually set them in result
        if hasattr(data, '_parsed_arrays'):
            if 'portfolio_images' in data._parsed_arrays:
                result['portfolio_images'] = data['portfolio_images']

        # Preserve custom flags
        if '_keep_profile_photo' in data:
            result['_keep_profile_photo'] = data['_keep_profile_photo']

        return result

    def validate(self, attrs):
        """Custom validation for provider profiles"""
        user = self.context['request'].user

        # Check if profile already exists
        try:
            existing_profile = UserProfile.objects.get(user=user)
            is_update = True
        except UserProfile.DoesNotExist:
            existing_profile = None
            is_update = False

        attrs['_is_update'] = is_update
        attrs['_existing_profile'] = existing_profile

        # Get provider_type and service_type
        provider_type = attrs.get('provider_type')
        if not provider_type and existing_profile:
            provider_type = existing_profile.provider_type

        service_type = attrs.get('service_type')
        if not service_type and existing_profile:
            service_type = existing_profile.service_type

        # CREATE MODE: Validate all provider fields
        if not is_update:
            # provider_type is required on create
            if not provider_type:
                raise serializers.ValidationError({
                    'provider_type': 'Provider type is required (individual or business)'
                })

            # Validate individual vs business fields
            if provider_type == 'individual':
                # Individual providers require: full_name, date_of_birth, gender
                required_individual_fields = {
                    'full_name': 'Full name is required for individual providers',
                    'date_of_birth': 'Date of birth is required for individual providers',
                    'gender': 'Gender is required for individual providers'
                }
                for field, message in required_individual_fields.items():
                    if not attrs.get(field):
                        raise serializers.ValidationError({field: message})

            elif provider_type == 'business':
                # Business providers require: business_name, business_location, established_date, profile_photo
                required_business_fields = {
                    'business_name': 'Business name is required for business-type providers',
                    'business_location': 'Business location is required for business-type providers',
                    'established_date': 'Established date is required for business-type providers',
                    'profile_photo': 'Profile photo is required for business-type providers'
                }
                for field, message in required_business_fields.items():
                    if not attrs.get(field):
                        raise serializers.ValidationError({field: message})

            # Service type is required
            if not service_type:
                raise serializers.ValidationError({
                    'service_type': 'Service type is required for providers'
                })

            if not attrs.get('service_coverage_area'):
                raise serializers.ValidationError({
                    'service_coverage_area': 'Service coverage area is required for all providers'
                })

            # Category fields required on create
            self._validate_category_fields(attrs, is_required=True)

            # Service-specific validation
            if service_type == 'skill':
                self._validate_skill_fields(attrs, is_required=True)
            elif service_type == 'vehicle':
                self._validate_vehicle_fields(attrs, is_required=True)
            elif service_type == 'properties':
                self._validate_property_fields(attrs, is_required=True)
            elif service_type == 'SOS':
                self._validate_sos_fields(attrs, is_required=True)

        # UPDATE MODE: Validate only provided fields
        else:
            # Validate individual/business fields if updating
            if provider_type == 'individual':
                if any(k in attrs for k in ['full_name', 'date_of_birth', 'gender']):
                    for field in ['full_name', 'date_of_birth', 'gender']:
                        value = attrs.get(field) or (getattr(existing_profile, field, None) if existing_profile else None)
                        if not value:
                            raise serializers.ValidationError({
                                field: f'{field.replace("_", " ").title()} is required for individual providers'
                            })

            elif provider_type == 'business':
                if any(k in attrs for k in ['business_name', 'business_location', 'established_date', 'website', 'profile_photo']):
                    for field in ['business_name', 'business_location', 'established_date', 'profile_photo']:
                        value = attrs.get(field) or (getattr(existing_profile, field, None) if existing_profile else None)
                        if not value:
                            raise serializers.ValidationError({
                                field: f'{field.replace("_", " ").title()} is required for business-type providers'
                            })

            if 'main_category_id' in attrs or 'sub_category_ids' in attrs:
                self._validate_category_fields(attrs, is_required=False)

            if service_type == 'skill' and any(k in attrs for k in ['years_experience', 'description']):
                self._validate_skill_fields(attrs, is_required=False)
            elif service_type == 'vehicle' and any(k in attrs for k in ['license_number', 'vehicle_registration_number', 'description', 'vehicle_service_offering_types']):
                self._validate_vehicle_fields(attrs, is_required=False)
            elif service_type == 'properties' and any(k in attrs for k in ['property_title', 'parking_availability', 'furnishing_type', 'description', 'property_service_offering_types']):
                self._validate_property_fields(attrs, is_required=False)
            elif service_type == 'SOS' and any(k in attrs for k in ['contact_number', 'location', 'description']):
                self._validate_sos_fields(attrs, is_required=False)

        # Aadhaar validation
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
                if not value or (isinstance(value, list) and len(value) == 0):
                    raise serializers.ValidationError({field: message})

        # Validate main category exists
        main_category_id = attrs.get('main_category_id')
        if main_category_id:
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
                codes_to_validate = []
                for item in sub_category_ids:
                    if isinstance(item, dict):
                        sub_id = item.get('sub_category_id')
                        if sub_id and sub_id != '':
                            codes_to_validate.append(sub_id)
                    elif isinstance(item, str):
                        codes_to_validate.append(item)

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

                    attrs['_subcategories'] = sub_category_ids
                    attrs['_validated_subcategory_objects'] = {sub.subcategory_code: sub for sub in valid_subcategories}

    def _validate_skill_fields(self, attrs, is_required=True):
        """Validate skill-specific required fields"""
        if is_required:
            required_fields = {
                'years_experience': 'Years of experience is required for skill providers',
                'description': 'Description is required for skill providers'
            }

            for field, message in required_fields.items():
                value = attrs.get(field)
                if not value and value != 0:
                    raise serializers.ValidationError({field: message})

    def _validate_vehicle_fields(self, attrs, is_required=True):
        """Validate vehicle-specific required fields"""
        if is_required:
            required_fields = {
                'license_number': 'License number is required for vehicle providers',
                'vehicle_registration_number': 'Vehicle registration number is required for vehicle providers',
                'years_experience': 'Years of experience is required for vehicle providers',
                'description': 'Description is required for vehicle providers',
                'vehicle_service_offering_types': 'Service offering types are required for vehicle providers (rent, sale, lease, or all)'
            }

            for field, message in required_fields.items():
                if not attrs.get(field) and attrs.get(field) != 0:
                    raise serializers.ValidationError({field: message})

        # Validate service_offering_types values
        vehicle_service_offering_types = attrs.get('vehicle_service_offering_types', [])
        if vehicle_service_offering_types:
            valid_types = ['rent', 'sale', 'lease', 'all']
            invalid_types = [t for t in vehicle_service_offering_types if t.lower() not in valid_types]
            if invalid_types:
                raise serializers.ValidationError({
                    'vehicle_service_offering_types': f'Invalid service offering types: {", ".join(invalid_types)}. Valid options are: rent, sale, lease, all'
                })

    def _validate_property_fields(self, attrs, is_required=True):
        """Validate property-specific required fields"""
        if is_required:
            required_fields = {
                'property_title': 'Property title is required for property services',
                'description': 'Description is required for property services',
                'property_service_offering_types': 'Service offering types are required for property providers (rent or sale)'
            }

            for field, message in required_fields.items():
                if not attrs.get(field):
                    raise serializers.ValidationError({field: message})

        # Validate service_offering_types values
        property_service_offering_types = attrs.get('property_service_offering_types', [])
        if property_service_offering_types:
            valid_types = ['rent', 'sale']
            invalid_types = [t for t in property_service_offering_types if t.lower() not in valid_types]
            if invalid_types:
                raise serializers.ValidationError({
                    'property_service_offering_types': f'Invalid service offering types: {", ".join(invalid_types)}. Valid options are: rent, sale'
                })

    def _validate_sos_fields(self, attrs, is_required=True):
        """Validate SOS/Emergency-specific required fields"""
        if is_required:
            required_fields = {
                'contact_number': 'Contact number is required for SOS services',
                'location': 'Location is required for SOS services',
                'description': 'Description is required for SOS services'
            }

            for field, message in required_fields.items():
                if not attrs.get(field):
                    raise serializers.ValidationError({field: message})

    @transaction.atomic
    def create(self, validated_data):
        """Create or update provider profile"""
        user = self.context['request'].user

        is_update = validated_data.pop('_is_update', False)
        existing_profile = validated_data.pop('_existing_profile', None)

        # Extract data that needs special handling
        main_category = validated_data.pop('_main_category', None)
        subcategories = validated_data.pop('_subcategories', [])
        portfolio_images = validated_data.pop('portfolio_images', [])
        keep_profile_photo = validated_data.pop('_keep_profile_photo', False)

        # Get provider_type and service_type
        provider_type = validated_data.get('provider_type')
        if not provider_type and existing_profile:
            provider_type = existing_profile.provider_type

        service_type = validated_data.get('service_type')
        if not service_type and existing_profile:
            service_type = existing_profile.service_type

        # Build defaults dict differently based on provider_type
        defaults = {}
        defaults['user_type'] = 'provider'
        defaults['service_type'] = service_type

        # Set provider_type
        if 'provider_type' in validated_data:
            defaults['provider_type'] = validated_data['provider_type']
        elif existing_profile:
            defaults['provider_type'] = existing_profile.provider_type

        # Handle fields based on provider_type
        if provider_type == 'individual':
            # Individual providers: set personal fields
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

            # Handle profile photo for individual
            if keep_profile_photo and existing_profile and existing_profile.profile_photo:
                defaults['profile_photo'] = existing_profile.profile_photo
            elif 'profile_photo' in validated_data and validated_data['profile_photo']:
                defaults['profile_photo'] = validated_data['profile_photo']
            elif existing_profile and existing_profile.profile_photo:
                defaults['profile_photo'] = existing_profile.profile_photo

            # Clear business fields for individual providers
            defaults['business_name'] = None
            defaults['business_location'] = None
            defaults['established_date'] = None
            defaults['website'] = None

        elif provider_type == 'business':
            # Business providers: set business fields
            if 'business_name' in validated_data:
                defaults['business_name'] = validated_data['business_name']
            elif existing_profile:
                defaults['business_name'] = existing_profile.business_name

            if 'business_location' in validated_data:
                defaults['business_location'] = validated_data['business_location']
            elif existing_profile:
                defaults['business_location'] = existing_profile.business_location

            if 'established_date' in validated_data:
                defaults['established_date'] = validated_data['established_date']
            elif existing_profile:
                defaults['established_date'] = existing_profile.established_date

            if 'website' in validated_data:
                defaults['website'] = validated_data['website']
            elif existing_profile:
                defaults['website'] = existing_profile.website

            # Handle profile photo for business
            if keep_profile_photo and existing_profile and existing_profile.profile_photo:
                defaults['profile_photo'] = existing_profile.profile_photo
            elif 'profile_photo' in validated_data and validated_data['profile_photo']:
                defaults['profile_photo'] = validated_data['profile_photo']
            elif existing_profile and existing_profile.profile_photo:
                defaults['profile_photo'] = existing_profile.profile_photo

            # Map business fields to personal fields (required for DB constraints)
            # Use business_name as full_name
            defaults['full_name'] = defaults.get('business_name', existing_profile.business_name if existing_profile else 'Business User')
            # Use established_date as date_of_birth
            defaults['date_of_birth'] = defaults.get('established_date', existing_profile.established_date if existing_profile else None)
            # Set gender to 'male' as placeholder (not applicable for business)
            defaults['gender'] = 'male'

        # Handle languages (providers have languages)
        defaults['languages'] = self._handle_languages(validated_data, existing_profile)

        # Handle service_coverage_area
        if 'service_coverage_area' in validated_data:
            defaults['service_coverage_area'] = validated_data['service_coverage_area']
        elif existing_profile:
            defaults['service_coverage_area'] = existing_profile.service_coverage_area

        defaults['profile_complete'] = False
        defaults['can_access_app'] = False

        # Create or update UserProfile
        profile, created = UserProfile.objects.update_or_create(
            user=user,
            defaults=defaults
        )

        # Handle provider-specific data
        if main_category is not None or subcategories:
            self._create_skill_data(profile, validated_data, main_category, subcategories)

        # Update service-specific data
        if service_type == 'vehicle':
            vehicle_fields = ['license_number', 'vehicle_registration_number', 'years_experience', 'description', 'vehicle_service_offering_types']
            if any(field in validated_data for field in vehicle_fields):
                self._create_vehicle_data(profile, validated_data)
        elif service_type == 'properties':
            property_fields = ['property_title', 'parking_availability', 'furnishing_type', 'description', 'property_service_offering_types']
            if any(field in validated_data for field in property_fields):
                self._create_property_data(profile, validated_data)
        elif service_type == 'SOS':
            sos_fields = ['contact_number', 'location', 'description']
            if any(field in validated_data for field in sos_fields):
                self._create_sos_data(profile, validated_data)

        # Handle portfolio images
        if portfolio_images:
            self._handle_portfolio_images(profile, portfolio_images, existing_profile)

        # Handle verification data
        self._handle_verification_data(profile, validated_data, service_type)

        # Update profile completion status
        profile.check_profile_completion()

        return profile

    def _handle_portfolio_images(self, profile, portfolio_images, existing_profile):
        """Handle portfolio image operations (add/replace/delete)"""
        existing_imgs = []
        if existing_profile:
            existing_imgs = list(existing_profile.service_portfolio_images.all().order_by('image_order'))

        # Separate operations
        replace_delete_operations = []
        add_images = []

        for img_data in portfolio_images:
            if isinstance(img_data, dict) and 'index' in img_data:
                replace_delete_operations.append(img_data)
            elif img_data is not None:
                add_images.append(img_data)

        # Process replace/delete operations
        for operation in replace_delete_operations:
            index = operation.get('index')
            new_image = operation.get('image')

            existing_at_index = next((img for img in existing_imgs if img.image_order == index), None)

            if new_image is None and existing_at_index:
                existing_at_index.delete()
                existing_imgs.remove(existing_at_index)
            elif new_image is not None and existing_at_index:
                if hasattr(new_image, 'read') or hasattr(new_image, 'file'):
                    existing_at_index.image = new_image
                    existing_at_index.save()
            elif new_image is not None and not existing_at_index:
                if hasattr(new_image, 'read') or hasattr(new_image, 'file'):
                    ServicePortfolioImage.objects.create(
                        user_profile=profile,
                        image=new_image,
                        image_order=index
                    )

        # Add new images
        if existing_imgs:
            next_order = max(img.image_order for img in existing_imgs) + 1
        else:
            next_order = 0

        for new_image in add_images:
            ServicePortfolioImage.objects.create(
                user_profile=profile,
                image=new_image,
                image_order=next_order
            )
            next_order += 1

    def _create_skill_data(self, profile, validated_data, main_category, subcategories):
        """Create skill-specific data and work selection"""
        work_selection, _ = UserWorkSelection.objects.update_or_create(
            user=profile,
            defaults={
                'main_category': main_category,
                'years_experience': validated_data.get('years_experience', 0),
                'skills': validated_data.get('description', '')  # Maps 'description' to DB 'skills' field
            }
        )

        validated_subcategory_objects = validated_data.get('_validated_subcategory_objects', {})

        # Check if we have indices for targeted updates
        has_indices = False
        subcategory_indices = {}

        for sub_data in subcategories:
            if isinstance(sub_data, dict) and 'index' in sub_data:
                has_indices = True
                index = sub_data.get('index')
                sub_category_id = sub_data.get('sub_category_id')

                if sub_category_id and sub_category_id in validated_subcategory_objects:
                    subcategory = validated_subcategory_objects[sub_category_id]
                elif sub_category_id is None or sub_category_id == '':
                    subcategory = None
                else:
                    continue

                subcategory_indices[index] = subcategory

        if has_indices:
            # Handle indexed subcategories
            existing_subs = list(UserWorkSubCategory.objects.filter(user_work_selection=work_selection).order_by('id'))

            for index, subcategory in subcategory_indices.items():
                if index < len(existing_subs):
                    if subcategory is None:
                        existing_subs[index].delete()
                    else:
                        existing_subs[index].sub_category = subcategory
                        existing_subs[index].save()
                elif subcategory is not None:
                    UserWorkSubCategory.objects.create(
                        user_work_selection=work_selection,
                        sub_category=subcategory
                    )
        else:
            # Add new subcategories without replacing
            existing_sub_ids = set(UserWorkSubCategory.objects.filter(
                user_work_selection=work_selection
            ).values_list('sub_category_id', flat=True))

            for sub_data in subcategories:
                if isinstance(sub_data, str):
                    if sub_data in validated_subcategory_objects:
                        subcategory = validated_subcategory_objects[sub_data]
                        if subcategory.id not in existing_sub_ids:
                            UserWorkSubCategory.objects.create(
                                user_work_selection=work_selection,
                                sub_category=subcategory
                            )

    def _create_vehicle_data(self, profile, validated_data):
        """Create vehicle-specific data"""
        VehicleServiceData.objects.update_or_create(
            user_profile=profile,
            defaults={
                'license_number': validated_data.get('license_number', ''),
                'vehicle_registration_number': validated_data.get('vehicle_registration_number', ''),
                'years_experience': validated_data.get('years_experience', 0),
                'driving_experience_description': validated_data.get('description', ''),  # Maps 'description' to DB field
                'service_offering_types': ','.join(validated_data.get('vehicle_service_offering_types', []))
            }
        )

    def _create_property_data(self, profile, validated_data):
        """Create property-specific data"""
        PropertyServiceData.objects.update_or_create(
            user_profile=profile,
            defaults={
                'property_types': '',  # Removed field, keep empty for DB compatibility
                'property_title': validated_data.get('property_title', ''),
                'parking_availability': validated_data.get('parking_availability'),
                'furnishing_type': validated_data.get('furnishing_type'),
                'property_description': validated_data.get('description', ''),  # Maps 'description' to DB field
                'service_offering_types': ','.join(validated_data.get('property_service_offering_types', []))
            }
        )

    def _create_sos_data(self, profile, validated_data):
        """Create SOS/Emergency-specific data"""
        SOSServiceData.objects.update_or_create(
            user_profile=profile,
            defaults={
                'emergency_service_types': '',  # Removed field, keep empty for DB compatibility
                'contact_number': validated_data.get('contact_number', ''),
                'current_location': validated_data.get('location', ''),  # Maps 'location' to DB 'current_location' field
                'emergency_description': validated_data.get('description', '')  # Maps 'description' to DB field
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
            is_vehicle = service_type == 'vehicle'
            LicenseVerification.objects.update_or_create(
                user=profile,
                defaults={
                    'license_number': license_number,
                    'license_type': validated_data.get('license_type', 'driving'),
                    'status': 'pending',
                    'is_required': is_vehicle
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
            'mobile_number', 'languages', 'provider_id', 'service_coverage_area',
            'seeker_type', 'business_name', 'business_location', 'established_date', 'website',
            'portfolio_images', 'service_data',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'age', 'mobile_number', 'provider_id', 'created_at', 'updated_at']

    def to_representation(self, instance):
        """
        Override to exclude irrelevant fields based on user_type and provider/seeker type.
        - For seekers: exclude provider-specific fields and languages
        - For providers: exclude seeker-specific fields
        - For individual types: exclude business fields
        - For business types: exclude personal fields
        """
        data = super().to_representation(instance)

        # Fields to exclude based on user type
        if instance.user_type == 'seeker':
            # Remove provider-specific fields and languages (seekers don't have languages)
            provider_fields = [
                'service_type', 'provider_id', 'service_coverage_area',
                'portfolio_images', 'service_data', 'languages'
            ]
            for field in provider_fields:
                data.pop(field, None)

            # Handle seeker type specific fields
            if instance.seeker_type == 'individual':
                # Remove business fields for individual seekers
                business_fields = ['business_name', 'business_location', 'established_date', 'website']
                for field in business_fields:
                    data.pop(field, None)
            elif instance.seeker_type == 'business':
                # Remove personal fields for business seekers (but keep profile_photo)
                personal_fields = ['full_name', 'date_of_birth', 'gender', 'age']
                for field in personal_fields:
                    data.pop(field, None)

        elif instance.user_type == 'provider':
            # Remove seeker-specific fields
            data.pop('seeker_type', None)

            # Determine provider type based on business_name (business if exists, individual if not)
            is_business_provider = bool(instance.business_name)

            # Handle provider type specific fields
            if not is_business_provider:
                # Remove business fields for individual providers
                business_fields = ['business_name', 'business_location', 'established_date', 'website']
                for field in business_fields:
                    data.pop(field, None)
            else:
                # Remove personal fields for business providers (but keep profile_photo)
                personal_fields = ['full_name', 'date_of_birth', 'gender', 'age']
                for field in personal_fields:
                    data.pop(field, None)

        return data

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

        if obj.service_type == 'skill':
            return self._get_skill_data(obj)
        elif obj.service_type == 'vehicle':
            return self._get_vehicle_data(obj)
        elif obj.service_type == 'properties':
            return self._get_property_data(obj)
        elif obj.service_type == 'SOS':
            return self._get_sos_data(obj)

        return None

    def _get_skill_data(self, obj):
        """Get skill-specific data"""
        if hasattr(obj, 'work_selection') and obj.work_selection:
            work_selection = obj.work_selection
            subcategories = work_selection.selected_subcategories.all()

            return {
                'main_category_id': work_selection.main_category.category_code,
                'main_category_name': work_selection.main_category.display_name,
                'sub_category_ids': [sub.sub_category.subcategory_code for sub in subcategories],
                'sub_category_names': [sub.sub_category.display_name for sub in subcategories],
                'years_experience': work_selection.years_experience,
                'description': work_selection.skills  # Return as 'description'
            }
        return None

    def _get_vehicle_data(self, obj):
        """Get vehicle-specific data including category data"""
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

        # Get vehicle-specific data
        if hasattr(obj, 'vehicle_service') and obj.vehicle_service:
            vehicle_data = obj.vehicle_service
            data.update({
                'license_number': vehicle_data.license_number,
                'vehicle_registration_number': vehicle_data.vehicle_registration_number,
                'description': vehicle_data.driving_experience_description,  # Return as 'description'
                'service_offering_types': vehicle_data.service_offering_types.split(',') if vehicle_data.service_offering_types else []
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
                'sub_category_ids': [sub.sub_category.subcategory_code for sub in subcategories]
            })

        # Get property-specific data
        if hasattr(obj, 'property_service') and obj.property_service:
            property_data = obj.property_service
            data.update({
                'property_title': property_data.property_title,
                'parking_availability': property_data.parking_availability,
                'furnishing_type': property_data.furnishing_type,
                'description': property_data.property_description,  # Return as 'description'
                'service_offering_types': property_data.service_offering_types.split(',') if property_data.service_offering_types else []
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
                'sub_category_ids': [sub.sub_category.subcategory_code for sub in subcategories]
            })

        # Get SOS-specific data
        if hasattr(obj, 'sos_service') and obj.sos_service:
            sos_data = obj.sos_service
            data.update({
                'contact_number': sos_data.contact_number,
                'location': sos_data.current_location,  # Return as 'location'
                'description': sos_data.emergency_description  # Return as 'description'
            })

        return data if data else None


