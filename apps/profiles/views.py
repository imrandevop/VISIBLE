# apps/profiles/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction

from apps.profiles.serializers import ProfileSetupSerializer, ProfileResponseSerializer, WalletSerializer
from apps.profiles.models import UserProfile, Wallet
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

        # Debug logging
        print(f"PROFILE SETUP API CALLED")
        print(f"Request data keys: {list(request.data.keys())}")
        print(f"User: {request.user.mobile_number}")

        # Debug portfolio_images specifically
        if 'portfolio_images' in request.data:
            portfolio_imgs = request.data.getlist('portfolio_images') if hasattr(request.data, 'getlist') else request.data.get('portfolio_images', [])
            print(f"Portfolio images count: {len(portfolio_imgs)}")
            for idx, img in enumerate(portfolio_imgs):
                print(f"  Image {idx}: type={type(img)}, value={img if not hasattr(img, 'read') else 'FILE_OBJECT'}")

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
        # Always log the error to console for debugging
        print(f"OUTER EXCEPTION IN PROFILE SETUP: {str(e)}")
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
    """
    Get current user's complete profile data including work history

    GET /api/1/profiles/me/

    Headers:
        Authorization: Bearer <jwt_token>

    Response:
        Success (200):
        {
            "status": "success",
            "message": "User details fetched successfully",
            "data": {
                "user_profile": {...},
                "service_data": {...},
                "portfolio_images": [...],
                "verification_status": {...},
                "wallet": {...},
                "rating_summary": {...},
                "service_history": {
                    "total_service": 47,
                    "completed_service": 42,
                    "cancelled_service": 3,
                    "rejected_service": 2
                }
            }
        }

        Not Found (404):
        {
            "status": "error",
            "message": "Profile not found"
        }
    """
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

        # Build user_profile data
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
            "profile_complete": profile.profile_complete,
            "can_access_app": profile.can_access_app,
            "fcm_token": profile.fcm_token,
            "is_active_for_work": profile.is_active_for_work,
            "created_at": profile.created_at.isoformat() if profile.created_at else None,
            "updated_at": profile.updated_at.isoformat() if profile.updated_at else None
        }

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

        # Get portfolio images
        portfolio_images = []
        if profile.user_type == 'provider':
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

        # Get wallet data (only for providers)
        wallet_data = None
        if profile.user_type == 'provider':
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

        # Get rating summary (only for providers)
        rating_summary = None
        if profile.user_type == 'provider':
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
        if profile.user_type == 'provider':
            # For providers, count orders where they are the provider
            total_service = WorkOrder.objects.filter(provider=user).count()
            completed_service = WorkOrder.objects.filter(provider=user, status='completed').count()
            cancelled_service = WorkOrder.objects.filter(provider=user, status='cancelled').count()
            rejected_service = WorkOrder.objects.filter(provider=user, status='rejected').count()
        else:
            # For seekers, count orders where they are the seeker
            total_service = WorkOrder.objects.filter(seeker=user).count()
            completed_service = WorkOrder.objects.filter(seeker=user, status='completed').count()
            cancelled_service = WorkOrder.objects.filter(seeker=user, status='cancelled').count()
            rejected_service = WorkOrder.objects.filter(seeker=user, status='rejected').count()

        service_history = {
            "total_service": total_service,
            "completed_service": completed_service,
            "cancelled_service": cancelled_service,
            "rejected_service": rejected_service
        }

        # Build final response
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
                "profile_complete": true,
                "active_status": {
                    "is_active": false,
                    "provider_id": "WKR1023",
                    "last_updated": "2025-10-07T10:55:00Z"
                },
                "wallet": {
                    "balance": 850.00,
                    "currency": "INR",
                    "online_subscription_expires_at": "2025-10-15T10:30:00Z",
                    "is_online_subscription_active": true,
                    "online_subscription_time_remaining": "12h 0m"
                },
                "services": {
                    "active_services": 2
                },
                "offers": [
                    {
                        "offer_id": "OFF001",
                        "title": "Snapdeal Mega Sale",
                        "description": "Get up to 70% off on all products",
                        "image_url": "https://imagesvs.oneindia.com/img/2016/09/snapdeal-21-1474438626.jpg",
                        "valid_until": "2025-10-31T23:59:59Z",
                        "is_active": true,
                        "priority": 1
                    }
                ],
                "previous_services": [...],
                "aadhaar_verified": true,
                "maintenance_mode": false
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

        # 1. Get active status from ProviderActiveStatus (location service)
        provider_status = ProviderActiveStatus.objects.filter(user=user).first()
        active_status_data = {
            "is_active": provider_status.is_active if provider_status else False,
            "provider_id": user_profile.provider_id,
            "last_updated": provider_status.last_active_at.isoformat() if provider_status and provider_status.last_active_at else None
        }

        # 2. Get wallet data with subscription details
        # Check if wallet exists, if not create it
        if hasattr(user_profile, 'wallet'):
            wallet = user_profile.wallet
        else:
            # Create wallet if doesn't exist
            from apps.profiles.models import Wallet
            wallet = Wallet.objects.create(
                user_profile=user_profile,
                balance=0.00,
                currency='INR'
            )

        # Calculate subscription time remaining
        from django.utils import timezone
        online_subscription_time_remaining = None
        if wallet.online_subscription_expires_at:
            now = timezone.now()
            if now < wallet.online_subscription_expires_at:
                time_diff = wallet.online_subscription_expires_at - now
                total_seconds = int(time_diff.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                online_subscription_time_remaining = f"{hours}h {minutes}m"

        wallet_data = {
            "balance": float(wallet.balance),
            "currency": wallet.currency,
            "online_subscription_expires_at": wallet.online_subscription_expires_at.isoformat() if wallet.online_subscription_expires_at else None,
            "is_online_subscription_active": wallet.is_online_subscription_active(),
            "online_subscription_time_remaining": online_subscription_time_remaining
        }

        # 3. Get active services count (services with active WorkSession)
        from apps.profiles.work_assignment_models import WorkOrder, WorkSession

        active_services_count = WorkSession.objects.filter(
            work_order__provider=user,
            connection_state='active'
        ).count()

        services_data = {
            "active_services": active_services_count
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

        # 6. Get active offers (sorted by priority, only active and not expired)
        from apps.profiles.models import Offer
        from django.utils import timezone

        active_offers = Offer.objects.filter(
            is_active=True,
            valid_until__gt=timezone.now()
        ).order_by('priority', '-created_at')

        offers_data = []
        for offer in active_offers:
            offers_data.append({
                "offer_id": offer.offer_id,
                "title": offer.title,
                "description": offer.description,
                "image_url": offer.image_url,
                "valid_until": offer.valid_until.isoformat(),
                "is_active": offer.is_active,
                "priority": offer.priority
            })

        # 7. Get maintenance mode status (from the first offer record, default to False)
        maintenance_mode = False
        first_offer = Offer.objects.first()
        if first_offer:
            maintenance_mode = first_offer.maintenance_mode

        # Build response
        response_data = {
            "status": "success",
            "message": "provider dashboard data fetched successfully",
            "data": {
                "profile_complete": user_profile.profile_complete,
                "active_status": active_status_data,
                "wallet": wallet_data,
                "services": services_data,
                "offers": offers_data,
                "previous_services": previous_services,
                "aadhaar_verified": aadhaar_verified,
                "maintenance_mode": maintenance_mode
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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_wallet_details_api(request, version=None):
    """
    Get provider's wallet details including balance, subscription status, and recent transactions

    GET /api/1/profiles/wallet/

    Headers:
        Authorization: Bearer <jwt_token>

    Response:
        Success (200):
        {
            "status": "success",
            "message": "Wallet details fetched successfully",
            "data": {
                "id": 1,
                "balance": 850.00,
                "currency": "INR",
                "last_online_payment_at": "2025-10-14T10:30:00Z",
                "online_subscription_expires_at": "2025-10-15T10:30:00Z",
                "is_online_subscription_active": true,
                "online_subscription_time_remaining": "12h 0m",
                "recent_transactions": [
                    {
                        "id": 1,
                        "transaction_type": "debit",
                        "amount": 20.00,
                        "description": "24-hour online subscription charge",
                        "balance_after": 830.00,
                        "created_at": "2025-10-14T10:30:00Z"
                    },
                    ...
                ],
                "created_at": "2025-10-01T08:00:00Z",
                "updated_at": "2025-10-14T10:30:00Z"
            }
        }

        Error (403):
        {
            "status": "error",
            "message": "Only providers can access wallet details"
        }

        Error (404):
        {
            "status": "error",
            "message": "Wallet not found for this provider"
        }
    """
    try:
        user = request.user

        # Check if user has profile
        try:
            user_profile = UserProfile.objects.get(user=user)
        except UserProfile.DoesNotExist:
            return Response({
                "status": "error",
                "message": "User profile not found. Please complete profile setup."
            }, status=status.HTTP_404_NOT_FOUND)

        # Check if user is provider
        if user_profile.user_type != 'provider':
            return Response({
                "status": "error",
                "message": "Only providers can access wallet details"
            }, status=status.HTTP_403_FORBIDDEN)

        # Get or create wallet
        wallet, created = Wallet.objects.get_or_create(
            user_profile=user_profile,
            defaults={
                'balance': 0.00,
                'currency': 'INR'
            }
        )

        # Serialize wallet data
        serializer = WalletSerializer(wallet, context={'request': request})

        return Response({
            "status": "success",
            "message": "Wallet details fetched successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_wallet_details_api: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return Response({
            "status": "error",
            "message": "An unexpected server error occurred. Please try again."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)