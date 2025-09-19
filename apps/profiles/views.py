# apps/profiles/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction

from apps.profiles.serializers import ProfileSetupSerializer, ProfileResponseSerializer
from apps.profiles.models import UserProfile


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def profile_setup_api(request, version=None):
    """
    Complete profile setup API - handles everything in one call
    
    POST /api/v1/profiles/setup/
    
    Headers:
        Authorization: Bearer <jwt_token>
        Content-Type: multipart/form-data
    
    Body (form-data):
        user_type: "worker" or "seeker"
        full_name: "John Doe"
        date_of_birth: "1990-01-15"
        gender: "male" or "female"
        profile_photo: <file> (optional)
        
        # Worker-specific fields (required if user_type=worker)
        main_category_id: "MS0001"
        sub_category_ids: ["SS0001", "SS0002"]
        years_experience: 5
        skills_description: "Expert plumber with residential experience"
        portfolio_images: [<file1>, <file2>, <file3>] (1-3 images required)
        
        # Verification fields (optional)
        aadhaar_number: "123456789012"
        license_number: "DL1234567890" (required for drivers)
        license_type: "driving"
    
    Response:
        Success (200):
        {
            "status": "success",
            "message": "Profile setup completed successfully",
            "profile": {
                "id": 1,
                "full_name": "John Doe",
                "user_type": "worker",
                "gender": "male",
                "date_of_birth": "1990-01-15",
                "profile_photo": "/media/profiles/photo.jpg",
                "profile_complete": true,
                "can_access_app": true,
                "main_category_id": "MS0001",
                "sub_category_ids": ["SS0001", "SS0002"],
                "created_at": "2025-08-15T10:30:00Z",
                "updated_at": "2025-08-15T10:30:00Z"
            }
        }
        
        Error (400):
        {
            "status": "error",
            "message": "Validation failed",
            "errors": {
                "main_category_id": ["Invalid main category: MS9999"],
                "portfolio_images": ["At least one portfolio image is required for workers"],
                "sub_category_ids": ["Invalid subcategories: SS9999, SS8888"]
            }
        }
    """
    try:
        # Handle versioning if needed
        if hasattr(request, 'version'):
            api_version = request.version
            # Future v2 logic can go here
            if api_version == 'v2':
                pass
        
        # Check if user already has a complete profile
        try:
            existing_profile = UserProfile.objects.get(user=request.user)
            if existing_profile.profile_complete:
                return Response({
                    "status": "error",
                    "message": "Profile is already completed",
                    "profile": ProfileResponseSerializer(existing_profile).data
                }, status=status.HTTP_400_BAD_REQUEST)
        except UserProfile.DoesNotExist:
            pass  # No existing profile, continue with setup
        
        # Validate and process data
        serializer = ProfileSetupSerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            try:
                # Create profile with all related data
                with transaction.atomic():
                    profile = serializer.save()
                
                # Return success response
                response_data = ProfileResponseSerializer(profile).data
                return Response({
                    "status": "success",
                    "message": "Profile setup completed successfully",
                    "profile": response_data
                }, status=status.HTTP_200_OK)
                
            except Exception as e:
                return Response({
                    "status": "error",
                    "message": "Failed to create profile. Please try again.",
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
        return Response({
            "status": "error",
            "message": "An unexpected server error occurred. Please try again.",
            "debug_error": str(e) if request.user.is_staff else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_profile_api(request, version=None):
    """
    Get current user's profile data
    
    GET /api/v1/profiles/me/
    
    Headers:
        Authorization: Bearer <jwt_token>
    
    Response:
        Success (200):
        {
            "status": "success",
            "profile": {
                "id": 1,
                "full_name": "John Doe",
                "user_type": "worker",
                "gender": "male",
                "date_of_birth": "1990-01-15",
                "profile_photo": "/media/profiles/photo.jpg",
                "profile_complete": true,
                "can_access_app": true,
                "main_category_id": "MS0001",
                "sub_category_ids": ["SS0001", "SS0002"],
                "created_at": "2025-08-15T10:30:00Z",
                "updated_at": "2025-08-15T10:30:00Z"
            }
        }
        
        Not Found (404):
        {
            "status": "error",
            "message": "Profile not found"
        }
    """
    try:
        profile = UserProfile.objects.get(user=request.user)
        response_data = ProfileResponseSerializer(profile).data
        
        return Response({
            "status": "success",
            "profile": response_data
        }, status=status.HTTP_200_OK)
        
    except UserProfile.DoesNotExist:
        return Response({
            "status": "error",
            "message": "Profile not found"
        }, status=status.HTTP_404_NOT_FOUND)
    
    except Exception as e:
        return Response({
            "status": "error",
            "message": "An unexpected server error occurred. Please try again."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_profile_status_api(request, version=None):
    """
    Check if user's profile is complete and can access app
    
    GET /api/v1/profiles/status/
    
    Headers:
        Authorization: Bearer <jwt_token>
    
    Response:
        {
            "status": "success",
            "profile_complete": true,
            "can_access_app": true,
            "user_type": "worker",
            "next_action": "proceed_to_app" // or "complete_profile"
        }
    """
    try:
        try:
            profile = UserProfile.objects.get(user=request.user)
            profile.check_profile_completion()  # Update completion status
            
            next_action = "proceed_to_app" if profile.can_access_app else "complete_profile"
            
            return Response({
                "status": "success",
                "profile_complete": profile.profile_complete,
                "can_access_app": profile.can_access_app,
                "user_type": profile.user_type,
                "next_action": next_action
            }, status=status.HTTP_200_OK)
            
        except UserProfile.DoesNotExist:
            return Response({
                "status": "success",
                "profile_complete": False,
                "can_access_app": False,
                "user_type": None,
                "next_action": "complete_profile"
            }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            "status": "error",
            "message": "An unexpected server error occurred. Please try again."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)