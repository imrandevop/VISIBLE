from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', RedirectView.as_view(url='/admin/', permanent=True)),  # Redirect root to admin
    
    # Versioned API URLs
    re_path(r'^api/(?P<version>v[0-9]+)/', include([
        path('', include('apps.authentication.urls')),
        # Add other app URLs here as you expand
        # path('', include('apps.other_app.urls')),
    ])),
]