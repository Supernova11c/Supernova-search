from django.urls import path
from . import views

urlpatterns = [
    path("", views.search_page, name="search-home"),
    path("api/search/", views.search_api, name="django-search-api"),
    path("api/health/", views.health, name="django-health"),
    path("api/dashboard/", views.dashboard_api, name="django-dashboard-api"),
]
