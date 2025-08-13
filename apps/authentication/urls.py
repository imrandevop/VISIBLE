#apps\authentication\urls.py
from django.urls import path
from . import views

urlpatterns = [
    # OTP endpoints
    path('send-otp/', views.send_otp_api, name='send_otp'),  # Use same for send & resend
    path('verify-otp/', views.verify_otp_api, name='verify_otp'),
    path('refresh-token/', views.refresh_token_api, name='refresh_token'),
]