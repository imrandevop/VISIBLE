from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse

def api_root(request):
    return JsonResponse({"message": "VISIBLE API", "version": "1.0", "status": "active"})

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(url='/admin/', permanent=True)),
    
    # API endpoints
    path('api/1/authentication/', include('apps.authentication.urls')),
    path('api/1/profiles/', include('apps.profiles.urls')),
    path('api/1/work-categories/', include('apps.work_categories.urls')),
    path('api/1/location/', include('apps.location_services.urls')),
    path('api/1/referral/', include('apps.referrals.urls')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)