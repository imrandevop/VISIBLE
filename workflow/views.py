from django.contrib.auth.models import User
from django.http import HttpResponse

def create_admin(request):
    if not User.objects.filter(username="workflow").exists():
        User.objects.create_superuser("admin", "workflow@example.com", "wfadmin1210")
    return HttpResponse("Superuser created")
