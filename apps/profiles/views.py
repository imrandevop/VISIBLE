# apps/profiles/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction

from apps.profiles.serializers import ProfileSetupSerializer, ProfileResponseSerializer
from apps.profiles.models import UserProfile
from apps.core.models import ProviderActiveStatus

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def profile_setup_api(request, version=None):
    """
    Complete profile setup API - handles everything in one call
    
    POST /api/1/profiles/setup/
    
    Headers:
        Authorization: Bearer <jwt_token>
        Content-Type: multipart/form-data
    
    Body (form-data):
        user_type: "provider" or "seeker"
        full_name: "John Doe"
        date_of_birth: "1990-01-15"
        gender: "male" or "female"
        profile_photo: <file> (optional)
        
        # Provider-specific fields (required if user_type=provider)
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
                "user_type": "provider",
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
                "portfolio_images": ["At least one portfolio image is required for providers"],
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
                    "profile": ProfileResponseSerializer(existing_profile, context={'request': request}).data
                }, status=status.HTTP_400_BAD_REQUEST)
        except UserProfile.DoesNotExist:
            pass  # No existing profile, continue with setup
        
        # Debug logging
        print(f"PROFILE SETUP API CALLED")
        print(f"Request data keys: {list(request.data.keys())}")
        print(f"User: {request.user.mobile_number}")

        # Validate and process data
        serializer = ProfileSetupSerializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            try:
                # Create profile with all related data
                with transaction.atomic():
                    profile = serializer.save()
                
                # Return success response
                response_data = ProfileResponseSerializer(profile, context={'request': request}).data
                return Response({
                    "status": "success",
                    "message": "Profile setup completed successfully",
                    "profile": response_data
                }, status=status.HTTP_200_OK)
                
            except Exception as e:
                # Always log the error to console for debugging
                print(f"PROFILE CREATION ERROR: {str(e)}")
                import traceback
                print(f"FULL TRACEBACK: {traceback.format_exc()}")

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
    
    GET /api/1/profiles/me/
    
    Headers:
        Authorization: Bearer <jwt_token>
    
    Response:
        Success (200):
        {
            "status": "success",
            "profile": {
                "id": 1,
                "full_name": "John Doe",
                "user_type": "provider",
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
        response_data = ProfileResponseSerializer(profile, context={'request': request}).data
        
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
                "name": "WORKER"
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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def provider_dashboard_api(request, version=None):
    """
    Get provider dashboard data including active status, wallet, services, and previous services

    GET /api/1/profiles/provider/dashboard/

    Headers:
        Authorization: Bearer <jwt_token>

    Response:
        Success (200):
        {
            "status": "success",
            "message": "provider dashboard data fetched successfully",
            "data": {
                "active_status": {
                    "is_active": false,
                    "provider_id": "WKR1023",
                    "last_updated": "2025-10-07T10:55:00Z"
                },
                "wallet": {
                    "balance": 850,
                    "currency": "INR"
                },
                "services": {
                    "completed_service": 4,
                    "cancelled_service": 1
                },
                "previous_services": [...],
                "aadhaar_verified": true
            }
        }

        Error (403):
        {
            "status": "error",
            "message": "Only providers can access dashboard"
        }

        Error (400):
        {
            "status": "error",
            "message": "Profile incomplete. Please complete your profile setup."
        }
    """
    try:
        user = request.user

        # Check if user has profile
        try:
            user_profile = UserProfile.objects.select_related('wallet').get(user=user)
        except UserProfile.DoesNotExist:
            return Response({
                "status": "error",
                "message": "User profile not found. Please complete profile setup."
            }, status=status.HTTP_404_NOT_FOUND)

        # Check if user is provider
        if user_profile.user_type != 'provider':
            return Response({
                "status": "error",
                "message": "Only providers can access dashboard"
            }, status=status.HTTP_403_FORBIDDEN)

        # Check if profile is complete
        if not user_profile.profile_complete:
            return Response({
                "status": "error",
                "message": "Profile incomplete. Please complete your profile setup."
            }, status=status.HTTP_400_BAD_REQUEST)

        # 1. Get active status
        provider_status = ProviderActiveStatus.objects.filter(user=user).first()
        active_status_data = {
            "is_active": provider_status.is_active if provider_status else False,
            "provider_id": user_profile.provider_id,
            "last_updated": user_profile.updated_at.isoformat() if user_profile.updated_at else None
        }

        # 2. Get wallet data
        wallet_data = {
            "balance": 0,
            "currency": "INR"
        }

        # Check if wallet exists, if not create it
        if hasattr(user_profile, 'wallet'):
            wallet = user_profile.wallet
            wallet_data = {
                "balance": float(wallet.balance),
                "currency": wallet.currency
            }
        else:
            # Create wallet if doesn't exist
            from apps.profiles.models import Wallet
            wallet = Wallet.objects.create(
                user_profile=user_profile,
                balance=0.00,
                currency='INR'
            )
            wallet_data = {
                "balance": 0,
                "currency": "INR"
            }

        # 3. Get services statistics (all time)
        from apps.profiles.work_assignment_models import WorkOrder

        completed_count = WorkOrder.objects.filter(
            provider=user,
            status='completed'
        ).count()

        cancelled_count = WorkOrder.objects.filter(
            provider=user,
            status='cancelled'
        ).count()

        services_data = {
            "completed_service": completed_count,
            "cancelled_service": cancelled_count
        }

        # 4. Get previous services (5 most recent, all statuses)
        work_orders = WorkOrder.objects.filter(
            provider=user
        ).select_related('seeker__profile').order_by('-created_at')[:5]

        previous_services = []
        for order in work_orders:
            # Format date and time
            created_at = order.created_at
            date_str = created_at.strftime("%Y-%m-%d")
            time_str = created_at.strftime("%I:%M %p")

            previous_services.append({
                "customer_name": order.seeker_profile.full_name if hasattr(order, 'seeker_profile') else "Unknown",
                "date": date_str,
                "time": time_str,
                "status": order.status
            })

        # 5. Check aadhaar verification
        aadhaar_verified = False
        try:
            from apps.verification.models import AadhaarVerification
            aadhaar_verification = AadhaarVerification.objects.get(user=user_profile)
            aadhaar_verified = aadhaar_verification.status == 'verified'
        except AadhaarVerification.DoesNotExist:
            aadhaar_verified = False

        # Build response
        response_data = {
            "status": "success",
            "message": "provider dashboard data fetched successfully",
            "data": {
                "active_status": active_status_data,
                "wallet": wallet_data,
                "services": services_data,
                "previous_services": previous_services,
                "aadhaar_verified": aadhaar_verified
            }
        }

        return Response(response_data, status=status.HTTP_200_OK)

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in provider dashboard API: {str(e)}")
        return Response({
            "status": "error",
            "message": "An unexpected server error occurred. Please try again."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)