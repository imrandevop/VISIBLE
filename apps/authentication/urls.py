from django.urls import path
from . import views
from django.http import JsonResponse

def auth_info(request):
    return JsonResponse({"app": "authentication", "status": "active", "endpoints": ["send-otp", "verify-otp", "refresh-token"]})

urlpatterns = [
    path('', auth_info, name='auth_info'),
    # OTP endpoints
    path('send-otp/', views.send_otp_api, name='send_otp'),
    path('verify-otp/', views.verify_otp_api, name='verify_otp'),
    path('refresh-token/', views.refresh_token_api, name='refresh_token'),
]