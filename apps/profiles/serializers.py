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
    Handles both worker and seeker profiles with all related data
    """
    
    # Basic Profile Fields (Required for all)
    user_type = serializers.ChoiceField(choices=['worker', 'seeker'])
    full_name = serializers.CharField(max_length=100)
    date_of_birth = serializers.DateField()
    gender = serializers.ChoiceField(choices=['male', 'female'])
    profile_photo = serializers.ImageField(required=False, allow_null=True)
    
    # Worker-specific Fields (Optional)
    main_category_id = serializers.IntegerField(required=False, allow_null=True)
    sub_category_names = serializers.CharField(
        required=False, 
        allow_blank=True,
        help_text="Space-separated subcategory names (case-insensitive). Example: 'Plumber Electrician'"
    )
    years_experience = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    skills_description = serializers.CharField(required=False, allow_blank=True, max_length=500)
    
    # Portfolio Images (Worker only, max 3)
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
        
        # Worker validation
        if user_type == 'worker':
            # Work category is required for workers
            if not attrs.get('main_category_id'):
                raise serializers.ValidationError({
                    'main_category_id': 'Main work category is required for workers'
                })
            
            # At least one portfolio image required for workers
            portfolio_images = attrs.get('portfolio_images', [])
            if not portfolio_images:
                raise serializers.ValidationError({
                    'portfolio_images': 'At least one portfolio image is required for workers'
                })
            
            # Validate main category exists
            main_category_id = attrs.get('main_category_id')
            try:
                main_category = WorkCategory.objects.get(id=main_category_id, is_active=True)
                attrs['_main_category'] = main_category
            except WorkCategory.DoesNotExist:
                raise serializers.ValidationError({
                    'main_category_id': 'Invalid work category selected'
                })
            
            # Validate subcategories belong to main category
            sub_category_names = attrs.get('sub_category_names', '').strip()
            if sub_category_names:
                # Split space-separated names and clean them
                subcategory_names_list = [name.strip() for name in sub_category_names.split() if name.strip()]
                
                if subcategory_names_list:
                    # Find subcategories by display_name (case-insensitive)
                    valid_subcategories = WorkSubCategory.objects.filter(
                        category_id=main_category_id,
                        display_name__iregex=r'^(' + '|'.join(subcategory_names_list) + ')$',
                        is_active=True
                    )
                    
                    found_names = [sub.display_name.lower() for sub in valid_subcategories]
                    requested_names = [name.lower() for name in subcategory_names_list]
                    
                    # Check if all requested subcategories were found
                    invalid_names = [name for name in requested_names if name not in found_names]
                    if invalid_names:
                        raise serializers.ValidationError({
                            'sub_category_names': f'Invalid subcategories: {", ".join(invalid_names)}'
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
                'profile_complete': True,
                'can_access_app': True
            }
        )
        
        # Handle worker-specific data
        if user_type == 'worker' and main_category:
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
    
    class Meta:
        model = UserProfile
        fields = [
            'id', 'full_name', 'user_type', 'gender', 'date_of_birth',
            'profile_photo', 'profile_complete', 'can_access_app',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']