# apps/work_categories/urls.py
from django.urls import path
from apps.work_categories import views

app_name = 'work_categories'

urlpatterns = [
    # Work category endpoints
    path('', views.list_work_categories_api, name='list_categories'),
]