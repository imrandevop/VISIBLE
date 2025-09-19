# apps/work_categories/views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from apps.work_categories.models import WorkCategory, WorkSubCategory


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_work_categories_api(request, version=None):
    """
    Get all active work categories with their subcategories
    
    GET /api/v1/work-categories/
    
    Headers:
        Authorization: Bearer <jwt_token>
    
    Response:
        {
            "status": "success",
            "categories": [
                {
                    "id": "MS0001",
                    "name": "worker",
                    "display_name": "Worker",
                    "description": "General worker services",
                    "subcategories": "Plumber Electrician Carpenter Painter"
                },
                {
                    "id": "MS0002",
                    "name": "driver",
                    "display_name": "Driver",
                    "description": "Transportation services",
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