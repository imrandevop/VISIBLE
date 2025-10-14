# apps/referrals/urls.py
from django.urls import path
from apps.referrals import views

app_name = 'referrals'

urlpatterns = [
    # Single endpoint handling both POST and GET
    path('', views.referral_api, name='referral_api'),
]
