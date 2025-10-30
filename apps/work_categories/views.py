# apps/work_categories/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from apps.work_categories.models import WorkCategory, WorkSubCategory, ServiceRequest
from django.db import IntegrityError


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_work_categories_api(request, version=None):
    """
    Get all active work categories with their subcategories
    
    GET /api/1/work-categories/
    
    Headers:
        Authorization: Bearer <jwt_token>
    
    Response:
        {
            "status": "success",
            "categories": [
                {
                    "id": "MS0001",
                    "name": "skill",
                    "display_name": "Skill",
                    "description": "General skill services",
                    "subcategories": "Plumber Electrician Carpenter Painter"
                },
                {
                    "id": "MS0002",
                    "name": "vehicle",
                    "display_name": "Vehicle",
                    "description": "Vehicle services",
                    "subcategories": "Taxi Delivery Truck Auto-Rickshaw"
                },
                {
                    "id": "MS0003",
                    "name": "business",
                    "display_name": "Business",
                    "description": "Business services",
                    "subcategories": ""
                }
            ]
        }
    """
    try:
        categories = WorkCategory.objects.filter(is_active=True).order_by('sort_order')
        
        categories_data = []
        for category in categories:
            # Get subcategories for this category
            subcategories = WorkSubCategory.objects.filter(
                category=category,
                is_active=True
            ).order_by('sort_order')
            
            # Create space-separated string of subcategory display names
            subcategory_names = " ".join([sub.display_name for sub in subcategories])
            
            categories_data.append({
                'id': category.category_code,
                'name': category.name,
                'display_name': category.display_name,
                'description': category.description,
                'subcategories': subcategory_names
            })
        
        return Response({
            "status": "success",
            "categories": categories_data
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            "status": "error",
            "message": "An unexpected server error occurred. Please try again."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def request_service_api(request, version=None):
    """
    API endpoint for users to request services not available in categories

    POST /api/1/work-categories/request-service/

    Headers:
        Authorization: Bearer <
        jwt_token>

    Body:
        {
            "service_name": "Custom plumbing service"
        }

    Response:
        {
            "name": "Custom plumbing service",
            "message": "Service request submitted successfully"
        }
    """
    try:
        service_name = request.data.get('service_name', '').strip()

        if not service_name:
            return Response({
                "error": "Service name is required"
            }, status=status.HTTP_400_BAD_REQUEST)

        # Create service request
        try:
            service_request = ServiceRequest.objects.create(
                user=request.user,
                service_name=service_name
            )

            return Response({
                "name": service_name,
                "message": "Service request submitted successfully"
            }, status=status.HTTP_201_CREATED)

        except IntegrityError:
            # User already requested this exact service
            return Response({
                "error": "You have already requested this service"
            }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({
            "error": "An unexpected server error occurred. Please try again."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)