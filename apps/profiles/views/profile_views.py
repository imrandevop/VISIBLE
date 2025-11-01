# apps/profiles/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction

from apps.profiles.serializers import (
    ProfileResponseSerializer, WalletSerializer, RoleSwitchSerializer,
    SeekerProfileSetupSerializer, ProviderProfileSetupSerializer
)
from apps.profiles.models import UserProfile, Wallet
from apps.core.models import ProviderActiveStatus

# ========================================================================================
# PROFILE SETUP ENDPOINTS - SEPARATED BY USER TYPE
# ========================================================================================

@api_view(['POST', 'PATCH'])
@permission_classes([IsAuthenticated])
def seeker_profile_setup_api(request, version=None):
    """
    Seeker profile setup and update API

    POST /api/1/profiles/seeker/setup/ - Create new seeker profile
    PATCH /api/1/profiles/seeker/setup/ - Update existing seeker profile (partial updates supported)

    Headers:
        Authorization: Bearer <jwt_token>
        Content-Type: multipart/form-data

    Body (form-data) - POST (Create Profile):
        # Seeker type (required)
        seeker_type: "individual" or "business"

        # Individual seeker fields (required if seeker_type=individual)
        full_name: "John Doe"
        date_of_birth: "1990-01-15"
        gender: "male" or "female"
        profile_photo: <file> (optional)

        # Business seeker fields (required if seeker_type=business)
        business_name: "Smith Enterprises"
        business_location: "123 Business St, Delhi"
        established_date: "2015-06-01"
        website: "https://smithenterprises.com" (optional)
        profile_photo: <file> (required for business)

    Body (form-data) - PATCH (Update Profile - Partial Updates Supported):
        # Only send fields you want to update
        full_name: "John Smith"  (update name)
        profile_photo: <file>    (update photo)
        # All other fields remain unchanged

    Response:
        Success (200) - Individual Seeker (POST):
        {
            "status": "success",
            "message": "Seeker profile created successfully",
            "profile": {
                "id": 1,
                "full_name": "John Doe",
                "user_type": "seeker",
                "seeker_type": "individual",
                "gender": "male",
                "date_of_birth": "1990-01-15",
                "profile_photo": "/media/profiles/photo.jpg",
                "profile_complete": true,
                "can_access_app": true,
                "created_at": "2025-08-15T10:30:00Z",
                "updated_at": "2025-08-15T10:30:00Z"
            }
        }

        Success (200) - Business Seeker (POST):
        {
            "status": "success",
            "message": "Seeker profile created successfully",
            "profile": {
                "id": 2,
                "user_type": "seeker",
                "seeker_type": "business",
                "business_name": "Smith Enterprises",
                "business_location": "123 Business St, Delhi",
                "established_date": "2015-06-01",
                "website": "https://smithenterprises.com",
                "profile_photo": "/media/profiles/business_logo.jpg",
                "profile_complete": true,
                "can_access_app": true,
                "created_at": "2025-08-15T10:30:00Z",
                "updated_at": "2025-08-15T10:30:00Z"
            }
        }

        Error (400) - Validation Failed:
        {
            "status": "error",
            "message": "Validation failed",
            "errors": {
                "seeker_type": ["Seeker type is required (individual or business)"],
                "business_name": ["Business name is required for business-type seekers"],
                "established_date": ["Established date is required for business-type seekers"]
            }
        }

        Error (400) - Profile Already Exists (POST):
        {
            "status": "error",
            "message": "Profile already exists. Use PATCH method to update.",
            "hint": "Use PATCH /api/1/profiles/seeker/setup/ to update your profile"
        }

        Error (404) - Profile Not Found (PATCH):
        {
            "status": "error",
            "message": "Profile not found. Use POST method to create profile.",
            "hint": "Use POST /api/1/profiles/seeker/setup/ to create your profile"
        }
    """
    try:
        # Handle versioning if needed
        if hasattr(request, 'version'):
            api_version = request.version
            if api_version == 'v2':
                pass

        # Debug logging
        print(f"SEEKER PROFILE SETUP API CALLED - Method: {request.method}")
        print(f"Request data keys: {list(request.data.keys())}")
        print(f"User: {request.user.mobile_number}")

        # Method-based validation: POST = create only, PATCH = update only
        if request.method == 'POST':
            # POST should only create, error if profile exists
            try:
                existing_profile = UserProfile.objects.get(user=request.user)
                return Response({
                    "status": "error",
                    "message": "Profile already exists. Use PATCH method to update.",
                    "hint": "Use PATCH /api/1/profiles/seeker/setup/ to update your profile"
                }, status=status.HTTP_400_BAD_REQUEST)
            except UserProfile.DoesNotExist:
                pass  # Good, profile doesn't exist, continue with creation

        elif request.method == 'PATCH':
            # PATCH should only update, error if profile doesn't exist
            try:
                existing_profile = UserProfile.objects.get(user=request.user)
            except UserProfile.DoesNotExist:
                return Response({
                    "status": "error",
                    "message": "Profile not found. Use POST method to create profile.",
                    "hint": "Use POST /api/1/profiles/seeker/setup/ to create your profile"
                }, status=status.HTTP_404_NOT_FOUND)

        # Validate and process data using SeekerProfileSetupSerializer
        serializer = SeekerProfileSetupSerializer(data=request.data, context={'request': request})

        if serializer.is_valid():
            try:
                # Create profile with all related data
                with transaction.atomic():
                    profile = serializer.save()

                # Return success response
                response_data = ProfileResponseSerializer(profile, context={'request': request}).data

                # Dynamic message based on request method
                message = "Seeker profile created successfully" if request.method == 'POST' else "Seeker profile updated successfully"

                return Response({
                    "status": "success",
                    "message": message,
                    "profile": response_data
                }, status=status.HTTP_200_OK)

            except Exception as e:
                # Always log the error to console for debugging
                print(f"SEEKER PROFILE CREATION ERROR: {str(e)}")
                import traceback
                print(f"FULL TRACEBACK: {traceback.format_exc()}")

                return Response({
                    "status": "error",
                    "message": "Failed to create seeker profile. Please try again.",
                    "debug_error": str(e) if request.user.is_staff else None
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            # Validation errors
            return Response({
                "status": "error",
                "message": "Validation failed",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        # Always log the error to console for debugging
        print(f"OUTER EXCEPTION IN SEEKER PROFILE SETUP: {str(e)}")
        import traceback
        print(f"FULL TRACEBACK: {traceback.format_exc()}")

        return Response({
            "status": "error",
            "message": "An unexpected server error occurred. Please try again.",
            "debug_error": str(e) if request.user.is_staff else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST', 'PATCH'])
@permission_classes([IsAuthenticated])
def provider_profile_setup_api(request, version=None):
    """
    Provider profile setup and update API

    POST /api/1/profiles/provider/setup/ - Create new provider profile
    PATCH /api/1/profiles/provider/setup/ - Update existing provider profile (partial updates supported)

    Headers:
        Authorization: Bearer <jwt_token>
        Content-Type: multipart/form-data

    Body (form-data) - POST (Create Profile):

    INDIVIDUAL SKILL PROVIDER:
        # Provider type (required)
        provider_type: "individual"

        # Personal fields (required for individual)
        full_name: "Rajesh Kumar"
        date_of_birth: "1988-08-20"
        gender: "male"
        profile_photo: <file> (optional)

        # Service configuration
        service_type: "skill"
        main_category_id: "MS0001"
        sub_category_ids: ["SS0001", "SS0002", "SS0003"]
        service_coverage_area: 25 (in kilometers)
        languages: ["English", "Hindi", "Telugu"]

        # Skill-specific fields
        years_experience: 5
        description: "Expert plumber with 5 years of residential and commercial experience. Specialized in pipe fitting, leak repairs."

        # Portfolio
        portfolio_images: [<file1>, <file2>, <file3>] (1-3 images, optional)

    Body (form-data) - BUSINESS SKILL PROVIDER:
        # Provider type (required)
        provider_type: "business"

        # Business fields (required for business)
        business_name: "Acme Corporation"
        business_location: "New York, USA"
        established_date: "2010-03-20"
        website: "https://www.acme.com" (optional)
        profile_photo: <file> (required for business)

        # Service configuration
        service_type: "skill"
        main_category_id: "MS0001"
        sub_category_ids: ["SS0001", "SS0002", "SS0003"]
        service_coverage_area: 25 (in kilometers)
        languages: ["English", "Hindi", "Telugu"]

        # Skill-specific fields
        years_experience: 5
        description: "Expert plumber with 5 years of residential and commercial experience. Specialized in pipe fitting, leak repairs."

        # Portfolio
        portfolio_images: [<file1>, <file2>, <file3>] (1-3 images, optional)

    Body (form-data) - INDIVIDUAL VEHICLE PROVIDER:
        # Provider type (required)
        provider_type: "individual"

        # Personal fields (required for individual)
        full_name: "Amit Sharma"
        date_of_birth: "1985-03-10"
        gender: "male"
        profile_photo: <file> (optional)

        # Service configuration
        service_type: "vehicle"
        main_category_id: "MS0002"
        sub_category_ids: ["SS0010", "SS0011"]
        service_coverage_area: 30 (in kilometers)
        languages: ["English", "Hindi"]

        # Vehicle-specific fields
        license_number: "DL1420150012345" (optional)
        vehicle_registration_number: "DL01AB1234" (optional)
        years_experience: 8 (required)
        driving_experience_description: "8 years professional driving experience with corporate clients, airport transfers, and outstation trips. Clean driving record." (required)
        vehicle_service_offering_types: ["For Rent", "Lease"] (required - options: All, For Sale, For Rent, Driver Service, Exchange, Lease, Delivery Service)

        # Portfolio
        portfolio_images: [<vehicle_photo1>, <vehicle_photo2>] (1-3 images, optional)

    Body (form-data) - BUSINESS VEHICLE PROVIDER:
        # Provider type (required)
        provider_type: "business"

        # Business fields (required for business)
        business_name: "City Cabs & Rentals"
        business_location: "123 Transport Nagar, Delhi"
        established_date: "2010-05-15"
        website: "https://citycabs.com" (optional)
        profile_photo: <file> (required for business)

        # Service configuration
        service_type: "vehicle"
        main_category_id: "MS0002"
        sub_category_ids: ["SS0010", "SS0011", "SS0012"]
        service_coverage_area: 50 (in kilometers)
        languages: ["English", "Hindi", "Punjabi"]

        # Vehicle-specific fields
        license_number: "DL1420150012345" (optional)
        vehicle_registration_number: "DL01XY9999" (optional)
        years_experience: 12 (required)
        driving_experience_description: "12 years in vehicle rental business. Fleet of 20+ vehicles with professional drivers. Corporate tie-ups and airport services." (required)
        vehicle_service_offering_types: ["For Rent", "Lease", "For Sale"] (required - options: All, For Sale, For Rent, Driver Service, Exchange, Lease, Delivery Service)

        # Portfolio
        portfolio_images: [<fleet_photo1>, <fleet_photo2>, <office_photo>] (1-3 images, optional)

    Body (form-data) - INDIVIDUAL PROPERTY PROVIDER:
        # Provider type (required)
        provider_type: "individual"

        # Personal fields (required for individual)
        full_name: "John Doe"
        date_of_birth: "1990-01-15"
        gender: "male" or "female"
        profile_photo: <file> (optional)

        # Service configuration
        service_type: "properties"
        main_category_id: "MS0003"
        sub_category_ids: ["SS0020", "SS0021"]
        service_coverage_area: 15 (in kilometers)

        # Property-specific fields
        property_service_offering_types: ["For Rent", "For Sale"] (required - options: All, For Rent, For Sale, Lease, Accommodation, Hospitality, Lodge)
        property_title: "Luxury 3BHK Apartment in Prime Location"
        parking_availability: "Yes"
        furnishing_type: "Fully Furnished"
        description: "Spacious 3BHK apartment with modern amenities, 24/7 security, power backup, and excellent connectivity to metro and shopping centers."

        # Portfolio
        portfolio_images: [<property_photo1>, <property_photo2>, <property_photo3>] (1-3 images, optional)

    Body (form-data) - BUSINESS PROPERTY PROVIDER:
        # Provider type (required)
        provider_type: "business"

        # Business fields (required for business)
        business_name: "Smith Enterprises"
        business_location: "123 Business St, Delhi"
        established_date: "2015-06-01"
        website: "https://smithenterprises.com" (optional)
        profile_photo: <file> (required for business)

        # Service configuration
        service_type: "properties"
        main_category_id: "MS0003"
        sub_category_ids: ["SS0020", "SS0021"]
        service_coverage_area: 15 (in kilometers)

        # Property-specific fields
        property_service_offering_types: ["For Rent", "For Sale"] (required - options: All, For Rent, For Sale, Lease, Accommodation, Hospitality, Lodge)
        property_title: "Luxury 3BHK Apartment in Prime Location"
        parking_availability: "Yes"
        furnishing_type: "Fully Furnished"
        description: "Spacious 3BHK apartment with modern amenities, 24/7 security, power backup, and excellent connectivity to metro and shopping centers."

        # Portfolio
        portfolio_images: [<property_photo1>, <property_photo2>, <property_photo3>] (1-3 images, optional)

    Body (form-data) - INDIVIDUAL SOS PROVIDER:
        # Provider type (required)
        provider_type: "individual"

        # Personal fields (required for individual)
        full_name: "John Doe"
        date_of_birth: "1990-01-15"
        gender: "male"
        profile_photo: <file> (optional)

        # Service configuration
        service_type: "SOS"
        main_category_id: "MS0004"
        sub_category_ids: ["SS0030", "SS0031"]
        service_coverage_area: 50 (in kilometers)

        # SOS-specific fields
        contact_number: "9876543210"
        location: "Delhi NCR, India"
        description: "24/7 emergency medical services available with equipped ambulance and trained medical staff. Specializing in cardiac emergencies and trauma care."

        # Portfolio
        portfolio_images: [<ambulance_photo>, <facility_photo>] (1-3 images, optional)

    Body (form-data) - BUSINESS SOS PROVIDER:
        # Provider type (required)
        provider_type: "business"

        # Business fields (required for business)
        business_name: "Smith Enterprises"
        business_location: "123 Business St, Delhi"
        established_date: "2015-06-01"
        website: "https://smithenterprises.com" (optional)
        profile_photo: <file> (required for business)

        # Service configuration
        service_type: "SOS"
        main_category_id: "MS0004"
        sub_category_ids: ["SS0030", "SS0031"]
        service_coverage_area: 50 (in kilometers)

        # SOS-specific fields
        contact_number: "9876543210"
        location: "Delhi NCR, India"
        description: "24/7 emergency medical services available with equipped ambulance and trained medical staff. Specializing in cardiac emergencies and trauma care."

        # Portfolio
        portfolio_images: [<ambulance_photo>, <facility_photo>] (1-3 images, optional)

    Body (form-data) - PATCH (Update Profile - Partial Updates Supported):
        # Only send fields you want to update
        # Examples for different update scenarios:

        # Update personal info (individual provider):
        full_name: "Updated Name"
        profile_photo: <file>

        # Update business info (business provider):
        business_name: "Updated Business Name"
        website: "https://newwebsite.com"
        profile_photo: <file>

        # Update service details:
        description: "Updated service description"
        service_coverage_area: 30

        # Update portfolio:
        portfolio_images: [<new_photo1>, <new_photo2>]

        # Update skill provider specific:
        years_experience: 10

        # Update property provider specific:
        property_title: "Updated Property Title"
        parking_availability: "Yes"

        # Update SOS provider specific:
        contact_number: "9999999999"
        location: "New Location"

        # All other fields remain unchanged

    Response:
        Success (200) - Individual Skill Provider (POST):
        {
            "status": "success",
            "message": "Provider profile created successfully",
            "profile": {
                "id": 1,
                "full_name": "Rajesh Kumar",
                "user_type": "provider",
                "provider_type": "individual",
                "service_type": "skill",
                "gender": "male",
                "date_of_birth": "1988-08-20",
                "profile_photo": "/media/profiles/photo.jpg",
                "profile_complete": true,
                "can_access_app": true,
                "service_coverage_area": 25,
                "languages": ["English", "Hindi", "Telugu"],
                "provider_id": "PRV0001",
                "service_data": {
                    "main_category_id": "MS0001",
                    "main_category_name": "SKILL",
                    "sub_category_ids": ["SS0001", "SS0002", "SS0003"],
                    "sub_category_names": ["Plumber", "Electrician", "Carpenter"],
                    "years_experience": 5,
                    "description": "Expert plumber with 5 years of residential and commercial experience. Specialized in pipe fitting, leak repairs."
                },
                "portfolio_images": ["/media/portfolios/img1.jpg", "/media/portfolios/img2.jpg", "/media/portfolios/img3.jpg"],
                "created_at": "2025-08-15T10:30:00Z",
                "updated_at": "2025-08-15T10:30:00Z"
            }
        }

        Success (200) - Business Skill Provider (POST):
        {
            "status": "success",
            "message": "Provider profile created successfully",
            "profile": {
                "id": 2,
                "user_type": "provider",
                "provider_type": "business",
                "service_type": "skill",
                "business_name": "Acme Corporation",
                "business_location": "New York, USA",
                "established_date": "2010-03-20",
                "website": "https://www.acme.com",
                "profile_photo": "/media/profiles/business_logo.jpg",
                "profile_complete": true,
                "can_access_app": true,
                "service_coverage_area": 25,
                "languages": ["English", "Hindi", "Telugu"],
                "provider_id": "PRV0002",
                "service_data": {
                    "main_category_id": "MS0001",
                    "main_category_name": "SKILL",
                    "sub_category_ids": ["SS0001", "SS0002", "SS0003"],
                    "sub_category_names": ["Plumber", "Electrician", "Carpenter"],
                    "years_experience": 5,
                    "description": "Expert plumber with 5 years of residential and commercial experience. Specialized in pipe fitting, leak repairs."
                },
                "portfolio_images": ["/media/portfolios/img1.jpg", "/media/portfolios/img2.jpg", "/media/portfolios/img3.jpg"],
                "created_at": "2025-08-15T10:30:00Z",
                "updated_at": "2025-08-15T10:30:00Z"
            }
        }

        Success (200) - Individual Vehicle Provider (POST):
        {
            "status": "success",
            "message": "Provider profile created successfully",
            "profile": {
                "id": 3,
                "full_name": "Amit Sharma",
                "user_type": "provider",
                "provider_type": "individual",
                "service_type": "vehicle",
                "gender": "male",
                "date_of_birth": "1985-03-10",
                "profile_photo": "/media/profiles/photo.jpg",
                "profile_complete": true,
                "can_access_app": true,
                "service_coverage_area": 30,
                "languages": ["English", "Hindi"],
                "provider_id": "PRV0003",
                "service_data": {
                    "main_category_id": "MS0002",
                    "main_category_name": "VEHICLE",
                    "sub_category_ids": ["SS0010", "SS0011"],
                    "sub_category_names": ["Car Rental", "Driver Service"],
                    "license_number": "DL1420150012345",
                    "vehicle_registration_number": "DL01AB1234",
                    "years_experience": 8,
                    "driving_experience_description": "8 years professional driving experience with corporate clients, airport transfers, and outstation trips. Clean driving record.",
                    "service_offering_types": ["rent", "lease"]
                },
                "portfolio_images": ["/media/portfolios/vehicle1.jpg", "/media/portfolios/vehicle2.jpg"],
                "created_at": "2025-08-15T10:30:00Z",
                "updated_at": "2025-08-15T10:30:00Z"
            }
        }

        Success (200) - Business Vehicle Provider (POST):
        {
            "status": "success",
            "message": "Provider profile created successfully",
            "profile": {
                "id": 4,
                "user_type": "provider",
                "provider_type": "business",
                "service_type": "vehicle",
                "business_name": "City Cabs & Rentals",
                "business_location": "123 Transport Nagar, Delhi",
                "established_date": "2010-05-15",
                "website": "https://citycabs.com",
                "profile_photo": "/media/profiles/business_logo.jpg",
                "profile_complete": true,
                "can_access_app": true,
                "service_coverage_area": 50,
                "languages": ["English", "Hindi", "Punjabi"],
                "provider_id": "PRV0004",
                "service_data": {
                    "main_category_id": "MS0002",
                    "main_category_name": "VEHICLE",
                    "sub_category_ids": ["SS0010", "SS0011", "SS0012"],
                    "sub_category_names": ["Car Rental", "Driver Service", "Luxury Vehicles"],
                    "license_number": "DL1420150012345",
                    "vehicle_registration_number": "DL01XY9999",
                    "years_experience": 12,
                    "driving_experience_description": "12 years in vehicle rental business. Fleet of 20+ vehicles with professional drivers. Corporate tie-ups and airport services.",
                    "service_offering_types": ["rent", "lease", "sale"]
                },
                "portfolio_images": ["/media/portfolios/fleet1.jpg", "/media/portfolios/fleet2.jpg", "/media/portfolios/office.jpg"],
                "created_at": "2025-08-15T10:30:00Z",
                "updated_at": "2025-08-15T10:30:00Z"
            }
        }

        Success (200) - Individual Property Provider (POST):
        {
            "status": "success",
            "message": "Provider profile created successfully",
            "profile": {
                "id": 1,
                "full_name": "John Doe",
                "user_type": "provider",
                "provider_type": "individual",
                "service_type": "properties",
                "gender": "male",
                "date_of_birth": "1990-01-15",
                "profile_photo": "/media/profiles/photo.jpg",
                "profile_complete": true,
                "can_access_app": true,
                "service_coverage_area": 15,
                "provider_id": "PRV0001",
                "service_data": {
                    "main_category_id": "MS0003",
                    "sub_category_ids": ["SS0020", "SS0021"],
                    "property_title": "Luxury 3BHK Apartment in Prime Location",
                    "parking_availability": "Yes",
                    "furnishing_type": "Fully Furnished",
                    "description": "Spacious 3BHK apartment with modern amenities, 24/7 security, power backup, and excellent connectivity to metro and shopping centers.",
                    "service_offering_types": ["rent", "sale"]
                },
                "portfolio_images": ["/media/portfolios/img1.jpg", "/media/portfolios/img2.jpg", "/media/portfolios/img3.jpg"],
                "created_at": "2025-08-15T10:30:00Z",
                "updated_at": "2025-08-15T10:30:00Z"
            }
        }

        Success (200) - Business Property Provider (POST):
        {
            "status": "success",
            "message": "Provider profile created successfully",
            "profile": {
                "id": 2,
                "user_type": "provider",
                "provider_type": "business",
                "service_type": "properties",
                "business_name": "Smith Enterprises",
                "business_location": "123 Business St, Delhi",
                "established_date": "2015-06-01",
                "website": "https://smithenterprises.com",
                "profile_photo": "/media/profiles/business_logo.jpg",
                "profile_complete": true,
                "can_access_app": true,
                "service_coverage_area": 15,
                "provider_id": "PRV0002",
                "service_data": {
                    "main_category_id": "MS0003",
                    "sub_category_ids": ["SS0020", "SS0021"],
                    "property_title": "Luxury 3BHK Apartment in Prime Location",
                    "parking_availability": "Yes",
                    "furnishing_type": "Fully Furnished",
                    "description": "Spacious 3BHK apartment with modern amenities, 24/7 security, power backup, and excellent connectivity to metro and shopping centers.",
                    "service_offering_types": ["rent", "sale"]
                },
                "portfolio_images": ["/media/portfolios/img1.jpg", "/media/portfolios/img2.jpg", "/media/portfolios/img3.jpg"],
                "created_at": "2025-08-15T10:30:00Z",
                "updated_at": "2025-08-15T10:30:00Z"
            }
        }

        Success (200) - Individual SOS Provider (POST):
        {
            "status": "success",
            "message": "Provider profile created successfully",
            "profile": {
                "id": 3,
                "full_name": "John Doe",
                "user_type": "provider",
                "provider_type": "individual",
                "service_type": "SOS",
                "gender": "male",
                "date_of_birth": "1990-01-15",
                "profile_photo": "/media/profiles/photo.jpg",
                "profile_complete": true,
                "can_access_app": true,
                "service_coverage_area": 50,
                "provider_id": "PRV0003",
                "service_data": {
                    "main_category_id": "MS0004",
                    "sub_category_ids": ["SS0030", "SS0031"],
                    "contact_number": "9876543210",
                    "location": "Delhi NCR, India",
                    "description": "24/7 emergency medical services available with equipped ambulance and trained medical staff. Specializing in cardiac emergencies and trauma care."
                },
                "portfolio_images": ["/media/portfolios/img1.jpg", "/media/portfolios/img2.jpg"],
                "created_at": "2025-08-15T10:30:00Z",
                "updated_at": "2025-08-15T10:30:00Z"
            }
        }

        Success (200) - Business SOS Provider (POST):
        {
            "status": "success",
            "message": "Provider profile created successfully",
            "profile": {
                "id": 4,
                "user_type": "provider",
                "provider_type": "business",
                "service_type": "SOS",
                "business_name": "Smith Enterprises",
                "business_location": "123 Business St, Delhi",
                "established_date": "2015-06-01",
                "website": "https://smithenterprises.com",
                "profile_photo": "/media/profiles/business_logo.jpg",
                "profile_complete": true,
                "can_access_app": true,
                "service_coverage_area": 50,
                "provider_id": "PRV0004",
                "service_data": {
                    "main_category_id": "MS0004",
                    "sub_category_ids": ["SS0030", "SS0031"],
                    "contact_number": "9876543210",
                    "location": "Delhi NCR, India",
                    "description": "24/7 emergency medical services available with equipped ambulance and trained medical staff. Specializing in cardiac emergencies and trauma care."
                },
                "portfolio_images": ["/media/portfolios/img1.jpg", "/media/portfolios/img2.jpg"],
                "created_at": "2025-08-15T10:30:00Z",
                "updated_at": "2025-08-15T10:30:00Z"
            }
        }

        Error (400) - Validation Failed:
        {
            "status": "error",
            "message": "Validation failed",
            "errors": {
                "main_category_id": ["Invalid main category: MS9999"],
                "service_coverage_area": ["Service coverage area is required for all providers"],
                "sub_category_ids": ["Invalid subcategories: SS9999"]
            }
        }

        Error (400) - Profile Already Exists (POST):
        {
            "status": "error",
            "message": "Profile already exists. Use PATCH method to update.",
            "hint": "Use PATCH /api/1/profiles/provider/setup/ to update your profile"
        }

        Error (404) - Profile Not Found (PATCH):
        {
            "status": "error",
            
            "message": "Profile not found. Use POST method to create profile.",
            "hint": "Use POST /api/1/profiles/provider/setup/ to create your profile"
        }
    """
    try:
        # Handle versioning if needed
        if hasattr(request, 'version'):
            api_version = request.version
            if api_version == 'v2':
                pass

        # Debug logging
        print(f"PROVIDER PROFILE SETUP API CALLED - Method: {request.method}")
        print(f"Request data keys: {list(request.data.keys())}")
        print(f"User: {request.user.mobile_number}")

        # Debug portfolio_images specifically
        if 'portfolio_images' in request.data:
            portfolio_imgs = request.data.getlist('portfolio_images') if hasattr(request.data, 'getlist') else request.data.get('portfolio_images', [])
            print(f"Portfolio images count: {len(portfolio_imgs)}")
            for idx, img in enumerate(portfolio_imgs):
                print(f"  Image {idx}: type={type(img)}, value={img if not hasattr(img, 'read') else 'FILE_OBJECT'}")

        # Method-based validation: POST = create only, PATCH = update only
        if request.method == 'POST':
            # POST should only create, error if profile exists
            try:
                existing_profile = UserProfile.objects.get(user=request.user)
                return Response({
                    "status": "error",
                    "message": "Profile already exists. Use PATCH method to update.",
                    "hint": "Use PATCH /api/1/profiles/provider/setup/ to update your profile"
                }, status=status.HTTP_400_BAD_REQUEST)
            except UserProfile.DoesNotExist:
                pass  # Good, profile doesn't exist, continue with creation

        elif request.method == 'PATCH':
            # PATCH should only update, error if profile doesn't exist
            try:
                existing_profile = UserProfile.objects.get(user=request.user)
            except UserProfile.DoesNotExist:
                return Response({
                    "status": "error",
                    "message": "Profile not found. Use POST method to create profile.",
                    "hint": "Use POST /api/1/profiles/provider/setup/ to create your profile"
                }, status=status.HTTP_404_NOT_FOUND)

        # Validate and process data using ProviderProfileSetupSerializer
        serializer = ProviderProfileSetupSerializer(data=request.data, context={'request': request})

        if serializer.is_valid():
            try:
                # Create profile with all related data
                with transaction.atomic():
                    profile = serializer.save()

                # Return success response
                response_data = ProfileResponseSerializer(profile, context={'request': request}).data

                # Dynamic message based on request method
                message = "Provider profile created successfully" if request.method == 'POST' else "Provider profile updated successfully"

                return Response({
                    "status": "success",
                    "message": message,
                    "profile": response_data
                }, status=status.HTTP_200_OK)

            except Exception as e:
                # Always log the error to console for debugging
                print(f"PROVIDER PROFILE CREATION ERROR: {str(e)}")
                import traceback
                print(f"FULL TRACEBACK: {traceback.format_exc()}")

                return Response({
                    "status": "error",
                    "message": "Failed to create provider profile. Please try again.",
                    "debug_error": str(e) if request.user.is_staff else None
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            # Validation errors
            return Response({
                "status": "error",
                "message": "Validation failed",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        # Always log the error to console for debugging
        print(f"OUTER EXCEPTION IN PROVIDER PROFILE SETUP: {str(e)}")
        import traceback
        print(f"FULL TRACEBACK: {traceback.format_exc()}")

        return Response({
            "status": "error",
            "message": "An unexpected server error occurred. Please try again.",
            "debug_error": str(e) if request.user.is_staff else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_profile_api(request, version=None):

    try:
        from apps.verification.models import AadhaarVerification, LicenseVerification
        from apps.profiles.models import Wallet, ProviderRating
        from apps.profiles.work_assignment_models import WorkOrder
        from apps.work_categories.models import UserWorkSelection, UserWorkSubCategory

        user = request.user

        # Get user profile
        try:
            profile = UserProfile.objects.select_related('wallet', 'rating_summary').get(user=user)
        except UserProfile.DoesNotExist:
            return Response({
                "status": "error",
                "message": "Profile not found"
            }, status=status.HTTP_404_NOT_FOUND)

        # Build user_profile data with all fields
        user_profile_data = {
            "id": profile.id,
            "full_name": profile.full_name,
            "mobile_number": profile.mobile_number,
            "user_type": profile.user_type,
            "service_type": profile.service_type,
            "gender": profile.gender,
            "date_of_birth": profile.date_of_birth.isoformat() if profile.date_of_birth else None,
            "age": profile.age,
            "profile_photo": request.build_absolute_uri(profile.profile_photo.url) if profile.profile_photo else None,
            "languages": [lang.strip() for lang in profile.languages.split(',') if lang.strip()] if profile.languages else [],
            "provider_id": profile.provider_id,
            "service_coverage_area": profile.service_coverage_area,
            "seeker_type": profile.seeker_type,
            "business_name": profile.business_name,
            "business_location": profile.business_location,
            "established_date": profile.established_date.isoformat() if profile.established_date else None,
            "website": profile.website,
            "profile_complete": profile.profile_complete,
            "can_access_app": profile.can_access_app,
            "fcm_token": profile.fcm_token,
            "is_active_for_work": profile.is_active_for_work,
            "created_at": profile.created_at.isoformat() if profile.created_at else None,
            "updated_at": profile.updated_at.isoformat() if profile.updated_at else None
        }

        # Filter fields based on user_type and seeker_type (keep current behavior)
        if profile.user_type == 'seeker':
            # Remove provider-specific fields
            user_profile_data.pop('service_type', None)
            user_profile_data.pop('provider_id', None)
            user_profile_data.pop('service_coverage_area', None)
            user_profile_data.pop('languages', None)
            user_profile_data.pop('is_active_for_work', None)  # Not needed for seekers
            user_profile_data.pop('fcm_token', None)  # Internal field

            # Filter based on seeker_type
            if profile.seeker_type == 'individual':
                # Remove business fields for individual seekers
                user_profile_data.pop('business_name', None)
                user_profile_data.pop('business_location', None)
                user_profile_data.pop('established_date', None)
                user_profile_data.pop('website', None)
            elif profile.seeker_type == 'business':
                # Remove personal fields for business seekers
                user_profile_data.pop('full_name', None)
                user_profile_data.pop('date_of_birth', None)
                user_profile_data.pop('gender', None)
                user_profile_data.pop('age', None)

        elif profile.user_type == 'provider':
            # Remove seeker-specific fields
            user_profile_data.pop('seeker_type', None)
            user_profile_data.pop('fcm_token', None)  # Internal field

            # Determine provider type based on business_name
            is_business_provider = bool(profile.business_name)

            # Filter based on provider type
            if not is_business_provider:
                # Remove business fields for individual providers
                user_profile_data.pop('business_name', None)
                user_profile_data.pop('business_location', None)
                user_profile_data.pop('established_date', None)
                user_profile_data.pop('website', None)
            else:
                # Remove personal fields for business providers
                user_profile_data.pop('full_name', None)
                user_profile_data.pop('date_of_birth', None)
                user_profile_data.pop('gender', None)
                user_profile_data.pop('age', None)

        # Get service_data (category information)
        service_data = None
        if profile.user_type == 'provider' and profile.service_type:
            try:
                work_selection = UserWorkSelection.objects.select_related('main_category').get(user=profile)
                subcategories = UserWorkSubCategory.objects.select_related('sub_category').filter(
                    user_work_selection=work_selection
                )

                service_data = {
                    "main_category_id": work_selection.main_category.category_code if work_selection.main_category else None,
                    "main_category_name": work_selection.main_category.display_name if work_selection.main_category else None,
                    "sub_category_ids": [sub.sub_category.subcategory_code for sub in subcategories],
                    "sub_category_names": [sub.sub_category.display_name for sub in subcategories],
                    "years_experience": work_selection.years_experience,
                    "skills": work_selection.skills
                }
            except UserWorkSelection.DoesNotExist:
                service_data = None

        # For seekers: skip unnecessary data collection and return early
        if profile.user_type == 'seeker':
            return Response({
                "status": "success",
                "message": "User details fetched successfully",
                "data": user_profile_data
            }, status=status.HTTP_200_OK)

        # --- PROVIDER-ONLY DATA COLLECTION BELOW ---

        # Get portfolio images
        portfolio_images = []
        portfolio_imgs = profile.service_portfolio_images.all().order_by('image_order')
        portfolio_images = [request.build_absolute_uri(img.image.url) for img in portfolio_imgs]

        # Get verification status
        verification_status = {
            "aadhaar_verified": False,
            "aadhaar_status": None,
            "license_verified": False,
            "license_status": None
        }

        try:
            aadhaar = AadhaarVerification.objects.get(user=profile)
            verification_status["aadhaar_verified"] = aadhaar.status == 'verified'
            verification_status["aadhaar_status"] = aadhaar.status
        except AadhaarVerification.DoesNotExist:
            pass

        try:
            license_ver = LicenseVerification.objects.get(user=profile)
            verification_status["license_verified"] = license_ver.status == 'verified'
            verification_status["license_status"] = license_ver.status
        except LicenseVerification.DoesNotExist:
            pass

        # Get wallet data
        wallet_data = None
        try:
            wallet = profile.wallet
            wallet_data = {
                "balance": float(wallet.balance),
                "currency": wallet.currency
            }
        except Wallet.DoesNotExist:
            # Create wallet if it doesn't exist
            wallet = Wallet.objects.create(
                user_profile=profile,
                balance=0.00,
                currency='INR'
            )
            wallet_data = {
                "balance": 0.00,
                "currency": "INR"
            }

        # Get rating summary
        rating_summary = None
        try:
            rating = profile.rating_summary
            rating_summary = {
                "average_rating": float(rating.average_rating),
                "total_reviews": rating.total_reviews
            }
        except ProviderRating.DoesNotExist:
            rating_summary = {
                "average_rating": 0.00,
                "total_reviews": 0
            }

        # Get service history counts
        total_service = WorkOrder.objects.filter(provider=user).count()
        completed_service = WorkOrder.objects.filter(provider=user, status='completed').count()
        cancelled_service = WorkOrder.objects.filter(provider=user, status='cancelled').count()
        rejected_service = WorkOrder.objects.filter(provider=user, status='rejected').count()

        service_history = {
            "total_service": total_service,
            "completed_service": completed_service,
            "cancelled_service": cancelled_service,
            "rejected_service": rejected_service
        }

        # Build final response for providers
        response_data = {
            "user_profile": user_profile_data,
            "service_data": service_data,
            "portfolio_images": portfolio_images,
            "verification_status": verification_status,
            "wallet": wallet_data,
            "rating_summary": rating_summary,
            "service_history": service_history
        }

        return Response({
            "status": "success",
            "message": "User details fetched successfully",
            "data": response_data
        }, status=status.HTTP_200_OK)

    except UserProfile.DoesNotExist:
        return Response({
            "status": "error",
            "message": "Profile not found"
        }, status=status.HTTP_404_NOT_FOUND)

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_profile_api: {str(e)}")
        return Response({
            "status": "error",
            "message": "An unexpected server error occurred. Please try again."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_profile_status_api(request, version=None):
    """
    Check if user's profile is complete and can access app

    GET /api/1/profiles/status/

    Headers:
        Authorization: Bearer <jwt_token>

    Response:
        For Provider:
        {
            "status": "success",
            "profile_complete": true,
            "can_access_app": true,
            "user_type": "provider",
            "next_action": "proceed_to_app",
            "main_category": {
                "code": "MS0001",
                "name": "SKILL"
            },
            "sub_category": {
                "code": "SS0006",
                "name": "Beautician"
            }
        }

        For Seeker:
        {
            "status": "success",
            "profile_complete": true,
            "can_access_app": true,
            "user_type": "seeker",
            "next_action": "proceed_to_app"
        }
    """
    try:
        from apps.work_categories.models import UserWorkSelection, UserWorkSubCategory

        try:
            profile = UserProfile.objects.get(user=request.user)
            profile.check_profile_completion()  # Update completion status

            next_action = "proceed_to_app" if profile.can_access_app else "complete_profile"

            response_data = {
                "status": "success",
                "profile_complete": profile.profile_complete,
                "can_access_app": profile.can_access_app,
                "user_type": profile.user_type,
                "next_action": next_action
            }

            # Add category information for providers only
            if profile.user_type == 'provider':
                try:
                    work_selection = UserWorkSelection.objects.get(user=profile)

                    # Add main category
                    if work_selection.main_category:
                        response_data["main_category"] = {
                            "code": work_selection.main_category.category_code,
                            "name": work_selection.main_category.display_name
                        }
                    else:
                        response_data["main_category"] = None

                    # Add sub categories (providers can have multiple, get first one)
                    sub_categories = UserWorkSubCategory.objects.filter(
                        user_work_selection=work_selection
                    ).first()

                    if sub_categories and sub_categories.sub_category:
                        response_data["sub_category"] = {
                            "code": sub_categories.sub_category.subcategory_code,
                            "name": sub_categories.sub_category.display_name
                        }
                    else:
                        response_data["sub_category"] = None

                except UserWorkSelection.DoesNotExist:
                    # No work selection set yet
                    response_data["main_category"] = None
                    response_data["sub_category"] = None

            return Response(response_data, status=status.HTTP_200_OK)

        except UserProfile.DoesNotExist:
            response_data = {
                "status": "success",
                "profile_complete": False,
                "can_access_app": False,
                "user_type": None,
                "next_action": "complete_profile"
            }

            # For users without profiles, we don't know if they're seekers yet
            # So we don't include category fields

            return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            "status": "error",
            "message": "An unexpected server error occurred. Please try again."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


