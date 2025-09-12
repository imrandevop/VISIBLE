# workflow/urls.py
from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(url='/admin/', permanent=True)),  # Redirect root to admin
    
    # Versioned API URLs
    re_path(r'^api/(?P<version>v[0-9]+)/', include([
        path('', include('apps.authentication.urls')),
        path('profiles/', include('apps.profiles.urls')),
        path('work-categories/', include('apps.work_categories.urls')),
        # Add other app URLs here as you expand
        # path('', include('apps.other_app.urls')),
    ])),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)