# apps/profiles/serializers.py
from rest_framework import serializers
from django.db import transaction
from django.core.exceptions import ValidationError

from apps.profiles.models import UserProfile
from apps.work_categories.models import (
    WorkCategory, WorkSubCategory, UserWorkSelection, 
    UserWorkSubCategory, WorkPortfolioImage
)
from apps.verification.models import AadhaarVerification, LicenseVerification


class ProfileSetupSerializer(serializers.Serializer):
    """
    Single comprehensive serializer for complete profile setup
    Handles both provider and seeker profiles with all related data
    """
    
    # Basic Profile Fields (Required for all)
    user_type = serializers.ChoiceField(choices=['provider', 'seeker'])
    full_name = serializers.CharField(max_length=100)
    date_of_birth = serializers.DateField()
    gender = serializers.ChoiceField(choices=['male', 'female'])
    profile_photo = serializers.ImageField(required=False, allow_null=True)
    languages = serializers.CharField(required=False, allow_blank=True, help_text="Languages spoken, comma-separated")
    
    # Provider-specific Fields (Optional)
    main_category_id = serializers.CharField(
        required=False,
        allow_null=True,
        help_text="Main category code. Example: 'MS0001'"
    )
    sub_category_ids = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="List of subcategory codes. Example: ['SS0001', 'SS0002']"
    )
    years_experience = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    skills_description = serializers.CharField(required=False, allow_blank=True, max_length=500)
    
    # Portfolio Images (Provider only, max 3)
    portfolio_images = serializers.ListField(
        child=serializers.ImageField(),
        required=False,
        allow_empty=True,
        max_length=3
    )
    
    # Verification Fields (Optional)
    aadhaar_number = serializers.CharField(required=False, allow_blank=True, max_length=12)
    license_number = serializers.CharField(required=False, allow_blank=True, max_length=50)
    license_type = serializers.ChoiceField(
        choices=['driving', 'commercial', 'other'],
        required=False,
        allow_blank=True
    )
    
    def validate(self, attrs):
        """Custom validation for business rules"""
        user_type = attrs.get('user_type')
        
        # Provider validation
        if user_type == 'provider':
            # Work category is required for providers
            if not attrs.get('main_category_id'):
                raise serializers.ValidationError({
                    'main_category_id': 'Main work category is required for providers'
                })
            
            # At least one portfolio image required for providers
            portfolio_images = attrs.get('portfolio_images', [])
            if not portfolio_images:
                raise serializers.ValidationError({
                    'portfolio_images': 'At least one portfolio image is required for providers'
                })
            
            # Validate main category exists
            main_category_id = attrs.get('main_category_id')
            try:
                main_category = WorkCategory.objects.get(category_code=main_category_id, is_active=True)
                attrs['_main_category'] = main_category
            except WorkCategory.DoesNotExist:
                raise serializers.ValidationError({
                    'main_category_id': f'Invalid main category: {main_category_id}'
                })

            # Validate subcategories belong to main category
            sub_category_ids = attrs.get('sub_category_ids', [])
            if sub_category_ids:
                # Find subcategories by subcategory_code
                valid_subcategories = WorkSubCategory.objects.filter(
                    category=main_category,
                    subcategory_code__in=sub_category_ids,
                    is_active=True
                )

                found_codes = [sub.subcategory_code for sub in valid_subcategories]

                # Check if all requested subcategories were found
                invalid_codes = [code for code in sub_category_ids if code not in found_codes]
                if invalid_codes:
                    raise serializers.ValidationError({
                        'sub_category_ids': f'Invalid subcategories: {", ".join(invalid_codes)}'
                    })

                attrs['_subcategories'] = valid_subcategories
            
            # Driver-specific validation
            if main_category.name == 'driver':
                license_number = attrs.get('license_number')
                if not license_number:
                    raise serializers.ValidationError({
                        'license_number': 'License number is required for drivers'
                    })
        
        # Aadhaar validation
        aadhaar_number = attrs.get('aadhaar_number')
        if aadhaar_number:
            if len(aadhaar_number) != 12 or not aadhaar_number.isdigit():
                raise serializers.ValidationError({
                    'aadhaar_number': 'Aadhaar number must be exactly 12 digits'
                })
        
        return attrs
    
    @transaction.atomic
    def create(self, validated_data):
        """Create complete profile with all related data"""
        user = self.context['request'].user
        user_type = validated_data['user_type']
        
        # Extract nested data
        main_category = validated_data.pop('_main_category', None)
        subcategories = validated_data.pop('_subcategories', [])
        portfolio_images = validated_data.pop('portfolio_images', [])
        
        # Create or update UserProfile
        profile, created = UserProfile.objects.update_or_create(
            user=user,
            defaults={
                'full_name': validated_data['full_name'],
                'date_of_birth': validated_data['date_of_birth'],
                'gender': validated_data['gender'],
                'profile_photo': validated_data.get('profile_photo'),
                'user_type': user_type,
                'languages': validated_data.get('languages', ''),
                'profile_complete': True,
                'can_access_app': True
            }
        )
        
        # Handle provider-specific data
        if user_type == 'provider' and main_category:
            # Create UserWorkSelection
            work_selection, _ = UserWorkSelection.objects.update_or_create(
                user=profile,
                defaults={
                    'main_category': main_category,
                    'years_experience': validated_data.get('years_experience', 0),
                    'skills_description': validated_data.get('skills_description', '')
                }
            )
            
            # Clear existing subcategories and add new ones
            UserWorkSubCategory.objects.filter(user_work_selection=work_selection).delete()
            for subcategory in subcategories:
                UserWorkSubCategory.objects.create(
                    user_work_selection=work_selection,
                    sub_category=subcategory
                )
            
            # Handle portfolio images
            WorkPortfolioImage.objects.filter(user_work_selection=work_selection).delete()
            for index, image in enumerate(portfolio_images, 1):
                WorkPortfolioImage.objects.create(
                    user_work_selection=work_selection,
                    image=image,
                    image_order=index
                )
        
        # Handle verification data
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
            is_driver = main_category and main_category.name == 'driver'
            LicenseVerification.objects.update_or_create(
                user=profile,
                defaults={
                    'license_number': license_number,
                    'license_type': validated_data.get('license_type', 'driving'),
                    'status': 'pending',
                    'is_required': is_driver
                }
            )
        
        return profile


class ProfileResponseSerializer(serializers.ModelSerializer):
    """Serializer for profile response data"""
    main_category_id = serializers.SerializerMethodField()
    sub_category_ids = serializers.SerializerMethodField()
    age = serializers.ReadOnlyField()
    mobile_number = serializers.ReadOnlyField()
    skills = serializers.SerializerMethodField()
    years_experience = serializers.SerializerMethodField()
    profile_photo = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = [
            'id', 'full_name', 'user_type', 'gender', 'date_of_birth', 'age',
            'profile_photo', 'profile_complete', 'can_access_app',
            'mobile_number', 'languages', 'provider_id',
            'main_category_id', 'sub_category_ids', 'skills', 'years_experience',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'age', 'mobile_number', 'provider_id', 'created_at', 'updated_at']

    def get_main_category_id(self, obj):
        """Get main category code for providers"""
        if obj.user_type == 'provider' and hasattr(obj, 'work_selection') and obj.work_selection:
            return obj.work_selection.main_category.category_code
        return None

    def get_sub_category_ids(self, obj):
        """Get list of subcategory codes for providers"""
        if obj.user_type == 'provider' and hasattr(obj, 'work_selection') and obj.work_selection:
            subcategories = obj.work_selection.selected_subcategories.all()
            return [sub.sub_category.subcategory_code for sub in subcategories]
        return []

    def get_skills(self, obj):
        """Get subcategory names as skills for providers"""
        if obj.user_type == 'provider' and hasattr(obj, 'work_selection') and obj.work_selection:
            subcategories = obj.work_selection.selected_subcategories.all()
            return [sub.sub_category.name for sub in subcategories]
        return []

    def get_years_experience(self, obj):
        """Get years of experience for providers"""
        if obj.user_type == 'provider' and hasattr(obj, 'work_selection') and obj.work_selection:
            return obj.work_selection.years_experience
        return None

    def get_profile_photo(self, obj):
        """Get full URL for profile photo"""
        if obj.profile_photo:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.profile_photo.url)
            return obj.profile_photo.url
        return None